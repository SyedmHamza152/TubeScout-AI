"use client";

import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api } from "@/lib/api";
import type { Anomaly, Cluster, ResearchSession } from "@/lib/types";
import { Disclaimer, EmptyState, LabelBadge, StatCard } from "./bits";

export function AudienceView() {
  const [sessions, setSessions] = useState<ResearchSession[]>([]);
  const [sessionId, setSessionId] = useState<string>("");
  const [clusters, setClusters] = useState<Cluster[]>([]);
  const [anomalies, setAnomalies] = useState<Anomaly[]>([]);
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    api.get<{ sessions: ResearchSession[] }>("/research/sessions").then((d) => {
      const done = d.sessions.filter((s) => s.status === "completed" || s.status === "partial");
      setSessions(done);
      if (done.length && !sessionId) setSessionId(done[0].id);
    }).catch(() => setSessions([]));
     
  }, []);

  const load = useCallback(async () => {
    if (!sessionId) return;
    const c = await api.get<{ clusters: Cluster[] }>(`/audience/clusters/${sessionId}`);
    setClusters(c.clusters);
    const a = await api.get<{ anomalies: Anomaly[] }>(`/audience/anomalies/${sessionId}`);
    setAnomalies(a.anomalies);
  }, [sessionId]);

  useEffect(() => { load(); }, [load]);

  async function runClustering() {
    setBusy("clusters");
    setNote(null);
    try {
      const r = await api.post<{ ok: boolean; reason?: string; k?: number; silhouette?: number; clusters?: number }>(`/audience/clusters/${sessionId}/run`);
      if (!r.ok) setNote(r.reason || "clustering produced no results");
      else setNote(`Found ${r.clusters} segments (k=${r.k}, silhouette ${r.silhouette})`);
      await load();
    } catch (err) {
      setNote(err instanceof Error ? err.message : "clustering failed");
    } finally {
      setBusy(null);
    }
  }

  async function runAnomalies() {
    setBusy("anomalies");
    setNote(null);
    try {
      const r = await api.post<{ anomalies: number }>(`/audience/anomalies/${sessionId}/run`);
      setNote(`Detected ${r.anomalies} unusual patterns`);
      await load();
    } catch (err) {
      setNote(err instanceof Error ? err.message : "anomaly detection failed");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-lg font-bold">Audience Intelligence</h1>
          <p className="text-xs text-muted-foreground">Behavioural segments (K-Means + DBSCAN noise) and unusual-pattern detection</p>
        </div>
        <div className="flex gap-2">
          <Select value={sessionId} onValueChange={setSessionId}>
            <SelectTrigger className="w-60"><SelectValue placeholder="Select session" /></SelectTrigger>
            <SelectContent>
              {sessions.map((s) => <SelectItem key={s.id} value={s.id}>{s.title.slice(0, 40)}</SelectItem>)}
            </SelectContent>
          </Select>
          <Button size="sm" variant="outline" onClick={runClustering} disabled={!sessionId || busy !== null}>
            {busy === "clusters" ? "Running…" : "Run clustering"}
          </Button>
          <Button size="sm" variant="outline" onClick={runAnomalies} disabled={!sessionId || busy !== null}>
            {busy === "anomalies" ? "Running…" : "Run anomaly detection"}
          </Button>
        </div>
      </div>

      {note ? <p className="rounded-md border border-indigo-200 bg-indigo-50 px-3 py-2 text-xs text-indigo-900">{note}</p> : null}

      {!sessionId ? (
        <EmptyState title="No completed research session" hint="Run a research first — segments and anomalies are computed from collected comments." />
      ) : null}

      {clusters.length > 0 ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {clusters.map((c) => {
            const p = c.profile as Record<string, number>;
            return (
              <Card key={c.id}>
                <CardHeader className="pb-2">
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-sm">{c.label}</CardTitle>
                    <LabelBadge label={c.data_label} />
                  </div>
                  <p className="text-[11px] text-muted-foreground">{c.size} commenters · method {c.method} · k={c.k} · silhouette {c.silhouette}</p>
                </CardHeader>
                <CardContent className="grid grid-cols-2 gap-x-3 gap-y-1.5 text-xs">
                  <Metric label="Positive share" value={p["pos_share"]} pct />
                  <Metric label="Negative share" value={p["neg_share"]} pct />
                  <Metric label="Purchase-intent rate" value={p["intent_purchase_intent"]} pct />
                  <Metric label="Price inquiries" value={p["intent_price_inquiry"]} pct />
                  <Metric label="Discount seeking" value={p["intent_discount_seeking"]} pct />
                  <Metric label="Delivery concerns" value={p["intent_delivery_concern"]} pct />
                  <Metric label="Avg sentiment score" value={p["avg_score"]} />
                  <Metric label="Avg comment likes" value={p["avg_likes"]} />
                </CardContent>
              </Card>
            );
          })}
          <Disclaimer>
            Segments are analytical behaviour patterns of public commenters (INFERENCE) — NOT verified
            demographic identities or confirmed customer categories. Commenters are anonymous and may not represent customers.
          </Disclaimer>
        </div>
      ) : sessionId ? (
        <EmptyState title="No clusters yet" hint="Click “Run clustering” — K-Means with silhouette-selected k over author-level behavioural features." />
      ) : null}

      {anomalies.length > 0 ? (
        <div className="space-y-3">
          <h2 className="text-sm font-semibold">Unusual patterns</h2>
          {anomalies.map((a) => (
            <Card key={a.id}>
              <CardContent className="p-4">
                <div className="flex flex-wrap items-center gap-2 text-xs">
                  <LabelBadge label={a.data_label} />
                  <span className="font-semibold">{a.kind.replace("_", " ")}</span>
                  <span className={"rounded px-1.5 py-0.5 " + (a.severity === "high" ? "bg-red-100 text-red-800" : a.severity === "medium" ? "bg-amber-100 text-amber-800" : "bg-stone-100 text-stone-700")}>
                    severity {a.severity}
                  </span>
                  <span className="text-muted-foreground">score {a.score}</span>
                </div>
                <p className="mt-1 text-sm font-medium">{a.entity_title}</p>
                <p className="mt-1 text-xs text-muted-foreground">{a.explanation}</p>
                {a.evidence.length ? (
                  <div className="mt-2 space-y-1">
                    {a.evidence.slice(0, 3).map((e, i) => (
                      <div key={i} className="rounded bg-stone-50 p-2 text-[11px]">
                        {typeof e["text"] === "string" ? `“${String(e["text"]).slice(0, 160)}”` : ""}
                        {typeof e["url"] === "string" ? (
                          <a className="ml-2 text-indigo-700 hover:underline" href={String(e["url"])} target="_blank" rel="noreferrer">open</a>
                        ) : null}
                      </div>
                    ))}
                  </div>
                ) : null}
              </CardContent>
            </Card>
          ))}
        </div>
      ) : sessionId ? (
        <EmptyState title="No anomalies recorded" hint="Run anomaly detection: engagement-rate z-scores, comment-volume spikes, negative-sentiment surges and IsolationForest outliers." />
      ) : null}
    </div>
  );
}

function Metric({ label, value, pct }: { label: string; value: number | undefined; pct?: boolean }) {
  if (value === undefined) return <span />;
  return (
    <div className="flex items-center justify-between">
      <span className="text-muted-foreground">{label}</span>
      <b className="tabular-nums">{pct ? `${Math.round(value * 100)}%` : (Math.round(value * 100) / 100)}</b>
    </div>
  );
}
