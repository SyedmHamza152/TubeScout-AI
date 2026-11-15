"use client";

import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api } from "@/lib/api";
import type { BudgetRun, ResearchSession } from "@/lib/types";
import { Disclaimer, LabelBadge } from "./bits";
import { Bar, BarChart, CartesianGrid, Cell, ComposedChart, Legend, Line, PolarAngleAxis, PolarGrid, PolarRadiusAxis, Radar, RadarChart, ResponsiveContainer, Tooltip as ChartTooltip, XAxis, YAxis } from "recharts";

const FORMAT_COLORS: Record<string, string> = { in_stream: "#0d9488", shorts: "#0ea5e9", in_feed: "#f59e0b" };
const formatColor = (key: string) => FORMAT_COLORS[key] ?? "#64748b";
const fmtMoney = (v: number, c: string) => `${Math.round(v).toLocaleString()} ${c}`;
const fmtNum = (v: number | null | undefined, d = 0) => (v == null ? "—" : Number(v).toLocaleString(undefined, { maximumFractionDigits: d }));
const fmtPct = (v: number, d = 0) => `${(v <= 1 ? v * 100 : v).toFixed(d)}%`;

function allocationInference(run: BudgetRun): string[] {
  const allocs = [...run.allocations].sort((a, b) => b.amount - a.amount);
  if (!allocs.length) return [];
  const top = allocs[0];
  const second = allocs[1];
  const out: string[] = [];
  out.push(top.share >= 0.5
    ? `${top.label} takes ${fmtPct(top.share, 0)} of the budget because it produced the highest objective-aligned value for “${run.objective}” under the optimizer constraints.`
    : `The budget is split rather than concentrated: ${top.label} leads at ${fmtPct(top.share, 0)}, with no single format dominating the objective value.`);
  if (second) {
    out.push(`${top.label} receives about ${Math.round((top.share - second.share) * 100)} percentage points more than ${second.label}; that gap comes from predicted funnel performance and fit multipliers, not from spend history alone.`);
  }
  const bonuses = (run.meta?.exploration_bonuses ?? {}) as Record<string, number>;
  const bonusKeys = Object.entries(bonuses).filter(([, v]) => v > 0.01).sort((a, b) => b[1] - a[1]).slice(0, 2);
  if (bonusKeys.length) {
    out.push(`Exploration bonus was applied to ${bonusKeys.map(([k, v]) => `${run.allocations.find((a) => a.format_key === k)?.label ?? k} (+${v.toFixed(2)})`).join(", ")} because evidence is thinner — the optimizer keeps a fair trial budget instead of starving those formats.`);
  }
  const fitEntries = Object.entries(top.fit_factors ?? {}).filter(([, v]) => v > 1.05).sort((a, b) => b[1] - a[1]).slice(0, 3);
  if (fitEntries.length) {
    out.push(`For ${top.label}, the strongest fit signals were ${fitEntries.map(([k, v]) => `${k} ×${v.toFixed(2)}`).join(", ")}; values above 1.0 mean that dimension supports this format for the brief.`);
  }
  out.push(run.cold_start || run.source_label === "ESTIMATED SCENARIO"
    ? "This is an estimated scenario: the division is anchored on documented priors and live research signals, so treat the percentages as a planning split rather than a forecast."
    : "This division is blended with synced Google Ads campaign history, so the shares reflect both priors and actual performance.");
  return out;
}

