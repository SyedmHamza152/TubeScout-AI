"use client";

import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api } from "@/lib/api";
import type { Analytics, CommentRow, ResearchSession, SentimentMix, VideoRow } from "@/lib/types";
import { Disclaimer, EmptyState, LabelBadge, SentimentBadge, StatCard } from "./bits";
import { Bar, BarChart, CartesianGrid, Cell, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip as ChartTooltip, XAxis, YAxis } from "recharts";
import { RefreshCw, Search } from "lucide-react";

const PIE_COLORS = ["#0d9488", "#dc2626", "#a8a29e", "#f59e0b", "#0ea5e9"];

export function ResearchView({ activeSessionId, onSelect }: { activeSessionId: string | null; onSelect: (id: string | null) => void }) {
  const [sessions, setSessions] = useState<ResearchSession[]>([]);
  const [selected, setSelected] = useState<string | null>(activeSessionId);
  const [showNew, setShowNew] = useState(false);

  const load = useCallback(async () => {
    const d = await api.get<{ sessions: ResearchSession[] }>("/research/sessions");
    setSessions(d.sessions);
    if (!selected && d.sessions.length) {
      setSelected(d.sessions[0].id);
    }
     
  }, [selected]);

  useEffect(() => { load(); }, []);
  useEffect(() => { if (activeSessionId) setSelected(activeSessionId); }, [activeSessionId]);
  useEffect(() => {
    const t = setInterval(load, 8000);
    return () => clearInterval(t);
  }, [load]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-lg font-bold">Live YouTube Research</h1>
          <p className="text-xs text-muted-foreground">Official YouTube Data API v3 · snapshots track engagement over time</p>
        </div>
        <div className="flex items-center gap-2">
          <Select value={selected ?? undefined} onValueChange={setSelected}>
            <SelectTrigger className="w-64"><SelectValue placeholder="Select session" /></SelectTrigger>
            <SelectContent>
              {sessions.map((s) => (
                <SelectItem key={s.id} value={s.id}>{s.title.slice(0, 44)} — {s.status}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button size="sm" className="bg-indigo-600 hover:bg-indigo-700" onClick={() => setShowNew((v) => !v)}>
            <Search className="mr-1 h-4 w-4" /> New research
          </Button>
        </div>
      </div>

      {showNew ? <NewResearchForm onCreated={(id) => { setShowNew(false); setSelected(id); load(); }} /> : null}

      {selected ? <SessionDetail sessionId={selected} onChanged={load} /> : (
        <EmptyState title="No research session selected"
          hint="Start a research from the AI Research Agent, or create one with “New research”. Sessions track videos, comments, sentiment, topics and anomalies." />
      )}
    </div>
  );
}

function NewResearchForm({ onCreated }: { onCreated: (id: string) => void }) {
  const [keywords, setKeywords] = useState("");
  const [country, setCountry] = useState("PK");
  const [days, setDays] = useState("90");
  const [intent, setIntent] = useState("campaign");
  const [maxVideos, setMaxVideos] = useState("40");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await api.post<{ id: string }>("/research/sessions", {
        title: keywords.split(",")[0]?.trim() || "YouTube research",
        keywords: keywords.split(",").map((k) => k.trim()).filter(Boolean).slice(0, 8),
        country, published_after_days: parseInt(days), max_videos: parseInt(maxVideos),
        research_intent: intent,
      });
      onCreated(res.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create session");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader className="pb-2"><CardTitle className="text-sm">Keyword-based research (official API only)</CardTitle></CardHeader>
      <CardContent>
        <form onSubmit={submit} className="grid gap-3 md:grid-cols-5">
          <div className="space-y-1.5 md:col-span-5">
            <label className="text-xs font-medium">Keywords (comma-separated, up to 8)</label>
            <Input value={keywords} onChange={(e) => setKeywords(e.target.value)} placeholder="lawn suit review, khaadi collection, winter dress price" required />
          </div>
          <div className="space-y-1.5">
            <label className="text-xs font-medium">Country</label>
            <Input value={country} onChange={(e) => setCountry(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <label className="text-xs font-medium">Intent</label>
            <Select value={intent} onValueChange={setIntent}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="campaign">Campaign</SelectItem>
                <SelectItem value="product">Product</SelectItem>
                <SelectItem value="content">Content</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <label className="text-xs font-medium">Last N days</label>
            <Input type="number" value={days} onChange={(e) => setDays(e.target.value)} min={7} max={3650} />
          </div>
          <div className="space-y-1.5">
            <label className="text-xs font-medium">Max videos</label>
            <Input type="number" value={maxVideos} onChange={(e) => setMaxVideos(e.target.value)} min={5} max={200} />
          </div>
          <Button type="submit" className="bg-indigo-600 hover:bg-indigo-700" disabled={busy}>
            {busy ? "Starting…" : "Start collection"}
          </Button>
          {error ? <p className="text-xs text-red-600 md:col-span-5">{error}</p> : null}
        </form>
      </CardContent>
    </Card>
  );
}

function SessionDetail({ sessionId, onChanged }: { sessionId: string; onChanged: () => void }) {
  const [session, setSession] = useState<ResearchSession | null>(null);
  const [analytics, setAnalytics] = useState<Analytics | null>(null);
  const [videos, setVideos] = useState<VideoRow[]>([]);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    let alive = true;
    async function poll() {
      try {
        const d = await api.get<ResearchSession>(`/research/sessions/${sessionId}`);
        if (alive) setSession(d);
        if (d.status === "completed" || d.status === "partial") {
          const a = await api.get<Analytics>(`/research/sessions/${sessionId}/analytics`);
          if (alive) setAnalytics(a);
          const v = await api.get<{ videos: VideoRow[] }>(`/research/sessions/${sessionId}/videos`);
          if (alive) setVideos(v.videos);
        }
      } catch { /* session may be gone */ }
    }
    poll();
    const t = setInterval(poll, 6000);
    return () => { alive = false; clearInterval(t); };
  }, [sessionId]);

  async function refreshStats() {
    setRefreshing(true);
    try {
      await api.post(`/research/sessions/${sessionId}/refresh`);
      onChanged();
    } finally {
      setRefreshing(false);
    }
  }

  if (!session) return <EmptyState title="Loading session…" />;
  const stats = session.stats || {};
  const s = analytics?.summary?.sentiment_overall;

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <CardTitle className="flex items-center gap-2 text-sm">
                {session.title} <LabelBadge label={session.data_label} />
              </CardTitle>
              <p className="mt-1 text-xs text-muted-foreground">
                {session.mode} · status {session.status}{session.stage ? ` · ${session.stage}` : ""}
                {session.completed_at ? ` · finished ${new Date(session.completed_at).toLocaleString()}` : ""}
              </p>
            </div>
            <Button size="sm" variant="outline" onClick={refreshStats} disabled={refreshing || session.status !== "completed"}>
              <RefreshCw className={"mr-1 h-3 w-3" + (refreshing ? " animate-spin" : "")} /> Refresh stats snapshot
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          {session.status === "completed" || session.status === "partial" ? (
            <>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <StatCard title="Videos found" value={stats.videos_found ?? 0} sub="from approved keywords" />
                <StatCard title="Comments analyzed" value={stats.comments_stored ?? 0} sub={`${stats.comments_duplicate ?? 0} duplicates skipped`} />
                <StatCard title="Quota spent" value={stats.quota_spent ?? 0} sub="YouTube API units (this run)" />
                <StatCard title="Comments-disabled videos" value={stats.comments_disabled_videos ?? 0} sub="handled gracefully" />
              </div>
              {session.error ? <p className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900">{session.error}</p> : null}
            </>
          ) : session.status === "failed" ? (
            <p className="rounded-md border border-red-300 bg-red-50 px-3 py-2 text-xs text-red-900">
              {session.error || "The research run failed."} Fix the cause and click “Refresh stats snapshot” after
              re-running the session from the agent or the New research form.
            </p>
          ) : (
            <div className="space-y-2">
              <Progress value={session.progress} className="h-2" />
              <p className="text-xs text-muted-foreground">{session.stage || "queued"} — polling every 6s…</p>
            </div>
          )}
        </CardContent>
      </Card>

      {analytics ? <AnalyticsTabs analytics={analytics} videos={videos} sessionId={sessionId} /> : null}
    </div>
  );
}

function AnalyticsTabs({ analytics, videos, sessionId }: { analytics: Analytics; videos: VideoRow[]; sessionId: string }) {
  const { summary, aspects, topics } = analytics;
  const so = summary.sentiment_overall;
  const pie = [
    { name: "positive", value: so.positive_pct },
    { name: "negative", value: so.negative_pct },
    { name: "neutral", value: so.neutral_pct },
    { name: "mixed", value: so.mixed_pct },
    { name: "uncertain", value: so.uncertain_pct },
  ].filter((p) => p.value > 0);

  return (
    <Tabs defaultValue="overview">
      <TabsList className="flex-wrap">
        <TabsTrigger value="overview">Overview</TabsTrigger>
        <TabsTrigger value="videos">Videos ({videos.length})</TabsTrigger>
        <TabsTrigger value="comments">Comment explorer</TabsTrigger>
        <TabsTrigger value="aspects">Aspects &amp; topics</TabsTrigger>
      </TabsList>

      <TabsContent value="overview" className="space-y-4">
        <div className="grid gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-sm">Sentiment distribution</CardTitle></CardHeader>
            <CardContent>
              <div className="flex items-center gap-4">
                <div className="h-44 w-44">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie data={pie} dataKey="value" nameKey="name" innerRadius={40} outerRadius={68} paddingAngle={2}>
                        {pie.map((_, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
                      </Pie>
                      <ChartTooltip formatter={(v: number) => `${v}%`} />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
                <div className="space-y-1 text-xs">
                  {pie.map((p, i) => (
                    <div key={p.name} className="flex items-center gap-2">
                      <span className="h-2.5 w-2.5 rounded-sm" style={{ background: PIE_COLORS[i % PIE_COLORS.length] }} />
                      <span className="capitalize">{p.name}</span>
                      <b>{p.value}%</b>
                    </div>
                  ))}
                </div>
              </div>
              <Disclaimer>{summary.sample_disclaimer}</Disclaimer>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-sm">Sentiment trend (comment publish dates)</CardTitle></CardHeader>
            <CardContent className="h-56">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={summary.trend.map((t) => ({ date: t.date.slice(5), negative: t.negative_pct, positive: t.positive_pct }))}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
                  <XAxis dataKey="date" fontSize={10} />
                  <YAxis fontSize={10} unit="%" />
                  <ChartTooltip />
                  <Line type="monotone" dataKey="positive" stroke="#0d9488" dot={false} />
                  <Line type="monotone" dataKey="negative" stroke="#dc2626" dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </div>

        <div className="grid gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-sm">Intent signals (trilingual rule-based)</CardTitle></CardHeader>
            <CardContent className="space-y-2">
              {summary.intents.length === 0 ? <p className="text-xs text-muted-foreground">No strong intent signals in this sample.</p> :
                summary.intents.map((i) => (
                  <div key={i.intent} className="flex items-center justify-between text-xs">
                    <span>{i.label}</span>
                    <div className="flex items-center gap-2">
                      <div className="h-2 w-32 rounded bg-stone-100">
                        <div className="h-2 rounded bg-indigo-600" style={{ width: `${Math.min(100, i.share_pct * 3)}%` }} />
                      </div>
                      <b className="tabular-nums">{i.count}</b>
                    </div>
                  </div>
                ))}
              <Disclaimer>Intent flags are lexical signals on anonymous public comments (INFERENCE) — not verified customer actions.</Disclaimer>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-sm">Language mix</CardTitle></CardHeader>
            <CardContent className="space-y-2">
              {summary.languages.slice(0, 6).map((l) => (
                <div key={l.language} className="flex items-center justify-between text-xs">
                  <SentimentBadge sentiment={l.language} />
                  <span className="tabular-nums text-muted-foreground">{l.total} comments · {l.positive_pct}%+ / {l.negative_pct}%−</span>
                </div>
              ))}
            </CardContent>
          </Card>
        </div>

        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm">Representative comments</CardTitle></CardHeader>
          <CardContent className="grid gap-3 md:grid-cols-2">
            <div className="space-y-2">
              <p className="text-xs font-semibold text-emerald-700">Top positive</p>
              {summary.representative.positive.map((c) => <EvidenceRow key={c.comment_id} text={c.text} likes={c.like_count} url={c.url} />)}
            </div>
            <div className="space-y-2">
              <p className="text-xs font-semibold text-red-700">Top negative</p>
              {summary.representative.negative.map((c) => <EvidenceRow key={c.comment_id} text={c.text} likes={c.like_count} url={c.url} />)}
            </div>
          </CardContent>
        </Card>
      </TabsContent>

      <TabsContent value="videos">
        <Card>
          <CardContent className="p-0">
            <ScrollArea className="max-h-[520px]">
              <table className="w-full text-xs">
                <thead className="sticky top-0 bg-white">
                  <tr className="border-b text-left text-muted-foreground">
                    <th className="p-2">Video</th><th className="p-2">Channel</th><th className="p-2 text-right">Views</th>
                    <th className="p-2 text-right">Likes</th><th className="p-2 text-right">Comments</th>
                    <th className="p-2 text-right">Engagement</th><th className="p-2">Type</th>
                  </tr>
                </thead>
                <tbody>
                  {videos.map((v) => (
                    <tr key={v.video_id} className="border-b hover:bg-stone-50">
                      <td className="max-w-64 truncate p-2"><a href={v.url} target="_blank" rel="noreferrer" className="hover:text-indigo-700 hover:underline">{v.title}</a></td>
                      <td className="p-2 text-muted-foreground">{v.channel_title}</td>
                      <td className="p-2 text-right tabular-nums">{v.views.toLocaleString()}</td>
                      <td className="p-2 text-right tabular-nums">{v.likes.toLocaleString()}</td>
                      <td className="p-2 text-right tabular-nums">{v.comment_count.toLocaleString()}</td>
                      <td className="p-2 text-right tabular-nums">{v.engagement_rate.toFixed(4)}</td>
                      <td className="p-2"><LabelBadge label={v.data_label} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </ScrollArea>
          </CardContent>
        </Card>
        <Disclaimer>Public organic statistics (LIVE DATA) — never advertising spend, paid conversions or competitor ROAS.</Disclaimer>
      </TabsContent>

      <TabsContent value="comments"><CommentExplorer sessionId={sessionId} /></TabsContent>

      <TabsContent value="aspects" className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Aspect-based sentiment</CardTitle>
            <p className="text-[11px] text-muted-foreground">Pack: {aspects.pack_label} (selected by research topic)</p>
          </CardHeader>
          <CardContent>
            {aspects.aspects.length === 0 ? <p className="text-xs text-muted-foreground">No aspect mentions detected yet.</p> : (
              <ResponsiveContainer width="100%" height={Math.max(180, aspects.aspects.length * 34)}>
                <BarChart data={aspects.aspects.slice(0, 8).map((a) => ({ name: a.label, pos: a.positive_pct, neg: a.negative_pct }))} layout="vertical">
                  <XAxis type="number" fontSize={10} unit="%" />
                  <YAxis type="category" dataKey="name" width={110} fontSize={10} />
                  <ChartTooltip />
                  <Bar dataKey="pos" fill="#0d9488" radius={[0, 3, 3, 0]} />
                  <Bar dataKey="neg" fill="#dc2626" radius={[0, 3, 3, 0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm">Discussion topics (clustered)</CardTitle></CardHeader>
          <CardContent className="space-y-2">
            {topics.length === 0 ? <p className="text-xs text-muted-foreground">Topic clustering needs ≥12 embedded comments.</p> :
              topics.map((t) => (
                <div key={t.topic_key} className="rounded-md border p-2">
                  <div className="flex items-center justify-between text-xs font-medium">
                    {t.label} <span className="text-muted-foreground">{t.comment_count} comments · {Math.round(t.share * 100)}%</span>
                  </div>
                  <p className="mt-1 text-[11px] text-muted-foreground">{t.keywords.slice(0, 6).join(" · ")}</p>
                </div>
              ))}
          </CardContent>
        </Card>
      </TabsContent>
    </Tabs>
  );
}

function EvidenceRow({ text, likes, url }: { text: string; likes: number; url: string | null }) {
  return (
    <div className="rounded-md border bg-white p-2 text-xs">
      <p className="line-clamp-3">{text}</p>
      <div className="mt-1 flex items-center justify-between text-[10px] text-muted-foreground">
        <span>♥ {likes}</span>
        {url ? <a href={url} target="_blank" rel="noreferrer" className="text-indigo-700 hover:underline">view on YouTube</a> : null}
      </div>
    </div>
  );
}

function CommentExplorer({ sessionId }: { sessionId: string }) {
  const [rows, setRows] = useState<CommentRow[]>([]);
  const [total, setTotal] = useState(0);
  const [sentiment, setSentiment] = useState<string>("all");
  const [language, setLanguage] = useState<string>("all");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);

  useEffect(() => {
    const params = new URLSearchParams();
    params.set("limit", "50");
    params.set("offset", String(page * 50));
    if (sentiment !== "all") params.set("sentiment", sentiment);
    if (language !== "all") params.set("language", language);
    if (search.trim()) params.set("search", search.trim());
    api.get<{ total: number; comments: CommentRow[] }>(`/research/sessions/${sessionId}/comments?${params}`)
      .then((d) => { setRows(d.comments); setTotal(d.total); })
      .catch(() => { setRows([]); setTotal(0); });
  }, [sessionId, sentiment, language, search, page]);

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex flex-wrap items-center gap-2">
          <Input value={search} onChange={(e) => { setSearch(e.target.value); setPage(0); }} placeholder="Search comment text…" className="w-56" />
          <Select value={sentiment} onValueChange={(v) => { setSentiment(v); setPage(0); }}>
            <SelectTrigger className="w-36"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All sentiments</SelectItem>
              {["positive", "negative", "neutral", "mixed", "uncertain"].map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}
            </SelectContent>
          </Select>
          <Select value={language} onValueChange={(v) => { setLanguage(v); setPage(0); }}>
            <SelectTrigger className="w-36"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All languages</SelectItem>
              {["english", "roman_urdu", "urdu", "mixed", "unknown"].map((l) => <SelectItem key={l} value={l}>{l}</SelectItem>)}
            </SelectContent>
          </Select>
          <span className="ml-auto text-xs text-muted-foreground">{total.toLocaleString()} comments · page {page + 1}</span>
        </div>
      </CardHeader>
      <CardContent className="p-0">
        <ScrollArea className="max-h-[480px]">
          <div className="divide-y">
            {rows.map((c) => (
              <div key={c.comment_id} className="flex gap-3 p-3 text-xs">
                <div className="w-20 shrink-0 space-y-1">
                  <SentimentBadge sentiment={c.sentiment} />
                  <p className="text-[10px] text-muted-foreground">{c.language} · ♥{c.like_count}</p>
                </div>
                <div className="min-w-0 flex-1">
                  <p className="break-words">{c.text}</p>
                  {c.translation ? <p className="mt-1 text-[11px] italic text-muted-foreground">gloss: {c.translation}</p> : null}
                  <div className="mt-1 flex flex-wrap gap-1">
                    {Object.entries(c.intents || {}).filter(([k, v]) => v && k !== "has_intent" && k !== "purchase_intent").map(([k]) => (
                      <span key={k} className="rounded bg-stone-100 px-1.5 py-0.5 text-[10px] text-stone-600">{k}</span>
                    ))}
                    {c.sarcasm_suspect ? <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] text-amber-800">sarcasm suspect</span> : null}
                    {c.is_spam ? <span className="rounded bg-red-100 px-1.5 py-0.5 text-[10px] text-red-700">spam</span> : null}
                    {c.url ? <a href={c.url} target="_blank" rel="noreferrer" className="ml-auto text-[10px] text-indigo-700 hover:underline">source</a> : null}
                  </div>
                </div>
              </div>
            ))}
            {rows.length === 0 ? <p className="p-6 text-center text-xs text-muted-foreground">No comments match these filters.</p> : null}
          </div>
        </ScrollArea>
        <div className="flex justify-between border-t p-2">
          <Button size="sm" variant="outline" onClick={() => setPage(Math.max(0, page - 1))} disabled={page === 0}>Prev</Button>
          <Button size="sm" variant="outline" onClick={() => setPage(page + 1)} disabled={(page + 1) * 50 >= total}>Next</Button>
        </div>
      </CardContent>
    </Card>
  );
}
