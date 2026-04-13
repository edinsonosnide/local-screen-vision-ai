import { ScrollText, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { LogEntry } from "../types";

interface Props {
  logs: LogEntry[];
  onClear: () => void;
}

const LEVEL_STYLES: Record<string, string> = {
  info: "text-accent-blue",
  warn: "text-accent-yellow",
  error: "text-accent-red",
  debug: "text-gray-500",
};

const LEVELS = ["all", "info", "warn", "error", "debug"] as const;
type Filter = (typeof LEVELS)[number];

function fmt(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString("en-US", { hour12: false });
}

export function DebugLog({ logs, onClear }: Props) {
  const [filter, setFilter] = useState<Filter>("all");
  const bottomRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);

  const visible = filter === "all" ? logs : logs.filter((l) => l.level === filter);

  useEffect(() => {
    if (autoScroll) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [visible.length, autoScroll]);

  return (
    <div className="card flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-surface-border flex-shrink-0">
        <ScrollText className="w-4 h-4 text-gray-500" />
        <span className="label">Debug Log</span>
        <div className="flex gap-1 ml-auto">
          {LEVELS.map((l) => (
            <button
              key={l}
              onClick={() => setFilter(l)}
              className={`text-xs px-2 py-0.5 rounded transition-colors ${
                filter === l
                  ? "bg-surface-border text-gray-200"
                  : "text-gray-600 hover:text-gray-400"
              }`}
            >
              {l}
            </button>
          ))}
        </div>
        <button
          onClick={onClear}
          title="Clear logs"
          className="ml-1 p-1 rounded hover:bg-surface-border text-gray-600 hover:text-gray-300 transition-colors"
        >
          <Trash2 className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Auto-scroll toggle */}
      <div className="flex items-center gap-2 px-3 py-1 border-b border-surface-border flex-shrink-0">
        <label className="flex items-center gap-1.5 text-xs text-gray-500 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={autoScroll}
            onChange={(e) => setAutoScroll(e.target.checked)}
            className="accent-accent-blue"
          />
          Auto-scroll
        </label>
        <span className="ml-auto text-xs text-gray-600">{visible.length} entries</span>
      </div>

      {/* Entries */}
      <div className="flex-1 overflow-y-auto font-mono text-xs p-2 space-y-0.5">
        {visible.length === 0 && (
          <p className="text-gray-700 italic text-center py-8">No log entries yet.</p>
        )}
        {visible.map((entry) => (
          <div key={entry.id} className="flex gap-2 hover:bg-surface-hover px-1 py-0.5 rounded">
            <span className="text-gray-600 flex-shrink-0">{fmt(entry.timestamp)}</span>
            <span className={`uppercase flex-shrink-0 w-10 ${LEVEL_STYLES[entry.level] ?? "text-gray-400"}`}>
              {entry.level}
            </span>
            <span className="text-gray-300 break-all">{entry.message}</span>
            {entry.latency_ms != null && (
              <span className="ml-auto text-gray-600 flex-shrink-0">
                {entry.latency_ms.toFixed(0)}ms
              </span>
            )}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
