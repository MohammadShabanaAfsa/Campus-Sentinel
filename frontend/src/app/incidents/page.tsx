"use client";

import { useCallback, useEffect, useState } from "react";
import { Sidebar } from "@/components/dashboard/Sidebar";
import { Header } from "@/components/dashboard/Header";
import { AlertTriangle, Plus, CheckCircle2, Clock, X, ChevronDown, ChevronUp } from "lucide-react";
import { cn } from "@/lib/utils";
import { formatDistanceToNow } from "date-fns";
import { useRealtimeEvents } from "@/hooks/useRealtimeEvents";

const SEV: Record<string, string> = {
  critical: "text-purple-400 border-purple-700 bg-purple-900/10",
  high:     "text-red-400 border-red-700 bg-red-900/10",
  medium:   "text-amber-400 border-amber-700 bg-amber-900/10",
  low:      "text-green-400 border-green-700 bg-green-900/10",
};
const STATUS_BADGE: Record<string, string> = {
  open:         "bg-red-900/20 text-red-300 border-red-800",
  investigating: "bg-amber-900/20 text-amber-300 border-amber-800",
  resolved:     "bg-green-900/20 text-green-300 border-green-800",
};

type Incident = {
  id: string;
  title: string;
  description?: string;
  incident_type: string;
  severity: string;
  status: string;
  camera_id?: string;
  created_at: string;
  resolved_at?: string;
};

const TYPES = ["unauthorized_access", "fight", "crowd_surge", "fire", "theft", "vandalism", "medical", "other"];

function CreateIncidentModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [form, setForm] = useState({
    title: "", description: "", incident_type: "unauthorized_access", severity: "medium"
  });
  const [loading, setLoading] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      const res = await fetch("/api/v1/incidents/", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${localStorage.getItem("access_token")}`,
        },
        body: JSON.stringify(form),
      });
      if (res.ok) { onCreated(); onClose(); }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="bg-[#1a1f2e] border border-[#2a3042] rounded-2xl w-full max-w-md">
        <div className="flex items-center justify-between p-5 border-b border-[#2a3042]">
          <h2 className="font-semibold text-white">Create Incident</h2>
          <button onClick={onClose}><X className="w-5 h-5 text-gray-400" /></button>
        </div>
        <form onSubmit={submit} className="p-5 space-y-3">
          <div>
            <label className="text-xs text-gray-400 mb-1 block">Title *</label>
            <input value={form.title} onChange={e => setForm(f => ({ ...f, title: e.target.value }))}
              required className="w-full bg-[#0d1117] border border-[#2a3042] rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500" />
          </div>
          <div>
            <label className="text-xs text-gray-400 mb-1 block">Description</label>
            <textarea value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
              rows={3} className="w-full bg-[#0d1117] border border-[#2a3042] rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500 resize-none" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-gray-400 mb-1 block">Type</label>
              <select value={form.incident_type} onChange={e => setForm(f => ({ ...f, incident_type: e.target.value }))}
                className="w-full bg-[#0d1117] border border-[#2a3042] rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500">
                {TYPES.map(t => <option key={t} value={t}>{t.replace(/_/g, " ")}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs text-gray-400 mb-1 block">Severity</label>
              <select value={form.severity} onChange={e => setForm(f => ({ ...f, severity: e.target.value }))}
                className="w-full bg-[#0d1117] border border-[#2a3042] rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500">
                {["low","medium","high","critical"].map(s => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
          </div>
          <div className="flex gap-3 pt-2">
            <button type="button" onClick={onClose}
              className="flex-1 py-2 border border-[#2a3042] text-gray-400 rounded-lg text-sm hover:text-white">
              Cancel
            </button>
            <button type="submit" disabled={loading}
              className="flex-1 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded-lg text-sm font-medium">
              {loading ? "Creating..." : "Create"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function IncidentCard({ incident, onResolve }: { incident: Incident; onResolve: () => void }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className={cn("bg-[#1a1f2e] border rounded-xl overflow-hidden", SEV[incident.severity] || "border-[#2a3042]")}>
      <div className="p-4">
        <div className="flex items-start gap-3">
          <AlertTriangle className="w-4 h-4 mt-0.5 flex-shrink-0 text-gray-400" />
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap mb-1">
              <span className={cn("text-xs px-1.5 py-0.5 rounded border", SEV[incident.severity])}>
                {incident.severity.toUpperCase()}
              </span>
              <span className={cn("text-xs px-1.5 py-0.5 rounded border capitalize", STATUS_BADGE[incident.status] || "")}>
                {incident.status}
              </span>
              <span className="text-xs text-gray-500 capitalize">
                {incident.incident_type.replace(/_/g, " ")}
              </span>
              <span className="text-xs text-gray-600 flex items-center gap-1 ml-auto">
                <Clock className="w-3 h-3" />
                {formatDistanceToNow(new Date(incident.created_at), { addSuffix: true })}
              </span>
            </div>
            <p className="text-sm font-medium text-white">{incident.title}</p>
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            {incident.status === "open" && (
              <button onClick={onResolve}
                className="text-xs px-2 py-1 bg-green-900/30 text-green-300 border border-green-700 rounded hover:bg-green-900/50">
                Resolve
              </button>
            )}
            <button onClick={() => setExpanded(v => !v)} className="text-gray-500 hover:text-white">
              {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
            </button>
          </div>
        </div>

        {expanded && (
          <div className="mt-3 pt-3 border-t border-[#2a3042] space-y-2">
            {incident.description && (
              <p className="text-xs text-gray-400">{incident.description}</p>
            )}
            <div className="flex gap-4 text-xs text-gray-600">
              <span>ID: <span className="text-gray-500 font-mono">{incident.id.split("-")[0]}</span></span>
              {incident.camera_id && <span>Camera: <span className="text-gray-500">{incident.camera_id.split("-")[0]}</span></span>}
              {incident.resolved_at && <span>Resolved: {formatDistanceToNow(new Date(incident.resolved_at), { addSuffix: true })}</span>}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default function IncidentsPage() {
  useRealtimeEvents();
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [status, setStatus] = useState("open");
  const [showCreate, setShowCreate] = useState(false);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = status !== "all" ? `?status=${status}` : "";
      const res = await fetch(`/api/v1/incidents/${params}`, {
        headers: { Authorization: `Bearer ${localStorage.getItem("access_token")}` },
      });
      const data = await res.json();
      setIncidents(Array.isArray(data) ? data : []);
    } finally {
      setLoading(false);
    }
  }, [status]);

  useEffect(() => { load(); }, [load]);

  const handleResolve = async (id: string) => {
    await fetch(`/api/v1/incidents/${id}/resolve`, {
      method: "PATCH",
      headers: { Authorization: `Bearer ${localStorage.getItem("access_token")}` },
    });
    setIncidents(prev => prev.map(i => i.id === id ? { ...i, status: "resolved" } : i));
  };

  const stats = {
    open: incidents.filter(i => i.status === "open").length,
    critical: incidents.filter(i => i.severity === "critical").length,
    resolved: incidents.filter(i => i.status === "resolved").length,
    total: incidents.length,
  };

  return (
    <div className="flex h-screen bg-[#0a0e1a] text-white overflow-hidden">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header />
        <main className="flex-1 overflow-auto p-4 space-y-4">
          {/* KPIs */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {[
              { label: "Open", value: stats.open, color: "text-red-400" },
              { label: "Critical", value: stats.critical, color: "text-purple-400" },
              { label: "Resolved", value: stats.resolved, color: "text-green-400" },
              { label: "Total", value: stats.total, color: "text-gray-300" },
            ].map(({ label, value, color }) => (
              <div key={label} className="bg-[#1a1f2e] border border-[#2a3042] rounded-xl p-4 text-center">
                <p className={cn("text-2xl font-bold", color)}>{value}</p>
                <p className="text-xs text-gray-500 mt-1">{label}</p>
              </div>
            ))}
          </div>

          {/* Toolbar */}
          <div className="flex items-center gap-2">
            <div className="flex gap-1">
              {["open", "investigating", "resolved", "all"].map(s => (
                <button key={s} onClick={() => setStatus(s)}
                  className={cn("px-3 py-1.5 rounded-lg text-xs capitalize border transition-colors",
                    status === s ? "bg-blue-600 border-blue-500 text-white" : "bg-[#1a1f2e] border-[#2a3042] text-gray-400 hover:text-white"
                  )}>
                  {s}
                </button>
              ))}
            </div>
            <button onClick={() => setShowCreate(true)}
              className="ml-auto flex items-center gap-2 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white text-xs rounded-lg">
              <Plus className="w-3 h-3" /> New Incident
            </button>
          </div>

          {/* List */}
          {loading ? (
            <div className="flex items-center justify-center h-40">
              <div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
            </div>
          ) : incidents.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-40 text-gray-500">
              <CheckCircle2 className="w-10 h-10 mb-2 text-green-500" />
              <p className="text-sm">No {status !== "all" ? status : ""} incidents</p>
            </div>
          ) : (
            <div className="space-y-3">
              {incidents.map(i => (
                <IncidentCard key={i.id} incident={i} onResolve={() => handleResolve(i.id)} />
              ))}
            </div>
          )}
        </main>
      </div>

      {showCreate && (
        <CreateIncidentModal onClose={() => setShowCreate(false)} onCreated={load} />
      )}
    </div>
  );
}
