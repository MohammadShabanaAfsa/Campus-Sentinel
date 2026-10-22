"use client";

import { useEffect, useState } from "react";
import { Sidebar } from "@/components/dashboard/Sidebar";
import { Header } from "@/components/dashboard/Header";
import { Bot, Activity, RefreshCw, CheckCircle2, XCircle, Clock } from "lucide-react";
import { cn } from "@/lib/utils";
import { useRealtimeEvents } from "@/hooks/useRealtimeEvents";
import { analyticsApi } from "@/lib/api";

interface AgentStatus {
  name: string;
  description: string;
  input_channel: string;
  output_channel: string;
  status: "running" | "idle" | "error" | "stopped";
  messages_processed?: number;
  last_event?: string;
  uptime_secs?: number;
}

const AGENT_META: Record<string, { color: string; icon: string; detail: string }> = {
  "VisionAgent":     { color: "text-blue-400",   icon: "👁️",  detail: "Processes raw frames → object detections" },
  "BehaviorAgent":   { color: "text-amber-400",  icon: "🧠",  detail: "Detects loitering, crowds, zone violations" },
  "PredictionAgent": { color: "text-purple-400", icon: "🔮",  detail: "RF/LSTM threat probability scoring" },
  "DecisionAgent":   { color: "text-red-400",    icon: "⚖️",  detail: "Routes threats → alert priority queue" },
  "ResponseAgent":   { color: "text-green-400",  icon: "📣",  detail: "Dispatches alerts, email, WebSocket push" },
};

function AgentCard({ agent }: { agent: AgentStatus }) {
  const meta = AGENT_META[agent.name] ?? { color: "text-gray-400", icon: "🤖", detail: "" };
  const isRunning = agent.status === "running";

  return (
    <div className={cn(
      "bg-[#1a1f2e] border rounded-xl p-5 transition-all",
      isRunning ? "border-[#2a3042] shadow-lg" : "border-red-900/50 opacity-75"
    )}>
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-3">
          <div className="text-2xl">{meta.icon}</div>
          <div>
            <h3 className={cn("font-semibold text-sm", meta.color)}>{agent.name}</h3>
            <p className="text-xs text-gray-500 mt-0.5">{meta.detail}</p>
          </div>
        </div>
        <div className="flex items-center gap-1.5">
          <div className={cn("w-2 h-2 rounded-full", isRunning ? "bg-green-400 animate-pulse" : "bg-red-500")} />
          <span className={cn("text-xs capitalize", isRunning ? "text-green-400" : "text-red-400")}>
            {agent.status}
          </span>
        </div>
      </div>

      <div className="space-y-2 text-xs">
        <div className="flex items-center justify-between text-gray-500">
          <span>Input</span>
          <code className="text-blue-400 bg-blue-900/10 px-1.5 py-0.5 rounded">{agent.input_channel}</code>
        </div>
        <div className="flex items-center justify-between text-gray-500">
          <span>Output</span>
          <code className="text-green-400 bg-green-900/10 px-1.5 py-0.5 rounded">{agent.output_channel}</code>
        </div>
        {agent.messages_processed !== undefined && (
          <div className="flex items-center justify-between text-gray-500">
            <span>Messages</span>
            <span className="text-gray-300">{agent.messages_processed.toLocaleString()}</span>
          </div>
        )}
        {agent.uptime_secs !== undefined && (
          <div className="flex items-center justify-between text-gray-500">
            <span>Uptime</span>
            <span className="text-gray-300">{formatUptime(agent.uptime_secs)}</span>
          </div>
        )}
        {agent.last_event && (
          <div className="flex items-center gap-1 text-gray-600 pt-1 border-t border-[#2a3042]">
            <Clock className="w-3 h-3" />
            <span className="truncate">{agent.last_event}</span>
          </div>
        )}
      </div>
    </div>
  );
}

function formatUptime(secs: number): string {
  if (secs < 60) return `${secs}s`;
  if (secs < 3600) return `${Math.floor(secs / 60)}m`;
  return `${Math.floor(secs / 3600)}h ${Math.floor((secs % 3600) / 60)}m`;
}

const STATIC_AGENTS: AgentStatus[] = [
  { name: "VisionAgent",     input_channel: "raw_frames",  output_channel: "detections", status: "running", description: "" },
  { name: "BehaviorAgent",   input_channel: "tracks",      output_channel: "behaviors",  status: "running", description: "" },
  { name: "PredictionAgent", input_channel: "behaviors",   output_channel: "threats",    status: "running", description: "" },
  { name: "DecisionAgent",   input_channel: "threats",     output_channel: "decisions",  status: "running", description: "" },
  { name: "ResponseAgent",   input_channel: "decisions",   output_channel: "responses",  status: "running", description: "" },
];