export function CampaignView() {
  const [formats, setFormats] = useState<Record<string, string>>({});
  const [objectives, setObjectives] = useState<string[]>([]);
  const [sessions, setSessions] = useState<ResearchSession[]>([]);
  const [briefId, setBriefId] = useState<number | null>(null);
  const [run, setRun] = useState<BudgetRun | null>(null);
  const [scenarios, setScenarios] = useState<BudgetRun[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({
    product: "", description: "", country: "PK", currency: "PKR", total_budget: "150000",
    duration_days: "14", objective: "Sales / Conversions", target_audience: "", session_id: "",
  });
  const [preferred, setPreferred] = useState<string[]>([]);

  useEffect(() => {
    api.get<{ formats: Record<string, string>; objectives: string[] }>("/campaigns/meta")
      .then((d) => { setFormats(d.formats); setObjectives(d.objectives); }).catch(() => {});
    api.get<{ sessions: ResearchSession[] }>("/research/sessions").then((d) => setSessions(d.sessions)).catch(() => {});
    api.get<{ briefs: Array<{ id: number }> }>("/campaigns/briefs").then((d) => {
      if (d.briefs.length) setBriefId(d.briefs[0].id);
    }).catch(() => {});
  }, []);

  const loadRun = useCallback(async (id: number) => {
    const d = await api.get<{ runs: BudgetRun[] }>("/campaigns/runs");
    const mine = d.runs.find((r) => r.id === id);
    if (mine) setRun(mine);
  }, []);

  async function createAndOptimize(strategy: string) {
    setBusy(true);
    setError(null);
    try {
      const body = {
        product: form.product || "product", description: form.description,
        country: form.country, currency: form.currency,
        total_budget: parseFloat(form.total_budget) || 0,
        duration_days: parseInt(form.duration_days) || 14,
        objective: form.objective, target_audience: form.target_audience,
        preferred_formats: preferred,
        session_id: form.session_id || null,
        strategy,
      };
      const brief = await api.post<{ id: number }>("/campaigns/briefs", body);
      setBriefId(brief.id);
      const res = await api.post<BudgetRun>(`/campaigns/briefs/${brief.id}/optimize?strategy=${strategy}`);
      setRun(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "optimization failed");
    } finally {
      setBusy(false);
    }
  }

  async function compareScenarios() {
    if (!briefId) return;
    setBusy(true);
    setError(null);
    try {
      const d = await api.post<{ scenarios: BudgetRun[] }>(`/campaigns/briefs/${briefId}/scenarios`);
      setScenarios(d.scenarios);
    } catch (err) {
      setError(err instanceof Error ? err.message : "scenario comparison failed");
    } finally {
      setBusy(false);
    }
  }

  const totalAllocated = run?.allocations.reduce((s, a) => s + a.amount, 0) ?? 0;
  const utilities = (run?.meta?.effective_utilities ?? {}) as Record<string, number>;
  const utilityData = run ? Object.entries(utilities).map(([key, u]) => ({ key, name: run.allocations.find((a) => a.format_key === key)?.label ?? key, utility: Math.round(u * 1000) / 1000 })) : [];
  const fitDims = ["audience", "objective", "category", "research"] as const;
  const fitAllocs = run?.allocations.filter((a) => a.fit_factors && Object.keys(a.fit_factors).length) ?? [];
  const radarData = fitAllocs.length ? fitDims.map((dim) => ({ dim, ...Object.fromEntries(fitAllocs.map((a) => [a.format_key, a.fit_factors[dim] ?? 1])) })) : [];
  const inferenceLines = run ? allocationInference(run) : [];

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-bold">Campaign Intelligence &amp; Budget Optimizer</h1>
        <p className="text-xs text-muted-foreground">
          SLSQP constrained optimization · UCB exploration · exact-budget rounding · recommendation only (never auto-executes)
        </p>
      </div>

      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-sm">Campaign brief (USER INPUT)</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <div className="grid gap-3 md:grid-cols-3">
            <div className="space-y-1.5 md:col-span-2">
              <Label>Product / service</Label>
              <Input value={form.product} onChange={(e) => setForm({ ...form, product: e.target.value })} placeholder="Winter lawn collection" />
            </div>
            <div className="space-y-1.5">
              <Label>Total budget ({form.currency})</Label>
              <Input type="number" value={form.total_budget} onChange={(e) => setForm({ ...form, total_budget: e.target.value })} />
            </div>
            <div className="space-y-1.5 md:col-span-3">
              <Label>Description</Label>
              <Input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="Pakistani clothing brand, women's lawn suits for winter" />
            </div>
            <div className="space-y-1.5">
              <Label>Country</Label>
              <Input value={form.country} onChange={(e) => setForm({ ...form, country: e.target.value })} />
            </div>
            <div className="space-y-1.5">
              <Label>Currency</Label>
              <Input value={form.currency} onChange={(e) => setForm({ ...form, currency: e.target.value })} />
            </div>
            <div className="space-y-1.5">
              <Label>Duration (days)</Label>
              <Input type="number" value={form.duration_days} onChange={(e) => setForm({ ...form, duration_days: e.target.value })} />
            </div>
            <div className="space-y-1.5">
              <Label>Objective</Label>
              <Select value={form.objective} onValueChange={(v) => setForm({ ...form, objective: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>{objectives.map((o) => <SelectItem key={o} value={o}>{o}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Target audience (optional)</Label>
              <Input value={form.target_audience} onChange={(e) => setForm({ ...form, target_audience: e.target.value })} placeholder="young women 18-34, fashion" />
            </div>
            <div className="space-y-1.5">
              <Label>Link research session (optional)</Label>
              <Select value={form.session_id || "none"} onValueChange={(v) => setForm({ ...form, session_id: v === "none" ? "" : v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">None</SelectItem>
                  {sessions.map((s) => <SelectItem key={s.id} value={s.id}>{s.title.slice(0, 30)} — {s.status}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Preferred formats (optional)</Label>
              <div className="flex flex-wrap gap-2 pt-1">
                {Object.entries(formats).map(([k, v]) => (
                  <label key={k} className="flex items-center gap-1 text-xs">
                    <input type="checkbox" checked={preferred.includes(k)}
                      onChange={(e) => setPreferred(e.target.checked ? [...preferred, k] : preferred.filter((x) => x !== k))} />
                    {v}
                  </label>
                ))}
              </div>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button className="bg-indigo-600 hover:bg-indigo-700" onClick={() => createAndOptimize("balanced")} disabled={busy || !form.product}>
              {busy ? "Optimizing…" : "Optimize (balanced)"}
            </Button>
            <Button variant="outline" onClick={() => createAndOptimize("performance")} disabled={busy}>Performance strategy</Button>
            <Button variant="outline" onClick={() => createAndOptimize("exploratory")} disabled={busy}>Exploratory strategy</Button>
            <Button variant="outline" onClick={compareScenarios} disabled={busy || !briefId}>Compare scenarios</Button>
          </div>
          {error ? <p className="text-xs text-red-600">{error}</p> : null}
        </CardContent>
      </Card>

      {run ? (
        <div className="space-y-4">
          <Card>
            <CardHeader className="pb-2">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <CardTitle className="text-sm">Recommended allocation — {run.strategy} strategy</CardTitle>
                  <p className="text-[11px] text-muted-foreground">{run.algorithm} · generated {new Date(run.created_at).toLocaleString()}</p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <LabelBadge label={run.source_label} />
                  {run.cold_start ? <span className="rounded-full border border-amber-300 bg-amber-100 px-2 py-0.5 text-[10px] font-semibold text-amber-800">COLD START</span> : null}
                  <span className="rounded-full border px-2 py-0.5 text-[10px] text-muted-foreground">Confidence {fmtPct(run.confidence, 0)}</span>
                  <span className="rounded-full border px-2 py-0.5 text-[10px] text-muted-foreground">Sum {fmtMoney(totalAllocated, run.currency)} {Math.abs(totalAllocated - run.total_budget) < 0.01 ? "✓ exact" : "✗"}</span>
                </div>
              </div>
              <p className="text-[11px] text-muted-foreground">Total {fmtMoney(run.total_budget, run.currency)} distributed across {run.allocations.length} format{run.allocations.length > 1 ? "s" : ""} · objective {run.objective}</p>
            </CardHeader>
          </Card>

          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-sm">Recommended allocation</CardTitle></CardHeader>
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <table className="w-full min-w-[760px] text-xs">
                  <thead>
                    <tr className="border-b text-left text-muted-foreground">
                      <th className="p-3">Advertising format</th><th className="p-3">Share</th><th className="p-3">Amount</th>
                      <th className="p-3">Predicted performance</th><th className="p-3 text-right">Confidence</th>
                    </tr>
                  </thead>
                  <tbody>
                    {run.allocations.map((a) => (
                      <tr key={a.format_key} className="border-b">
                        <td className="p-3 font-medium">{a.label}</td>
                        <td className="p-3">
                          <div className="flex items-center gap-2">
                            <div className="h-1.5 w-16 overflow-hidden rounded-full bg-stone-200">
                              <div className="h-full rounded-full" style={{ width: `${a.share * 100}%`, background: formatColor(a.format_key) }} />
                            </div>
                            {(a.share * 100).toFixed(0)}%
                          </div>
                        </td>
                        <td className="p-3 tabular-nums">{fmtMoney(a.amount, run.currency)}</td>
                        <td className="p-3 text-muted-foreground">
                          {fmtNum(a.predicted["impressions"])} impr · {fmtNum(a.predicted["clicks"])} clicks · {fmtNum(a.predicted["conversions"], 0)} conv · ROAS {a.predicted["roas"] ?? "—"}
                        </td>
                        <td className="p-3 text-right tabular-nums">{fmtPct(a.confidence, 0)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>

          <div className="grid gap-4 lg:grid-cols-2">
            {radarData.length ? (
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm">Why each format scores the way it does</CardTitle>
                  <p className="text-[11px] text-muted-foreground">Fit multipliers: audience, objective, category and live YouTube niche signal (1.0 = neutral).</p>
                </CardHeader>
                <CardContent className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <RadarChart data={radarData}>
                      <PolarGrid stroke="#e7e5e4" />
                      <PolarAngleAxis dataKey="dim" tick={{ fill: "#78716c", fontSize: 11 }} />
                      <PolarRadiusAxis domain={[0.5, 1.5]} tick={{ fill: "#78716c", fontSize: 9 }} axisLine={false} />
                      {fitAllocs.map((a) => (
                        <Radar key={a.format_key} name={a.label} dataKey={a.format_key} stroke={formatColor(a.format_key)} fill={formatColor(a.format_key)} fillOpacity={0.15} strokeWidth={2} />
                      ))}
                      <Legend wrapperStyle={{ fontSize: 11 }} />
                      <ChartTooltip />
                    </RadarChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>
            ) : null}
            {utilityData.length ? (
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm">Objective-aligned utility per format</CardTitle>
                  <p className="text-[11px] text-muted-foreground">Value per currency unit the optimizer maximizes for “{run.objective}”.</p>
                </CardHeader>
                <CardContent className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={utilityData} layout="vertical" margin={{ left: 8, right: 24 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#eee" horizontal={false} />
                      <XAxis type="number" tick={{ fill: "#78716c", fontSize: 10 }} axisLine={{ stroke: "#e7e5e4" }} tickLine={false} />
                      <YAxis type="category" dataKey="name" width={150} tick={{ fill: "#44403c", fontSize: 11 }} axisLine={false} tickLine={false} />
                      <ChartTooltip formatter={(v: number) => [v, "utility"]} cursor={{ fill: "rgba(13,148,136,0.06)" }} />
                      <Bar dataKey="utility" radius={[0, 6, 6, 0]} barSize={30}>
                        {utilityData.map((d) => <Cell key={d.key} fill={formatColor(d.key)} />)}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>
            ) : null}
          </div>

          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-sm">Predicted outcomes per format</CardTitle></CardHeader>
            <CardContent className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={run.allocations.map((a) => ({ name: a.label.replace("YouTube ", "").replace(" Ads", ""), conversions: a.predicted["conversions"] ?? 0, roas: a.predicted["roas"] ?? 0, key: a.format_key }))}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
                  <XAxis dataKey="name" tick={{ fill: "#78716c", fontSize: 11 }} tickLine={false} axisLine={{ stroke: "#e7e5e4" }} />
                  <YAxis yAxisId="l" tick={{ fill: "#78716c", fontSize: 10 }} tickLine={false} axisLine={false} tickFormatter={(v) => fmtNum(v)} width={56} />
                  <YAxis yAxisId="r" orientation="right" tick={{ fill: "#78716c", fontSize: 10 }} tickLine={false} axisLine={false} width={40} />
                  <ChartTooltip />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <Bar yAxisId="l" dataKey="conversions" name="Conversions (MODEL PREDICTION)" radius={[4, 4, 0, 0]}>
                    {run.allocations.map((a) => <Cell key={a.format_key} fill={formatColor(a.format_key)} />)}
                  </Bar>
                  <Line yAxisId="r" type="monotone" dataKey="roas" name="ROAS (×)" stroke="#e879f9" strokeWidth={2} dot={{ r: 4 }} />
                </ComposedChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-sm">Why this allocation</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              {run.allocations.map((a) => (
                <div key={a.format_key} className="rounded-lg border bg-stone-50 p-3">
                  <p className="text-sm font-semibold">{a.label} — {(a.share * 100).toFixed(0)}% ({fmtMoney(a.amount, run.currency)})</p>
                  <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{a.reason}</p>
                </div>
              ))}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-sm">Allocation inference <LabelBadge label="INFERENCE" /></CardTitle></CardHeader>
            <CardContent className="space-y-2">
              {inferenceLines.map((line, i) => <p key={i} className="text-xs leading-relaxed text-muted-foreground">{line}</p>)}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-sm">Methodology</CardTitle></CardHeader>
            <CardContent className="space-y-2 text-xs text-muted-foreground">
              <p className="rounded-md border border-stone-200 bg-stone-50 p-3 text-[11px] leading-relaxed text-stone-600">{run.methodology}</p>
              <p>Predicted totals: {fmtNum(run.predicted_totals["impressions"])} impressions · {fmtNum(run.predicted_totals["clicks"])} clicks · {fmtNum(run.predicted_totals["conversions"], 0)} conversions · {run.predicted_totals["revenue"] != null ? fmtMoney(Number(run.predicted_totals["revenue"]), run.currency) : "—"} revenue · ROAS {run.predicted_totals["roas"] ?? "—"}</p>
              <Disclaimer>{run.disclaimer}</Disclaimer>
            </CardContent>
          </Card>
        </div>
      ) : null}

      {scenarios.length ? (
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm">Strategy comparison</CardTitle></CardHeader>
          <CardContent className="p-0">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b text-left text-muted-foreground">
                  <th className="p-2">Strategy</th>
                  <th className="p-2">Allocation</th>
                  <th className="p-2 text-right">Confidence</th>
                  <th className="p-2 text-right">Label</th>
                </tr>
              </thead>
              <tbody>
                {scenarios.map((r) => (
                  <tr key={r.id} className="border-b">
                    <td className="p-2 font-medium">{r.strategy}</td>
                    <td className="p-2">{r.allocations.map((a) => `${a.label.split(" ")[0]} ${Math.round(a.share * 100)}%`).join(" · ")}</td>
                    <td className="p-2 text-right tabular-nums">{r.confidence}</td>
                    <td className="p-2"><LabelBadge label={r.source_label} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
