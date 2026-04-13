import { AlertCircle, CheckCircle, Clock, Cpu, Loader2, XCircle } from "lucide-react";
import { AllModelStatus, ModelLoadStatus, ModelStatus } from "../types";

interface Props {
  status: AllModelStatus | null;
}

function statusColor(s: ModelLoadStatus): string {
  switch (s) {
    case "idle":
      return "text-accent-green";
    case "running":
      return "text-accent-blue";
    case "loading":
      return "text-accent-yellow";
    case "error":
      return "text-accent-red";
    default:
      return "text-gray-500";
  }
}

function statusDot(s: ModelLoadStatus): string {
  switch (s) {
    case "idle":
      return "bg-accent-green";
    case "running":
      return "bg-accent-blue animate-pulse";
    case "loading":
      return "bg-accent-yellow animate-pulse";
    case "error":
      return "bg-accent-red";
    default:
      return "bg-gray-600";
  }
}

function StatusIcon({ s }: { s: ModelLoadStatus }) {
  const cls = `w-3.5 h-3.5 ${statusColor(s)}`;
  switch (s) {
    case "idle":
      return <CheckCircle className={cls} />;
    case "running":
      return <Loader2 className={`${cls} animate-spin`} />;
    case "loading":
      return <Clock className={`${cls} animate-pulse`} />;
    case "error":
      return <XCircle className={cls} />;
    default:
      return <AlertCircle className={cls} />;
  }
}

function ModelCard({ m }: { m: ModelStatus }) {
  return (
    <div className="p-3 rounded-md bg-surface border border-surface-border">
      <div className="flex items-center gap-2 mb-1.5">
        <span className={`status-dot ${statusDot(m.status)}`} />
        <span className="text-sm font-medium text-gray-200 flex-1 truncate">
          {m.name}
        </span>
        <StatusIcon s={m.status} />
      </div>

      <div className="space-y-0.5 pl-4">
        <div className="flex items-center gap-1.5">
          <p className="text-xs text-gray-500 truncate flex-1" title={m.model}>
            {m.model || "—"}
          </p>
          {m.device && (
            <span
              className={`text-[10px] font-mono px-1 py-0.5 rounded shrink-0 ${
                m.device.startsWith("cuda")
                  ? "bg-green-900/50 text-green-400"
                  : "bg-gray-800 text-gray-500"
              }`}
            >
              {m.device.startsWith("cuda") ? "GPU" : "CPU"}
            </span>
          )}
        </div>
        <div className="flex items-center justify-between">
          <span className={`text-xs font-mono ${statusColor(m.status)}`}>
            {m.status}
          </span>
          {m.latency_ms != null && (
            <span className="text-xs font-mono text-gray-600">
              {m.latency_ms.toFixed(0)}ms
            </span>
          )}
        </div>
        {m.error && (
          <p className="text-xs text-accent-red mt-1 break-words">{m.error}</p>
        )}
      </div>
    </div>
  );
}

export function ModelStatusPanel({ status }: Props) {
  return (
    <div className="card p-3 flex flex-col gap-2">
      <div className="flex items-center gap-2 mb-1">
        <Cpu className="w-4 h-4 text-gray-500" />
        <span className="label">Models</span>
      </div>

      {status ? (
        <>
          <ModelCard m={status.stt} />
          <ModelCard m={status.llm} />
          <ModelCard m={status.tts} />
        </>
      ) : (
        <p className="text-xs text-gray-600 text-center py-4">Connecting…</p>
      )}
    </div>
  );
}
