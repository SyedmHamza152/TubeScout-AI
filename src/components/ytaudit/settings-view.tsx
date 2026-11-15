"use client";

import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import type { QuotaStatus } from "@/lib/types";
import { Disclaimer, StatCard } from "./bits";
import { ExternalLink, RefreshCw } from "lucide-react";

interface YTStatus {
  configured: boolean;
  api: string;
  scraping: string;
  quota: QuotaStatus;
  hint: string;
}

interface GoogleStatus {
  app_configured: boolean;
  app_missing: string[];
  workspace_connected: boolean;
  email: string;
  customer_id: string;
  status: string;
  detail: string;
  actual_data_available: boolean;
  note: string;
}

export function SettingsView() {
  const [yt, setYt] = useState<YTStatus | null>(null);
  const [google, setGoogle] = useState<GoogleStatus | null>(null);
  const [customerId, setCustomerId] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    const y = await api.get<YTStatus>("/integrations/youtube/status");
    setYt(y);
    const g = await api.get<GoogleStatus>("/integrations/google/status");
    setGoogle(g);
    if (g.customer_id) setCustomerId(g.customer_id);
  }, []);

  useEffect(() => { load(); }, [load]);

  async function connectGoogle() {
    setBusy("connect");
    setMsg(null);
    try {
      const d = await api.get<{ authorization_url: string }>("/integrations/google/start");
      window.location.href = d.authorization_url.replace("http://localhost:8321", `${window.location.origin}/api/v1`).replace("/api/v1/api/v1", "/api/v1") + `&XTransformPort=8321`;
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "OAuth start failed");
    } finally {
      setBusy(null);
    }
  }

  async function saveCustomer() {
    setBusy("customer");
    try {
      await api.post(`/integrations/google/customer?customer_id=${encodeURIComponent(customerId)}`);
      await load();
      setMsg("Customer ID saved.");
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "failed");
    } finally {
      setBusy(null);
    }
  }

  async function testConnection() {
    setBusy("test");
    try {
      const r = await api.post<{ ok: boolean; detail?: string; video_campaigns_last_90d?: number }>("/integrations/google/test-connection");
      setMsg(r.ok ? `Connected — ${r.video_campaigns_last_90d ?? 0} video campaigns in last 90 days.` : `Test failed: ${r.detail}`);
      await load();
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "test failed");
    } finally {
      setBusy(null);
    }
  }

  async function syncAds() {
    setBusy("sync");
    try {
      const r = await api.post<{ campaigns: number; rows_synced: number }>("/integrations/google/sync?days=90");
      setMsg(`Synced ${r.campaigns} campaigns, ${r.rows_synced} daily rows (LIVE DATA).`);
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "sync failed");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-bold">Settings &amp; Integrations</h1>
        <p className="text-xs text-muted-foreground">API connection status, quota management and data policy</p>
      </div>

      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-sm">YouTube Data API v3</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          {yt ? (
            <>
              <div className="grid gap-3 sm:grid-cols-4">
                <StatCard title="Connection" value={yt.configured ? "Configured" : "Not configured"} sub={yt.configured ? yt.api : yt.hint} />
                <StatCard title="Quota used today" value={`${yt.quota.used_today.toLocaleString()} / ${yt.quota.limit.toLocaleString()}`} sub={`${yt.quota.remaining.toLocaleString()} units remaining`} />
                <StatCard title="Search calls left" value={Math.floor(yt.quota.remaining / 100)} sub="search.list costs 100 units" />
                <StatCard title="Scraping" value={yt.scraping} sub="official API only, by policy" />
              </div>
              {!yt.configured ? (
                <Disclaimer>
                  Set <code>YOUTUBE_API_KEY</code> in <code>backend/.env</code> (Google Cloud Console → Enable YouTube Data API v3 →
                  create API key). Until then, live collection is unavailable and the app shows honest empty states — no demo data is substituted.
                </Disclaimer>
              ) : null}
            </>
          ) : <p className="text-xs text-muted-foreground">Loading…</p>}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-sm">Google Ads (actual campaign performance)</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          {google ? (
            <>
              <div className="grid gap-2 text-xs md:grid-cols-3">
                <StatCard title="Server OAuth app" value={google.app_configured ? "Configured" : "Missing env"} sub={google.app_missing.join(", ") || "OAuth client + Google Cloud project access"} />
                <StatCard title="Workspace connection" value={google.workspace_connected ? `Connected (${google.email || "google account"})` : google.status} />
                <StatCard title="Actual data available" value={google.actual_data_available ? "Yes" : "No"} sub={google.actual_data_available ? "LIVE DATA sync enabled" : "estimated scenarios only, clearly labeled"} />
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Button size="sm" className="bg-indigo-600 hover:bg-indigo-700" onClick={connectGoogle} disabled={!google.app_configured || busy !== null}>
                  <ExternalLink className="mr-1 h-4 w-4" /> Connect Google Ads
                </Button>
                <Input value={customerId} onChange={(e) => setCustomerId(e.target.value)} placeholder="Ads customer ID (123-456-7890)" className="w-56" />
                <Button size="sm" variant="outline" onClick={saveCustomer} disabled={busy !== null}>Save customer ID</Button>
                <Button size="sm" variant="outline" onClick={testConnection} disabled={busy !== null || !google.workspace_connected}>Test</Button>
                <Button size="sm" variant="outline" onClick={syncAds} disabled={busy !== null || !google.workspace_connected}>
                  <RefreshCw className="mr-1 h-3 w-3" /> Sync 90 days
                </Button>
              </div>
              {google.detail ? <p className="text-xs text-amber-700">{google.detail}</p> : null}
              <Disclaimer>
                When Google Ads is not connected, actual campaign performance data is unavailable; the optimizer uses documented
                priors and live research signals and labels every result ESTIMATED SCENARIO. Organic YouTube statistics are never
                presented as advertising metrics.
              </Disclaimer>
            </>
          ) : <p className="text-xs text-muted-foreground">Loading…</p>}
        </CardContent>
      </Card>

      {msg ? <p className="rounded-md border border-indigo-200 bg-indigo-50 px-3 py-2 text-xs text-indigo-900">{msg}</p> : null}

      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-sm">Data policy</CardTitle></CardHeader>
        <CardContent className="space-y-1 text-xs text-muted-foreground">
          <p>· Official APIs only (YouTube Data API v3, Google Ads API). Scraping and unofficial endpoints are disabled.</p>
          <p>· Mandatory provenance labels on every derived result: LIVE DATA / MODEL PREDICTION / ESTIMATED SCENARIO / INFERENCE / USER INPUT / INSUFFICIENT DATA.</p>
          <p>· Percentages describe the collected sample, never the entire YouTube audience. Segments are behavioural inferences, not demographics.</p>
          <p>· No demo seeding, synthetic history or lab environments exist in this platform by design.</p>
        </CardContent>
      </Card>
    </div>
  );
}
