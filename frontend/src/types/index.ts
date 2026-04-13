export type ModelLoadStatus = "not_loaded" | "loading" | "idle" | "running" | "error";

export interface ModelStatus {
  name: string;
  status: ModelLoadStatus;
  model: string;
  device?: string;
  error: string | null;
  latency_ms: number | null;
}

export interface AllModelStatus {
  stt: ModelStatus;
  llm: ModelStatus;
  tts: ModelStatus;
}

export interface GPUInfo {
  name: string;
  utilization: number;
  mem_used_gb: number;
  mem_total_gb: number;
}

export interface HardwareInfo {
  cpu_percent: number;
  ram_used_gb: number;
  ram_total_gb: number;
  ram_percent: number;
  gpu: GPUInfo | null;
  using_gpu: boolean;
}

export interface LogEntry {
  id: string;
  level: "info" | "warn" | "error" | "debug";
  message: string;
  timestamp: number;
  latency_ms: number | null;
}

export type PipelineState = "idle" | "transcribing" | "thinking" | "speaking";

export type AudioMode = "whisper" | "direct";

export interface Config {
  frameInterval: number;
  vadSilence: number;
  wsUrl: string;
  audioMode: AudioMode;
  ttsEnabled: boolean;
  thinkingEnabled: boolean;
}

export type WSConnectionState = "disconnected" | "connecting" | "connected" | "error";

export interface ServerMessage {
  type: string;
  data: unknown;
}
