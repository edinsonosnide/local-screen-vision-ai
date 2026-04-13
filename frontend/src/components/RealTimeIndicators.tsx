import { Mic, Monitor, Volume2, Wand2 } from "lucide-react";
import { PipelineState, WSConnectionState } from "../types";

interface Props {
  wsState: WSConnectionState;
  micActive: boolean;
  screenActive: boolean;
  pipelineState: PipelineState;
}

function Indicator({
  icon: Icon,
  label,
  active,
  color,
  pulse,
}: {
  icon: React.ElementType;
  label: string;
  active: boolean;
  color: string;
  pulse?: boolean;
}) {
  return (
    <div className="flex items-center gap-1.5">
      <div className={`relative flex items-center justify-center`}>
        <Icon
          className={`w-4 h-4 transition-colors ${active ? color : "text-gray-600"}`}
        />
        {active && pulse && (
          <span
            className={`absolute inset-0 rounded-full ${color.replace("text-", "bg-")} opacity-30 speaking-ring`}
          />
        )}
      </div>
      <span
        className={`text-xs font-medium transition-colors ${active ? "text-gray-200" : "text-gray-600"}`}
      >
        {label}
      </span>
    </div>
  );
}

function ConnectionBadge({ state }: { state: WSConnectionState }) {
  const map: Record<WSConnectionState, { label: string; cls: string }> = {
    connected: { label: "Connected", cls: "text-accent-green border-accent-green/30 bg-accent-green/10" },
    connecting: { label: "Connecting…", cls: "text-accent-yellow border-accent-yellow/30 bg-accent-yellow/10" },
    disconnected: { label: "Disconnected", cls: "text-gray-500 border-gray-700 bg-gray-800" },
    error: { label: "Error", cls: "text-accent-red border-accent-red/30 bg-accent-red/10" },
  };
  const { label, cls } = map[state];
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full border font-medium ${cls}`}>
      {label}
    </span>
  );
}

const PIPELINE_LABEL: Record<PipelineState, string> = {
  idle: "Idle",
  transcribing: "Transcribing…",
  thinking: "Thinking…",
  speaking: "Speaking…",
};

export function RealTimeIndicators({ wsState, micActive, screenActive, pipelineState }: Props) {
  return (
    <div className="flex items-center gap-4 flex-wrap">
      <ConnectionBadge state={wsState} />

      <div className="h-4 w-px bg-surface-border" />

      <Indicator
        icon={Mic}
        label="Mic"
        active={micActive}
        color="text-accent-green"
        pulse={micActive}
      />
      <Indicator
        icon={Monitor}
        label="Screen"
        active={screenActive}
        color="text-accent-blue"
      />
      <Indicator
        icon={Wand2}
        label={PIPELINE_LABEL[pipelineState]}
        active={pipelineState !== "idle"}
        color={
          pipelineState === "thinking"
            ? "text-accent-purple"
            : pipelineState === "speaking"
            ? "text-accent-orange"
            : "text-accent-yellow"
        }
        pulse={pipelineState !== "idle"}
      />
      <Indicator
        icon={Volume2}
        label="TTS"
        active={pipelineState === "speaking"}
        color="text-accent-orange"
        pulse={pipelineState === "speaking"}
      />
    </div>
  );
}
