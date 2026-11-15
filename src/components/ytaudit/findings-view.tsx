"use client";

import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api } from "@/lib/api";
import type { Finding, ResearchSession } from "@/lib/types";
import { Disclaimer, EmptyState, LabelBadge } from "./bits";
import { Download } from "lucide-react";

export function FindingsView() {
  const [sessions, setSessions] = useState<ResearchSession[]>([]);
  const [sessionId, setSessionId] = useState<string>("");
  const [findings, setFindings] = useState<Finding[]>([]);
  const [busy, setBusy] = useState(false);
  const [reportBusy, setReportBusy] = useState(false);
  const [reportError, setReportError] = useState<string | null>(null);

  useEffect(() => {
    api.get<{ sessions: ResearchSession[] }>("/research/sessions").then((d) => {
      const done = d.sessions.filter((s) => s.status === "completed" || s.status === "partial");
      setSessions(done);
      if (done.length && !sessionId) setSessionId(done[0].id);
    }).catch(() => {});
     
  }, []);

  const load = useCallback(async () => {
    if (!sessionId) return;
    const d = await api.get<{ findings: Finding[] }>(`/findings/${sessionId}`);
    setFindings(d.findings);
  }, [sessionId]);

  useEffect(() => { load(); }, [load]);

  async function regenerate() {
    setBusy(true);
    try {
      await api.post(`/findings/${sessionId}/run`);
      await load();
    } finally {
      setBusy(false);
    }
  }

  async function downloadReport() {
    if (!sessionId) return;
    setReportBusy(true);
    setReportError(null);
    try {
      const { blob, filename } = await api.postBlob(`/findings/${sessionId}/report.pdf`);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setReportError(err instanceof Error ? err.message : "PDF report failed");
    } finally {
      setReportBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-lg font-bold">Findings &amp; Recommendations</h1>
          <p className="text-xs text-muted-foreground">Evidence-based findings with methodology, confidence and limitations</p>
        </div>
        <div className="flex gap-2">
          <Select value={sessionId} onValueChange={setSessionId}>
            <SelectTrigger className="w-60"><SelectValue placeholder="Select session" /></SelectTrigger>
            <SelectContent>
              {sessions.map((s) => <SelectItem key={s.id} value={s.id}>{s.title.slice(0, 40)}</SelectItem>)}
            </SelectContent>
          </Select>
          <Button size="sm" variant="outline" onClick={regenerate} disabled={!sessionId || busy}>
            {busy ? "Building…" : "Rebuild findings"}
          </Button>
          <Button size="sm" className="bg-indigo-600 hover:bg-indigo-700" onClick={downloadReport} disabled={!sessionId || reportBusy}>
            <Download className="mr-1 h-4 w-4" /> {reportBusy ? "Preparing…" : "PDF report"}
          </Button>
        </div>
      </div>
      {reportError ? <p className="text-xs text-red-600">{reportError}</p> : null}

      {!sessionId ? (
        <EmptyState title="No completed research" hint="Findings are generated from collected data only — run a research session first." />
      ) : findings.length === 0 ? (
        <EmptyState title="No findings yet" hint="Click “Rebuild findings” to convert this session's analytics into evidence-based recommendations." />
      ) : (
        <div className="space-y-3">
          {findings.map((f) => (
            <Card key={f.id}>
              <CardHeader className="pb-2">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <CardTitle className="text-sm">{f.title}</CardTitle>
                  <div className="flex items-center gap-2">
                    <span className="rounded bg-stone-100 px-1.5 py-0.5 text-[10px] text-stone-600">{f.category}</span>
                    <LabelBadge label={f.data_label} />
                    <span className="text-[10px] text-muted-foreground">confidence {f.confidence.toFixed(2)}</span>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-2 text-xs">
                <p>{f.description}</p>
                {Object.keys(f.metrics).length ? (
                  <div className="flex flex-wrap gap-1.5">
                    {Object.entries(f.metrics).filter(([k]) => !["evidence"].includes(k)).slice(0, 8).map(([k, v]) => (
                      <span key={k} className="rounded bg-stone-100 px-1.5 py-0.5 font-mono text-[10px] text-stone-700">
                        {k}: {typeof v === "object" ? JSON.stringify(v).slice(0, 40) : String(v)}
                      </span>
                    ))}
                  </div>
                ) : null}
                {f.evidence.length ? (
                  <div className="space-y-1">
                    <p className="text-[11px] font-semibold text-muted-foreground">Evidence</p>
                    {f.evidence.slice(0, 3).map((e, i) => (
                      <div key={i} className="rounded bg-stone-50 p-2 text-[11px]">
                        {typeof e["text"] === "string" ? `“${String(e["text"]).slice(0, 180)}”` : ""}
                        {e["video"] ? <span className="text-muted-foreground"> — {String(e["video"])}</span> : null}
                        {typeof e["url"] === "string" ? (
                          <a className="ml-1 text-indigo-700 hover:underline" href={String(e["url"])} target="_blank" rel="noreferrer">open</a>
                        ) : null}
                      </div>
                    ))}
                  </div>
                ) : null}
                {f.recommended_action ? (
                  <p className="rounded-md border border-indigo-200 bg-indigo-50 px-3 py-2 text-indigo-900">
                    <b>Recommended action:</b> {f.recommended_action}
                  </p>
                ) : null}
                <p className="text-[11px] text-muted-foreground"><b>Methodology:</b> {f.methodology}</p>
                <p className="text-[11px] text-muted-foreground"><b>Limitations:</b> {f.limitations}</p>
                {f.period_start ? (
                  <p className="text-[10px] text-muted-foreground">Collection period: {new Date(f.period_start).toLocaleDateString()} — {f.period_end ? new Date(f.period_end).toLocaleDateString() : ""}</p>
                ) : null}
              </CardContent>
            </Card>
          ))}
          <Disclaimer>Every finding traces to collected data and computed metrics. Findings never present estimated or inferred results as live facts.</Disclaimer>
        </div>
      )}
    </div>
  );
}
