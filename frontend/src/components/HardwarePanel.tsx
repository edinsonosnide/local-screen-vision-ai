import { Activity, AlertTriangle, Zap } from "lucide-react";
import { HardwareInfo } from "../types";

interface Props {
  hw: HardwareInfo | null;
}

function Bar({ pct, color }: { pct: number; color: string }) {
  return (
    <div className="h-1.5 w-full bg-surface-border rounded-full overflow-hidden">
      <div
        className={`h-full rounded-full transition-all duration-500 ${color}`}
        style={{ width: `${Math.min(100, pct)}%` }}
      />
    </div>
  );
}

function barColor(pct: number): string {
  if (pct > 85) return "bg-accent-red";
  if (pct > 65) return "bg-accent-yellow";
  return "bg-accent-green";
}

export function HardwarePanel({ hw }: Props) {
  return (
    <div className="card p-3 flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <Activity className="w-4 h-4 text-gray-500" />
        <span className="label">Hardware</span>
        {hw && !hw.using_gpu && (
          <span className="ml-auto flex items-center gap-1 text-accent-yellow text-xs">
            <AlertTriangle className="w-3 h-3" />
            CPU only
          </span>
        )}
      </div>

      {hw ? (
        <div className="space-y-3">
          {/* CPU */}
          <div>
            <div className="flex justify-between text-xs mb-1">
              <span className="text-gray-400">CPU</span>
              <span className="font-mono text-gray-300">{hw.cpu_percent.toFixed(0)}%</span>
            </div>
            <Bar pct={hw.cpu_percent} color={barColor(hw.cpu_percent)} />
          </div>

          {/* RAM */}
          <div>
            <div className="flex justify-between text-xs mb-1">
              <span className="text-gray-400">RAM</span>
              <span className="font-mono text-gray-300">
                {hw.ram_used_gb.toFixed(1)} / {hw.ram_total_gb.toFixed(1)} GB
              </span>
            </div>
            <Bar pct={hw.ram_percent} color={barColor(hw.ram_percent)} />
          </div>

          {/* GPU */}
          {hw.gpu ? (
            <>
              <div>
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-gray-400 truncate flex items-center gap-1">
                    <Zap className="w-3 h-3 text-accent-blue" />
                    {hw.gpu.name}
                  </span>
                  <span className="font-mono text-gray-300 ml-2">
                    {hw.gpu.utilization}%
                  </span>
                </div>
                <Bar pct={hw.gpu.utilization} color="bg-accent-blue" />
              </div>
              <div>
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-gray-400">VRAM</span>
                  <span className="font-mono text-gray-300">
                    {hw.gpu.mem_used_gb.toFixed(1)} / {hw.gpu.mem_total_gb.toFixed(1)} GB
                  </span>
                </div>
                <Bar
                  pct={(hw.gpu.mem_used_gb / hw.gpu.mem_total_gb) * 100}
                  color={barColor((hw.gpu.mem_used_gb / hw.gpu.mem_total_gb) * 100)}
                />
              </div>
            </>
          ) : (
            <p className="text-xs text-gray-600 italic">No GPU detected</p>
          )}
        </div>
      ) : (
        <p className="text-xs text-gray-600 text-center py-2">Connecting…</p>
      )}
    </div>
  );
}
