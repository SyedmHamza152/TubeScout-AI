"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api, loadWorkspace } from "@/lib/api";
import type { Analytics, AspectRow, QuotaStatus, ResearchSession, TopicRow, WorkspaceInfo } from "@/lib/types";
import { Disclaimer, EmptyState, LabelBadge, SentimentBadge, StatCard } from "./bits";
import { Bot, Search, TrendingUp, Users } from "lucide-react";

interface Dash {
  sessions: ResearchSession[];
  quota: QuotaStatus;
  ytConfigured: boolean;
}

export function DashboardView({ onNavigate }: { onNavigate: (view: string) => void }) {
  const [dash, setDash] = useState<Dash | null>(null);
  const [workspace, setWorkspace] = useState<WorkspaceInfo | null>(null);
  const [latest, setLatest] = useState<{ sentiment?: Analytics["summary"]["sentiment_overall"]; title?: string; id?: string; aspects?: AspectRow[]; topics?: TopicRow[] } | null>(null);

  useEffect(() => {
    setWorkspace(loadWorkspace());
    Promise.all([
      api.get<{ sessions: ResearchSession[] }>("/research/sessions"),
      api.get<QuotaStatus>("/research/quota"),
      api.get<{ configured: boolean }>("/integrations/youtube/status").catch(() => ({ configured: false })),
    ]).then(([s, q, yt]) => {
      setDash({ sessions: s.sessions, quota: q, ytConfigured: Boolean(yt.configured) });
      const done = s.sessions.find((x) => x.status === "completed" || x.status === "partial");
      if (done) {
        api.get<Analytics>(`/research/sessions/${done.id}/analytics`)
          .then((a) => setLatest({ id: done.id, title: done.title, sentiment: a.summary?.sentiment_overall, aspects: a.aspects?.aspects?.slice(0, 3), topics: a.topics?.slice(0, 3) }))
          .catch(() => setLatest({ id: done.id, title: done.title }));
      }
    }).catch(() => setDash(null));
  }, []);

  if (!dash) return <EmptyState title="Connecting to the backend…" hint="The API server starts automatically on first use." />;

  const active = dash.sessions.filter((s) => s.status === "collecting" || s.status === "processing" || s.status === "analyzing" || s.status === "queued");
  const completed = dash.sessions.filter((s) => s.status === "completed" || s.status === "partial");
  const totals = dash.sessions.reduce((acc, s) => {
    const st = s.stats || {};
    acc.videos += st.videos_found || 0;
    acc.comments += st.comments_stored || 0;
    acc.quota += st.quota_spent || 0;
    return acc;
  }, { videos: 0, comments: 0, quota: 0 });
  const failed = dash.sessions.filter((s) => s.status === "failed").length;
  const endpoints = Object.entries(dash.quota.by_endpoint || {}).sort((a, b) => b[1] - a[1]).slice(0, 6);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-bold">Dashboard</h1>
        <p className="text-xs text-muted-foreground">
          Workspace overview{workspace ? ` — ${workspace.name} · ${workspace.market} · ${workspace.currency}` : ""} — all figures from live, authorized data only
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard title="YouTube API" value={dash.ytConfigured ? "Connected" : "Not configured"} sub={dash.ytConfigured ? "official v3 · scraping disabled" : "set YOUTUBE_API_KEY in backend/.env"} />
        <StatCard title="Quota today" value={`${dash.quota.used_today}/${dash.quota.limit}`} sub="YouTube API units" />
        <StatCard title="Research sessions" value={dash.sessions.length} sub={`${completed.length} completed · ${active.length} running`} />
        <StatCard
          title="Latest sample"
          value={latest?.sentiment ? `${latest.sentiment.positive_pct}%+ / ${latest.sentiment.negative_pct}%−` : "—"}
          sub={latest?.title ?? "no completed research yet"}
        />
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard title="Videos collected" value={totals.videos} sub="across all sessions" />
        <StatCard title="Comments analyzed" value={totals.comments} sub="stored after dedupe" />
        <StatCard title="Quota spent by runs" value={totals.quota} sub="YouTube API units" />
        <StatCard title="Failed runs" value={failed} sub={`${active.length} currently running`} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm">YouTube quota breakdown</CardTitle></CardHeader>
          <CardContent className="space-y-2 text-xs">
            <div className="flex justify-between"><span className="text-muted-foreground">Used today</span><b>{dash.quota.used_today} / {dash.quota.limit}</b></div>
            <div className="flex justify-between"><span className="text-muted-foreground">Remaining</span><b>{dash.quota.remaining}</b></div>
            <div className="flex flex-wrap gap-1.5 pt-1">
              {endpoints.length ? endpoints.map(([k, v]) => (
                <span key={k} className="rounded-full border px-2 py-0.5 text-[11px]">{k}: {v}</span>
              )) : <span className="text-muted-foreground">No endpoint usage recorded yet.</span>}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2"><CardTitle className="flex items-center gap-2 text-sm"><TrendingUp className="h-4 w-4 text-indigo-600" /> Latest research snapshot</CardTitle></CardHeader>
          <CardContent className="space-y-2 text-xs">
            {latest?.sentiment ? (
              <>
                <p>{latest.sentiment.total} comments · +{latest.sentiment.positive_pct}% / −{latest.sentiment.negative_pct}% / neutral {latest.sentiment.neutral_pct}%</p>
                {latest.aspects?.length ? <p className="text-muted-foreground">Top aspects: {latest.aspects.map((a) => `${a.label} ${a.positive_pct}%+`).join(" · ")}</p> : null}
                {latest.topics?.length ? <p className="text-muted-foreground">Topics: {latest.topics.map((t) => t.label).join(" · ")}</p> : null}
              </>
            ) : <p className="text-muted-foreground">No completed research snapshot yet.</p>}
            {latest?.title ? <p className="text-[11px] text-muted-foreground">{latest.title}</p> : null}
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-sm"><Bot className="h-4 w-4 text-indigo-600" /> Start with the AI Research Agent</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-xs text-muted-foreground">
            <p>Describe your business, market and goal. The agent drafts a structured research plan (keywords, channels, filters, collection caps), you edit and approve it, and only then is data collected through the official API.</p>
            <div className="flex flex-wrap gap-2">
              <Button size="sm" className="bg-indigo-600 hover:bg-indigo-700" onClick={() => onNavigate("agent")}>Open research agent</Button>
              <Button size="sm" variant="outline" onClick={() => onNavigate("product")}><Search className="mr-1 h-3 w-3" /> Product Search</Button>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-sm"><Users className="h-4 w-4 text-indigo-600" /> What you get after research</CardTitle>
          </CardHeader>
          <CardContent className="grid grid-cols-2 gap-2 text-xs text-muted-foreground">
            <span>· Multilingual sentiment (EN / Urdu / Roman Urdu / mixed)</span>
            <span>· Aspect-based sentiment packs</span>
            <span>· Purchase-intent signals</span>
            <span>· Discussion topics</span>
            <span>· Audience segments (clustering)</span>
            <span>· Anomaly detection</span>
            <span>· Competitor comparison</span>
            <span>· Budget optimizer (SLSQP)</span>
          </CardContent>
        </Card>
      </div>

      {dash.sessions.length ? (
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm">Recent research sessions</CardTitle></CardHeader>
          <CardContent className="space-y-2">
            {dash.sessions.slice(0, 8).map((s) => (
              <button key={s.id} onClick={() => onNavigate("research")}
                className="flex w-full flex-wrap items-center justify-between gap-2 rounded-md border px-3 py-2 text-left text-xs hover:border-indigo-400">
                <span className="font-medium">{s.title}</span>
                <span className="flex items-center gap-2 text-muted-foreground">
                  {(s.stats || {})["comments_stored"] ? `${(s.stats || {})["comments_stored"]} comments · ` : ""}
                  {s.status}
                  <LabelBadge label={s.data_label} />
                </span>
              </button>
            ))}
          </CardContent>
        </Card>
      ) : (
        <EmptyState title="No research yet" hint="Your workspace starts empty — no demo data is ever seeded. Run your first research via the agent." />
      )}

      {latest?.sentiment ? (
        <Card>
          <CardHeader className="pb-2"><CardTitle className="flex items-center gap-2 text-sm"><TrendingUp className="h-4 w-4 text-indigo-600" /> Latest sample sentiment</CardTitle></CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            {["positive", "negative", "neutral"].map((k) => (
              <SentimentBadge key={k} sentiment={k} />
            ))}
            <span className="text-xs text-muted-foreground">{latest.sentiment.total} public comments analyzed</span>
          </CardContent>
        </Card>
      ) : null}

      <Disclaimer>
        TubeScout AI is a recommendation system. It never spends advertising money or modifies campaigns, and public
        YouTube statistics are never presented as advertising performance.
      </Disclaimer>
    </div>
  );
}
