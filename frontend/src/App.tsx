import { Mic, MicOff, Monitor, MonitorOff, ScanEye } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { ConfigPanel } from "./components/ConfigPanel";
import { DebugLog } from "./components/DebugLog";
import { HardwarePanel } from "./components/HardwarePanel";
import { ModelStatusPanel } from "./components/ModelStatusPanel";
import { RealTimeIndicators } from "./components/RealTimeIndicators";
import { SystemDisplay } from "./components/SystemDisplay";
import { useMicrophone } from "./hooks/useMicrophone";
import { useScreenCapture } from "./hooks/useScreenCapture";
import { useWebSocket } from "./hooks/useWebSocket";
import type {
  AllModelStatus,
  Config,
  HardwareInfo,
  LogEntry,
  PipelineState,
} from "./types";

const LS_KEY = "lsva_config";

function loadConfig(): Config {
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (raw) {
      const saved = JSON.parse(raw) as Partial<Config>;
      // Cap frame interval — values above 5s make the model blind between turns
      if (saved.frameInterval && saved.frameInterval > 5) {
        saved.frameInterval = DEFAULT_CONFIG.frameInterval;
      }
      return { ...DEFAULT_CONFIG, ...saved };
    }
  } catch {
    // ignore
  }
  return DEFAULT_CONFIG;
}

const DEFAULT_CONFIG: Config = {
  frameInterval: 1.5,
  vadSilence: 0.8,
  wsUrl: `ws://${window.location.hostname}:8000/ws`,
  audioMode: "whisper",
  ttsEnabled: false,
  thinkingEnabled: false,
};

let logIdCounter = 0;

