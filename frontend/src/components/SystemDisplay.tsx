import { Bot, Mic, Sparkles } from "lucide-react";
import { PipelineState } from "../types";

interface Props {
  transcript: string;
  llmResponse: string;
  pipelineState: PipelineState;
  ttsPlaying: boolean;
}

function PipelineBadge({ state }: { state: PipelineState }) {
  if (state === "idle") return null;
  const map: Record<Exclude<PipelineState, "idle">, { label: string; cls: string }> = {
    transcribing: { label: "Transcribing…", cls: "text-accent-yellow bg-accent-yellow/10 border-accent-yellow/20" },
    thinking: { label: "Thinking…", cls: "text-accent-purple bg-accent-purple/10 border-accent-purple/20" },
    streaming: { label: "Generating…", cls: "text-accent-purple bg-accent-purple/10 border-accent-purple/20" },
    speaking: { label: "Speaking…", cls: "text-accent-orange bg-accent-orange/10 border-accent-orange/20" },
  };
  const { label, cls } = map[state as Exclude<PipelineState, "idle">];
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full border font-medium animate-pulse ${cls}`}>
      {label}
    </span>
  );
}

export function SystemDisplay({ transcript, llmResponse, pipelineState, ttsPlaying }: Props) {
  return (
    <div className="card flex flex-col gap-0 overflow-hidden h-full">
      {/* Header */}
      <div className="px-4 py-3 border-b border-surface-border flex items-center gap-3">
        <Sparkles className="w-4 h-4 text-accent-blue" />
        <span className="label">System Understanding</span>
        <div className="ml-auto">
          <PipelineBadge state={pipelineState} />
        </div>
      </div>

      <div className="flex flex-col gap-0 flex-1 overflow-auto divide-y divide-surface-border">
        {/* Transcript */}
        <div className="p-4 flex-1">
          <div className="flex items-center gap-2 mb-2">
            <Mic className="w-3.5 h-3.5 text-accent-green" />
            <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
              You said
            </span>
          </div>
          {transcript ? (
            <p className="text-sm text-gray-200 leading-relaxed">{transcript}</p>
          ) : (
            <p className="text-sm text-gray-600 italic">
              {pipelineState === "transcribing"
                ? "Transcribing speech…"
                : "Speak to begin…"}
            </p>
          )}
        </div>

        {/* LLM response */}
        <div className="p-4 flex-1">
          <div className="flex items-center gap-2 mb-2">
            <Bot className="w-3.5 h-3.5 text-accent-purple" />
            <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
              Assistant
            </span>
          </div>
          {llmResponse ? (
            <p className="text-sm text-gray-200 leading-relaxed whitespace-pre-wrap">
              {llmResponse}
              {pipelineState === "streaming" && (
                <span className="inline-block w-0.5 h-[1em] bg-accent-purple ml-0.5 align-middle animate-pulse" />
              )}
            </p>
          ) : (
            <p className="text-sm text-gray-600 italic">
              {pipelineState === "thinking" || pipelineState === "streaming"
                ? "Generating response…"
                : "Response will appear here."}
            </p>
          )}
        </div>

        {/* Pipeline viz */}
        <div className="px-4 py-3">
          <span className="label mb-2 block">Pipeline</span>
          <div className="flex items-center gap-1">
            {(["transcribing", "thinking", "speaking"] as const).map((step, i) => {
              const states: Record<string, { label: string; color: string }> = {
                transcribing: { label: "STT", color: "bg-accent-yellow" },
                thinking: { label: "LLM", color: "bg-accent-purple" },
                speaking: { label: "TTS", color: "bg-accent-orange" },
              };
              const s = states[step];
              const ttsActive = pipelineState === "speaking" || ttsPlaying;
              const isActive =
                pipelineState === step ||
                (step === "thinking" && pipelineState === "streaming") ||
                (step === "speaking" && ttsActive);
              const isDone =
                (step === "transcribing" &&
                  (pipelineState === "thinking" || pipelineState === "streaming" || pipelineState === "speaking" || ttsActive)) ||
                (step === "thinking" && (pipelineState === "speaking" || ttsActive));
              return (
                <div key={step} className="flex items-center gap-1">
                  <div
                    className={`px-2 py-0.5 rounded text-xs font-mono transition-all ${
                      isActive
                        ? `${s.color} text-black font-bold`
                        : isDone
                        ? "bg-surface-border text-gray-400"
                        : "bg-surface text-gray-700 border border-surface-border"
                    }`}
                  >
                    {s.label}
                  </div>
                  {i < 2 && (
                    <span className={`text-xs ${isDone || isActive ? "text-gray-400" : "text-gray-700"}`}>
                      →
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
