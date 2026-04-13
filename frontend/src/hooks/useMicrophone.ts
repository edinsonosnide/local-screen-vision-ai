import { useCallback, useRef, useState } from "react";

type AudioChunkCallback = (b64: string) => void;

export function useMicrophone(onChunk: AudioChunkCallback) {
  const [active, setActive] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ctxRef = useRef<AudioContext | null>(null);
  const nodeRef = useRef<AudioWorkletNode | null>(null);
  const streamRef = useRef<MediaStream | null>(null);

  const start = useCallback(async () => {
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      const ctx = new AudioContext();
      ctxRef.current = ctx;

      await ctx.audioWorklet.addModule("/audio-processor.js");

      const source = ctx.createMediaStreamSource(stream);
      const worklet = new AudioWorkletNode(ctx, "audio-processor");
      nodeRef.current = worklet;

      worklet.port.onmessage = (ev: MessageEvent) => {
        const int16 = new Int16Array(ev.data.data as ArrayBuffer);
        const bytes = new Uint8Array(int16.buffer);
        // Base64 encode
        let binary = "";
        for (let i = 0; i < bytes.byteLength; i++) {
          binary += String.fromCharCode(bytes[i]);
        }
        onChunk(btoa(binary));
      };

      source.connect(worklet);
      worklet.connect(ctx.destination); // needed in some browsers

      setActive(true);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg);
    }
  }, [onChunk]);

  const stop = useCallback(() => {
    nodeRef.current?.disconnect();
    nodeRef.current = null;
    ctxRef.current?.close();
    ctxRef.current = null;
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    setActive(false);
  }, []);

  return { active, error, start, stop };
}
