"use client";

import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "@/lib/api";
import type { CompetitorProfile, ResearchSession, TrackedChannelRow } from "@/lib/types";
import { Disclaimer, EmptyState } from "./bits";

export function CompetitorsView() {
  const [profiles, setProfiles] = useState<CompetitorProfile[]>([]);
  const [channels, setChannels] = useState<TrackedChannelRow[]>([]);
  const [sessions, setSessions] = useState<ResearchSession[]>([]);
  const [sessionId, setSessionId] = useState<string>("all");
  const [gapTarget, setGapTarget] = useState("");
  const [gaps, setGaps] = useState<Array<{ tag: string; coverage: number }> | null>(null);
  const [gapError, setGapError] = useState<string | null>(null);

  useEffect(() => {
    api.get<{ sessions: ResearchSession[] }>("/research/sessions").then((d) => setSessions(d.sessions)).catch(() => {});
  }, []);

  const load = useCallback(async () => {
    const qs = sessionId !== "all" ? `?session_id=${sessionId}` : "";
    const d = await api.get<{ profiles: CompetitorProfile[]; tracked_channels: TrackedChannelRow[] }>(`/competitors/channels${qs}`);
    setProfiles(d.profiles);
    setChannels(d.tracked_channels);
    if (!gapTarget && d.profiles.length) setGapTarget(d.profiles[0].channel_title);
  }, [sessionId, gapTarget]);

  useEffect(() => { load(); }, [sessionId]);

  async function findGaps() {
    setGapError(null);
    setGaps(null);
    try {
      if (sessionId === "all") {
        setGapError("Select a specific research session for gap analysis.");
        return;
      }
      const d = await api.get<{ gaps: Array<{ tag: string; coverage: number }>; reason?: string }>(
        `/competitors/gaps/${sessionId}?target_channel=${encodeURIComponent(gapTarget)}`);
      setGaps(d.gaps || []);
      if (d.reason) setGapError(d.reason);
    } catch (err) {
      setGapError(err instanceof Error ? err.message : "gap analysis failed");
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-lg font-bold">Competitor &amp; Market Intelligence</h1>
          <p className="text-xs text-muted-foreground">Public YouTube data only — no private analytics, ad spend or competitor ROAS</p>
        </div>
        <Select value={sessionId} onValueChange={setSessionId}>
          <SelectTrigger className="w-56"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All sessions</SelectItem>
            {sessions.map((s) => <SelectItem key={s.id} value={s.id}>{s.title.slice(0, 36)}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>

      {profiles.length >= 1 ? (
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm">Channel comparison</CardTitle></CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Channel</TableHead>
                  <TableHead className="text-right">Videos</TableHead>
                  <TableHead className="text-right">Median views</TableHead>
                  <TableHead className="text-right">Engagement</TableHead>
                  <TableHead className="text-right">Shorts share</TableHead>
                  <TableHead className="text-right">Cadence/wk</TableHead>
                  <TableHead className="text-right">Comments</TableHead>
                  <TableHead className="text-right">Neg %</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {profiles.map((p) => (
                  <TableRow key={p.channel_id}>
                    <TableCell className="font-medium">{p.channel_title}</TableCell>
                    <TableCell className="text-right tabular-nums">{p.videos_in_research}</TableCell>
                    <TableCell className="text-right tabular-nums">{Math.round(p.median_views).toLocaleString()}</TableCell>
                    <TableCell className="text-right tabular-nums">{p.avg_engagement_rate.toFixed(4)}</TableCell>
                    <TableCell className="text-right tabular-nums">{Math.round(p.shorts_share * 100)}%</TableCell>
                    <TableCell className="text-right tabular-nums">{p.upload_cadence_per_week}</TableCell>
                    <TableCell className="text-right tabular-nums">{p.comments_collected}</TableCell>
                    <TableCell className="text-right tabular-nums">{p.negative_pct}%</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      ) : (
        <EmptyState title="No channel data yet" hint="Run channel- or keyword-based research; each discovered channel is profiled from public stats." />
      )}

      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-sm">Content-gap finder</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap gap-2">
            <Input value={gapTarget} onChange={(e) => setGapTarget(e.target.value)} placeholder="Your channel title (exact match)" className="w-72" />
            <Button size="sm" className="bg-indigo-600 hover:bg-indigo-700" onClick={findGaps}>Find gaps</Button>
          </div>
          {gapError ? <p className="text-xs text-amber-700">{gapError}</p> : null}
          {gaps && gaps.length > 0 ? (
            <div className="flex flex-wrap gap-2">
              {gaps.map((g) => (
                <span key={g.tag} className="rounded-full border bg-white px-3 py-1 text-xs">
                  {g.tag} <span className="text-muted-foreground">({g.coverage})</span>
                </span>
              ))}
            </div>
          ) : gaps ? <p className="text-xs text-muted-foreground">No missing tags detected among compared channels.</p> : null}
          <Disclaimer>Gaps are inferred from public video tags of comparable channels in the workspace (LIVE DATA, directional only).</Disclaimer>
        </CardContent>
      </Card>

      {channels.length > 0 ? (
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm">Tracked channels ({channels.length})</CardTitle></CardHeader>
          <CardContent className="grid gap-2 text-xs md:grid-cols-2 xl:grid-cols-3">
            {channels.map((c) => (
              <div key={c.channel_id} className="rounded-md border p-2">
                <div className="flex items-center justify-between">
                  <b>{c.title}</b>
                  {c.is_competitor ? <span className="rounded bg-indigo-100 px-1.5 py-0.5 text-[10px] text-indigo-800">competitor</span> : null}
                </div>
                <p className="text-muted-foreground">
                  {c.handle ? `@${c.handle} · ` : ""}{c.subscribers.toLocaleString()} subs · {c.video_count.toLocaleString()} videos
                  {c.last_synced_at ? ` · synced ${new Date(c.last_synced_at).toLocaleDateString()}` : ""}
                </p>
              </div>
            ))}
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
