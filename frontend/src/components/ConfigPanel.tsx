import { AudioLines, Brain, Lightbulb, LightbulbOff, RotateCcw, Settings2, Volume2, VolumeX } from "lucide-react";
import { AudioMode, Config } from "../types";

interface Props {
  config: Config;
  onChange: (c: Partial<Config>) => void;
  onClearHistory: () => void;
}

function Slider({
  label,
  value,
  min,
  max,
  step,
  unit,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  unit: string;
  onChange: (v: number) => void;
}) {
  return (
    <div className="flex items-center gap-3">
      <span className="text-xs text-gray-400 w-28 flex-shrink-0">{label}</span>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        className="flex-1 accent-accent-blue h-1"
      />
      <span className="text-xs font-mono text-gray-300 w-16 text-right">
        {value}
        {unit}
      </span>
    </div>
  );
}

const MODE_OPTIONS: { value: AudioMode; label: string; desc: string; icon: React.ElementType }[] = [
  {
    value: "whisper",
    label: "Whisper STT",
    desc: "Audio → Whisper → text → Gemma 4",
    icon: AudioLines,
  },
  {
    value: "direct",
    label: "Direct Audio",
    desc: "Audio → Gemma 4 natively (E2B/E4B)",
    icon: Brain,
  },
];

export function ConfigPanel({ config, onChange, onClearHistory }: Props) {
  return (
    <div className="card px-4 py-2 flex items-center gap-6 flex-wrap">
      <div className="flex items-center gap-2 flex-shrink-0">
        <Settings2 className="w-4 h-4 text-gray-500" />
        <span className="label">Config</span>
      </div>

      {/* Audio mode toggle */}
      <div className="flex items-center gap-1 flex-shrink-0 bg-surface rounded-md p-0.5 border border-surface-border">
        {MODE_OPTIONS.map(({ value, label, desc, icon: Icon }) => {
          const active = config.audioMode === value;
          return (
            <button
              key={value}
              title={desc}
              onClick={() => onChange({ audioMode: value })}
              className={`flex items-center gap-1.5 px-3 py-1 rounded text-xs font-medium transition-all ${
                active
                  ? "bg-accent-blue/20 text-accent-blue border border-accent-blue/30"
                  : "text-gray-500 hover:text-gray-300"
              }`}
            >
              <Icon className="w-3.5 h-3.5" />
              {label}
            </button>
          );
        })}
      </div>

      <div className="flex-1 flex items-center gap-6 flex-wrap min-w-0">
        <div className="flex-1 min-w-48">
          <Slider
            label="Frame interval"
            value={config.frameInterval}
            min={0.5}
            max={5}
            step={0.5}
            unit="s"
            onChange={(v) => onChange({ frameInterval: v })}
          />
        </div>

        <div className="flex-1 min-w-48">
          <Slider
            label="VAD silence"
            value={config.vadSilence}
            min={0.3}
            max={3.0}
            step={0.1}
            unit="s"
            onChange={(v) => onChange({ vadSilence: v })}
          />
        </div>
      </div>

      {/* Thinking toggle */}
      <button
        onClick={() => onChange({ thinkingEnabled: !config.thinkingEnabled })}
        title={config.thinkingEnabled ? "Thinking enabled — model reasons step-by-step (slower)" : "Thinking disabled — faster direct answers"}
        className={`flex items-center gap-1.5 px-3 py-1 rounded text-xs font-medium border transition-all flex-shrink-0 ${
          config.thinkingEnabled
            ? "bg-accent-yellow/20 text-accent-yellow border-accent-yellow/30 hover:bg-accent-yellow/30"
            : "bg-surface text-gray-500 border-surface-border hover:text-gray-300"
        }`}
      >
        {config.thinkingEnabled ? (
          <><Lightbulb className="w-3.5 h-3.5" /> Thinking on</>
        ) : (
          <><LightbulbOff className="w-3.5 h-3.5" /> Thinking off</>
        )}
      </button>

      {/* TTS toggle */}
      <button
        onClick={() => onChange({ ttsEnabled: !config.ttsEnabled })}
        title={config.ttsEnabled ? "TTS enabled — click to disable" : "TTS disabled — click to enable"}
        className={`flex items-center gap-1.5 px-3 py-1 rounded text-xs font-medium border transition-all flex-shrink-0 ${
          config.ttsEnabled
            ? "bg-accent-green/20 text-accent-green border-accent-green/30 hover:bg-accent-green/30"
            : "bg-surface text-gray-500 border-surface-border hover:text-gray-300"
        }`}
      >
        {config.ttsEnabled ? (
          <><Volume2 className="w-3.5 h-3.5" /> TTS on</>
        ) : (
          <><VolumeX className="w-3.5 h-3.5" /> TTS off</>
        )}
      </button>

      <button
        onClick={onClearHistory}
        className="btn-danger flex items-center gap-1.5 flex-shrink-0"
        title="Clear LLM conversation history"
      >
        <RotateCcw className="w-3.5 h-3.5" />
        Clear history
      </button>
    </div>
  );
}