export default function App() {
  const [config, setConfigState] = useState<Config>(loadConfig);
  const [modelStatus, setModelStatus] = useState<AllModelStatus | null>(null);
  const [hw, setHw] = useState<HardwareInfo | null>(null);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [transcript, setTranscript] = useState("");
  const [llmResponse, setLlmResponse] = useState("");
  const [pipelineState, setPipelineState] = useState<PipelineState>("idle");
  const [ttsPlaying, setTtsPlaying] = useState(false);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const ttsQueueRef = useRef<string[]>([]);
  const ttsPlayingRef = useRef(false);
  const ttsEnabledRef = useRef(config.ttsEnabled);
  useEffect(() => { ttsEnabledRef.current = config.ttsEnabled; }, [config.ttsEnabled]);

  const addLog = useCallback((entry: Omit<LogEntry, "id">) => {
    setLogs((prev) => [
      ...prev.slice(-499), // cap at 500
      { ...entry, id: String(++logIdCounter) },
    ]);
  }, []);

  // -------------------------------------------------------------------------
  // TTS audio playback — sequential queue so segments don't overlap
  // -------------------------------------------------------------------------
  const drainTTSQueue = useCallback(async function drain() {
    if (ttsPlayingRef.current) return;
    const b64 = ttsQueueRef.current.shift();
    if (!b64) {
      setTtsPlaying(false);
      return;
    }

    ttsPlayingRef.current = true;
    setTtsPlaying(true);
    try {
      if (!audioCtxRef.current || audioCtxRef.current.state === "closed") {
        audioCtxRef.current = new AudioContext();
      }
      const ctx = audioCtxRef.current;
      if (ctx.state === "suspended") await ctx.resume();

      const binary = atob(b64);
      const bytes = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
      const buf = bytes.buffer.slice(0);
      const decoded = await ctx.decodeAudioData(buf);
      const src = ctx.createBufferSource();
      src.buffer = decoded;
      src.connect(ctx.destination);
      src.addEventListener("ended", () => {
        ttsPlayingRef.current = false;
        drain();
      });
      src.start();
    } catch (err) {
      ttsPlayingRef.current = false;
      addLog({ level: "error", message: `Audio playback error: ${err}`, timestamp: Date.now() / 1000, latency_ms: null });
      drain();
    }
  }, [addLog]);

  const enqueueTTS = useCallback((b64: string) => {
    ttsQueueRef.current.push(b64);
    void drainTTSQueue();
  }, [drainTTSQueue]);

  // -------------------------------------------------------------------------
  // WebSocket
  // -------------------------------------------------------------------------
  const handleMessage = useCallback(
    (msg: { type: string; data: unknown }) => {
      switch (msg.type) {
        case "model_status":
          setModelStatus(msg.data as AllModelStatus);
          break;
        case "hardware":
          setHw(msg.data as HardwareInfo);
          break;
        case "log": {
          const d = msg.data as LogEntry;
          addLog(d);
          break;
        }
        case "transcript": {
          const d = msg.data as { text: string; is_final: boolean };
          setTranscript(d.text);
          break;
        }
        case "llm_response": {
          const d = msg.data as { text: string };
          setLlmResponse(d.text);
          break;
        }
        case "llm_response_start":
          // New streaming response beginning — clear previous answer
          setLlmResponse("");
          setPipelineState("streaming");
          break;
        case "llm_chunk":
          // Streaming delta — append to current response
          setLlmResponse((prev) => prev + (msg.data as string));
          break;
        case "tts_audio":
          if (ttsEnabledRef.current) enqueueTTS(msg.data as string);
          break;
        case "pipeline_state":
          setPipelineState((msg.data as string) as PipelineState);
          break;
        case "pong":
          break;
      }
    },
    [addLog, enqueueTTS]
  );

  const { state: wsState, send } = useWebSocket({
    url: config.wsUrl,
    onMessage: handleMessage,
    onConnect: () => addLog({ level: "info", message: "WebSocket connected", timestamp: Date.now() / 1000, latency_ms: null }),
    onDisconnect: () => addLog({ level: "warn", message: "WebSocket disconnected — reconnecting…", timestamp: Date.now() / 1000, latency_ms: null }),
  });

  // -------------------------------------------------------------------------
  // Microphone → audio chunks
  // -------------------------------------------------------------------------
  const handleAudioChunk = useCallback(
    (b64: string) => {
      send({ type: "audio_chunk", data: b64 });
    },
    [send]
  );

  const mic = useMicrophone(handleAudioChunk);

  useEffect(() => {
    if (mic.error) {
      addLog({ level: "error", message: `Mic error: ${mic.error}`, timestamp: Date.now() / 1000, latency_ms: null });
    }
  }, [mic.error, addLog]);

  // -------------------------------------------------------------------------
  // Screen capture → frames
  // -------------------------------------------------------------------------
  const handleFrame = useCallback(
    (b64: string) => {
      send({ type: "screen_frame", data: b64 });
    },
    [send]
  );

  const screen = useScreenCapture(handleFrame, config.frameInterval * 1000);

  useEffect(() => {
    if (screen.error) {
      addLog({ level: "error", message: `Screen error: ${screen.error}`, timestamp: Date.now() / 1000, latency_ms: null });
    }
  }, [screen.error, addLog]);

  // -------------------------------------------------------------------------
  // Config changes
  // -------------------------------------------------------------------------
  const handleConfigChange = useCallback(
    (patch: Partial<Config>) => {
      setConfigState((prev) => {
        const next = { ...prev, ...patch };
        localStorage.setItem(LS_KEY, JSON.stringify(next));
        send({
          type: "config_update",
          data: {
            frame_interval: next.frameInterval,
            vad_silence: next.vadSilence,
            audio_mode: next.audioMode,
            tts_enabled: next.ttsEnabled,
            thinking_enabled: next.thinkingEnabled,
          },
        });
        return next;
      });
    },
    [send]
  );

  const handleClearHistory = useCallback(() => {
    send({ type: "clear_history" });
    setTranscript("");
    setLlmResponse("");
  }, [send]);

  // Keepalive ping
  useEffect(() => {
    const id = setInterval(() => send({ type: "ping" }), 15000);
    return () => clearInterval(id);
  }, [send]);

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------
  return (
    <div className="h-screen flex flex-col bg-surface overflow-hidden">
      {/* ── Header ── */}
      <header className="flex items-center gap-4 px-4 py-2.5 border-b border-surface-border bg-surface-card flex-shrink-0">
        <div className="flex items-center gap-2">
          <ScanEye className="w-5 h-5 text-accent-blue" />
          <h1 className="text-sm font-semibold text-gray-100 tracking-tight">
            Local Screen Vision AI
          </h1>
          <span className="text-xs text-gray-600 hidden sm:inline">
            · Gemma 4 E2B-it
          </span>
        </div>

        <div className="flex-1" />

        <RealTimeIndicators
          wsState={wsState}
          micActive={mic.active}
          screenActive={screen.active}
          pipelineState={pipelineState}
          ttsPlaying={ttsPlaying}
        />

        <div className="h-5 w-px bg-surface-border ml-2" />

        {/* Control buttons */}
        <button
          onClick={mic.active ? mic.stop : mic.start}
          className={mic.active ? "btn-danger flex items-center gap-1.5" : "btn-green flex items-center gap-1.5"}
          disabled={wsState !== "connected"}
        >
          {mic.active ? (
            <><MicOff className="w-3.5 h-3.5" /> Stop Mic</>
          ) : (
            <><Mic className="w-3.5 h-3.5" /> Start Mic</>
          )}
        </button>

        <button
          onClick={screen.active ? screen.stop : screen.start}
          className={screen.active ? "btn-danger flex items-center gap-1.5" : "btn-primary flex items-center gap-1.5"}
          disabled={wsState !== "connected"}
        >
          {screen.active ? (
            <><MonitorOff className="w-3.5 h-3.5" /> Stop Screen</>
          ) : (
            <><Monitor className="w-3.5 h-3.5" /> Share Screen</>
          )}
        </button>
      </header>

      {/* ── Main layout ── */}
      <div className="flex flex-1 gap-2 p-2 overflow-hidden">
        {/* Left column */}
        <div className="w-56 flex-shrink-0 flex flex-col gap-2 overflow-auto">
          <ModelStatusPanel status={modelStatus} />
          <HardwarePanel hw={hw} />
        </div>

        {/* Center column */}
        <div className="flex-1 min-w-0">
          <SystemDisplay
            transcript={transcript}
            llmResponse={llmResponse}
            pipelineState={pipelineState}
            ttsPlaying={ttsPlaying}
          />
        </div>

        {/* Right column */}
        <div className="w-72 flex-shrink-0">
          <DebugLog
            logs={logs}
            onClear={() => setLogs([])}
          />
        </div>
      </div>

      {/* ── Footer config bar ── */}
      <div className="flex-shrink-0 border-t border-surface-border px-2 py-1.5">
        <ConfigPanel
          config={config}
          onChange={handleConfigChange}
          onClearHistory={handleClearHistory}
        />
      </div>
    </div>
  );
}
