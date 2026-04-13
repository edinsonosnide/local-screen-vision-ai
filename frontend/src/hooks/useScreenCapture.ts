import { useCallback, useEffect, useRef, useState } from "react";

type FrameCallback = (b64: string) => void;

export function useScreenCapture(
  onFrame: FrameCallback,
  intervalMs: number = 2000
) {
  const [active, setActive] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  const captureFrame = useCallback(() => {
    const video = videoRef.current;
    if (!video || video.readyState < 2) return;

    if (!canvasRef.current) {
      canvasRef.current = document.createElement("canvas");
    }
    const canvas = canvasRef.current;
    canvas.width = Math.min(video.videoWidth, 1280);
    canvas.height = Math.min(
      video.videoHeight,
      Math.round((video.videoHeight / video.videoWidth) * canvas.width)
    );
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    const dataUrl = canvas.toDataURL("image/jpeg", 0.7);
    const b64 = dataUrl.split(",")[1];
    onFrame(b64);
  }, [onFrame]);

  const start = useCallback(async () => {
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getDisplayMedia({
        video: { frameRate: 1 },
        audio: false,
      });
      streamRef.current = stream;

      const video = document.createElement("video");
      video.srcObject = stream;
      video.muted = true;
      video.playsInline = true;
      await video.play();
      videoRef.current = video;

      stream.getVideoTracks()[0].onended = () => stop();

      // Capture the first frame immediately so latest_frame is never null
      // when the user first speaks, then tick on the regular interval.
      setTimeout(captureFrame, 300);
      timerRef.current = setInterval(captureFrame, intervalMs);
      setActive(true);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg);
    }
  }, [captureFrame, intervalMs]);

  const stop = useCallback(() => {
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = null;
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    if (videoRef.current) {
      videoRef.current.srcObject = null;
      videoRef.current = null;
    }
    setActive(false);
  }, []);

  // Restart interval when intervalMs changes
  useEffect(() => {
    if (!active) return;
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = setInterval(captureFrame, intervalMs);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [active, intervalMs, captureFrame]);

  return { active, error, start, stop };
}