export default function AgentsPage() {
  useRealtimeEvents();
  const [agents, setAgents] = useState<AgentStatus[]>(STATIC_AGENTS);
  const [abdStatus, setAbdStatus] = useState<string>("idle");
  const [abdMessage, setAbdMessage] = useState<string>("");
  const [celeryStats, setCeleryStats] = useState<Record<string, unknown>>({});
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const loadStats = async () => {
      try {
        const res = await analyticsApi.summary(1);
        setCeleryStats(res.data);
      } catch {
        // swallow — stats are non-critical
      }
    };
    loadStats();
    const t = setInterval(loadStats, 30000);
    return () => clearInterval(t);
  }, []);

  const triggerABD = async () => {
    setLoading(true);
    setAbdStatus("running");
    setAbdMessage("Triggering ABD model retraining...");
    try {
      const res = await fetch("/api/v1/admin/train-abd", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${localStorage.getItem("access_token")}`,
        },
      });
      const data = await res.json();
      setAbdStatus("done");
      setAbdMessage(data.message ?? "Training queued successfully");
    } catch (e) {
      setAbdStatus("error");
      setAbdMessage("Failed to trigger training");
    } finally {
      setLoading(false);
    }
  };

  const runningCount = agents.filter((a) => a.status === "running").length;

  return (
    <div className="flex h-screen bg-[#0a0e1a] text-white overflow-hidden">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header />
        <main className="flex-1 overflow-auto p-4 space-y-4">
          {/* Header bar */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Bot className="w-5 h-5 text-blue-400" />
              <h2 className="text-lg font-semibold">AI Agents</h2>
              <span className="text-xs px-2 py-0.5 bg-green-900/20 text-green-400 border border-green-800 rounded-full">
                {runningCount}/{agents.length} Running
              </span>
            </div>
          </div>

          {/* Pipeline overview */}
          <div className="bg-[#1a1f2e] border border-[#2a3042] rounded-xl p-4">
            <h3 className="text-xs text-gray-500 mb-3 uppercase tracking-wide">Multi-Agent Pipeline</h3>
            <div className="flex items-center gap-1 overflow-x-auto pb-2">
              {STATIC_AGENTS.map((agent, i) => (
                <div key={agent.name} className="flex items-center gap-1 flex-shrink-0">
                  <div className="flex flex-col items-center">
                    <div className="text-lg mb-1">{AGENT_META[agent.name]?.icon}</div>
                    <div className={cn("text-xs font-medium", AGENT_META[agent.name]?.color)}>
                      {agent.name.replace("Agent", "")}
                    </div>
                    <div className="w-2 h-2 rounded-full bg-green-400 mt-1 animate-pulse" />
                  </div>
                  {i < STATIC_AGENTS.length - 1 && (
                    <div className="flex-shrink-0 mx-2 text-gray-600">→</div>
                  )}
                </div>
              ))}
            </div>
            <p className="text-xs text-gray-600 mt-2">
              Data flows: Camera frames → Vision → Behavior → Prediction → Decision → Response (alert dispatch)
            </p>
          </div>

          {/* Agent cards */}
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {agents.map((agent) => (
              <AgentCard key={agent.name} agent={agent} />
            ))}
          </div>

          {/* ABD Training Control */}
          <div className="bg-[#1a1f2e] border border-[#2a3042] rounded-xl p-5">
            <div className="flex items-start justify-between mb-3">
              <div>
                <h3 className="text-sm font-semibold text-white">Adaptive Behavioral DNA (ABD)</h3>
                <p className="text-xs text-gray-500 mt-1">
                  IsolationForest models trained per camera × hour × day-of-week.
                  Auto-trains nightly via Celery Beat.
                </p>
              </div>
              <button
                onClick={triggerABD}
                disabled={loading}
                className="flex items-center gap-2 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-xs rounded-lg transition-colors"
              >
                <RefreshCw className={cn("w-3 h-3", loading && "animate-spin")} />
                {loading ? "Training..." : "Retrain Now"}
              </button>
            </div>

            {abdMessage && (
              <div className={cn(
                "flex items-center gap-2 text-xs px-3 py-2 rounded-lg border",
                abdStatus === "done"  ? "bg-green-900/20 border-green-800 text-green-300" :
                abdStatus === "error" ? "bg-red-900/20 border-red-800 text-red-300" :
                                        "bg-blue-900/20 border-blue-800 text-blue-300"
              )}>
                {abdStatus === "done"  ? <CheckCircle2 className="w-3 h-3" /> :
                 abdStatus === "error" ? <XCircle className="w-3 h-3" /> :
                                         <Activity className="w-3 h-3" />}
                {abdMessage}
              </div>
            )}

            <div className="mt-3 grid grid-cols-3 gap-3 text-center">
              <div className="bg-[#0d1117] rounded-lg p-3">
                <p className="text-lg font-bold text-blue-400">168</p>
                <p className="text-xs text-gray-500">Models/Camera</p>
              </div>
              <div className="bg-[#0d1117] rounded-lg p-3">
                <p className="text-lg font-bold text-purple-400">30d</p>
                <p className="text-xs text-gray-500">Training Window</p>
              </div>
              <div className="bg-[#0d1117] rounded-lg p-3">
                <p className="text-lg font-bold text-green-400">5%</p>
                <p className="text-xs text-gray-500">Contamination Rate</p>
              </div>
            </div>
          </div>

          {/* Redis pub/sub channels */}
          <div className="bg-[#1a1f2e] border border-[#2a3042] rounded-xl p-5">
            <h3 className="text-sm font-semibold text-white mb-3">Redis Pub/Sub Channels</h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
              {["raw_frames", "detections", "tracks", "behaviors", "threats", "decisions", "responses", "alerts_channel", "csi_updates"].map((ch) => (
                <div key={ch} className="flex items-center gap-1.5 bg-[#0d1117] rounded-lg px-2 py-1.5">
                  <div className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse flex-shrink-0" />
                  <code className="text-xs text-gray-400 truncate">{ch}</code>
                </div>
              ))}
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
