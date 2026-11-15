"use client";

import { useCallback, useEffect, useState } from "react";
import { AuthView } from "@/components/ytaudit/auth-view";
import { AgentView } from "@/components/ytaudit/agent-view";
import { DashboardView } from "@/components/ytaudit/dashboard-view";
import { ResearchView } from "@/components/ytaudit/research-view";
import { AudienceView } from "@/components/ytaudit/audience-view";
import { CompetitorsView } from "@/components/ytaudit/competitors-view";
import { CampaignView } from "@/components/ytaudit/campaign-view";
import { FindingsView } from "@/components/ytaudit/findings-view";
import { ProductSearchView } from "@/components/ytaudit/product-search-view";
import { SettingsView } from "@/components/ytaudit/settings-view";
import { ensureBackend, clearAuth, loadUser, loadWorkspace } from "@/lib/api";
import type { UserInfo, WorkspaceInfo } from "@/lib/types";
import { cn } from "@/lib/utils";
import {
  Bot, Database, FileSearch, LayoutDashboard, LogOut, Search, Settings, Target, TrendingUp, Users,
} from "lucide-react";

type View = "dashboard" | "product" | "agent" | "research" | "audience" | "competitors" | "campaigns" | "findings" | "settings";

const NAV: Array<{ key: View; label: string; icon: React.ElementType; group: string }> = [
  { key: "dashboard", label: "Dashboard", icon: LayoutDashboard, group: "Overview" },
  { key: "product", label: "Product Search", icon: Search, group: "Overview" },
  { key: "agent", label: "AI Research Agent", icon: Bot, group: "Research" },
  { key: "research", label: "Live YouTube Research", icon: Database, group: "Research" },
  { key: "audience", label: "Audience Intelligence", icon: Users, group: "Intelligence" },
  { key: "competitors", label: "Competitor Analysis", icon: Target, group: "Intelligence" },
  { key: "campaigns", label: "Campaign & Budget", icon: TrendingUp, group: "Campaign" },
  { key: "findings", label: "Findings & Reports", icon: FileSearch, group: "Output" },
  { key: "settings", label: "Settings & Integrations", icon: Settings, group: "Workspace" },
];

export default function Home() {
  const [ready, setReady] = useState(false);
  const [user, setUser] = useState<UserInfo | null>(null);
  const [workspace, setWorkspace] = useState<WorkspaceInfo | null>(null);
  const [view, setView] = useState<View>("agent");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [booting, setBooting] = useState(true);

  const boot = useCallback(async () => {
    setBooting(true);
    await ensureBackend();
    setUser(loadUser());
    setWorkspace(loadWorkspace());
    setBooting(false);
    setReady(true);
  }, []);

  useEffect(() => { boot(); }, [boot]);

  function logout() {
    clearAuth();
    setUser(null);
    setWorkspace(null);
  }

  if (!ready || booting) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="text-center">
          <div className="mx-auto mb-3 h-10 w-10 animate-pulse rounded-2xl bg-indigo-600" />
          <p className="text-sm text-muted-foreground">Starting TubeScout AI — backend, database and services…</p>
        </div>
      </div>
    );
  }

  if (!user || !workspace) {
    return <AuthView onDone={() => { setUser(loadUser()); setWorkspace(loadWorkspace()); }} />;
  }

  const groups = [...new Set(NAV.map((n) => n.group))];

  return (
    <div className="flex min-h-screen flex-col bg-stone-50">
      <header className="sticky top-0 z-20 border-b bg-white/95 backdrop-blur">
        <div className="flex h-14 items-center justify-between px-4">
          <div className="flex items-center gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-600 text-sm font-black text-white">T</div>
            <div>
              <p className="text-sm font-bold leading-none">TubeScout AI</p>
              <p className="mt-0.5 text-[10px] text-muted-foreground">YouTube-powered intelligent product discovery.</p>
            </div>
          </div>
          <div className="flex items-center gap-3 text-xs">
            <span className="hidden text-muted-foreground sm:inline">
              {workspace.name} · {workspace.market} · {workspace.currency}
            </span>
            <span className="hidden text-muted-foreground md:inline">{user.email}</span>
            <button onClick={logout} className="flex items-center gap-1 rounded-md border px-2 py-1 hover:bg-stone-50">
              <LogOut className="h-3 w-3" /> Sign out
            </button>
          </div>
        </div>
      </header>

      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        <nav className="flex w-full gap-1 overflow-x-auto border-b bg-white p-2 lg:hidden">
          {NAV.map((n) => (
            <button key={n.key} onClick={() => setView(n.key)}
              className={cn("whitespace-nowrap rounded-md px-2.5 py-1.5 text-xs",
                view === n.key ? "bg-indigo-600 text-white" : "text-stone-600")}>
              {n.label}
            </button>
          ))}
        </nav>

        <aside className="hidden w-56 shrink-0 border-r bg-white py-4 lg:block">
          {groups.map((g) => (
            <div key={g} className="mb-3">
              <p className="px-4 pb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">{g}</p>
              {NAV.filter((n) => n.group === g).map((n) => {
                const Icon = n.icon;
                return (
                  <button key={n.key} onClick={() => setView(n.key)}
                    className={cn(
                      "flex w-full items-center gap-2 px-4 py-2 text-left text-sm transition",
                      view === n.key ? "border-l-2 border-indigo-600 bg-indigo-50 font-medium text-indigo-800" : "text-stone-600 hover:bg-stone-50",
                    )}>
                    <Icon className="h-4 w-4" /> {n.label}
                  </button>
                );
              })}
            </div>
          ))}
        </aside>

        <main className="min-w-0 flex-1 px-4 py-5 lg:px-6">
          <div className="mx-auto w-full max-w-6xl">
            {view === "dashboard" ? <DashboardView onNavigate={(v) => setView(v as View)} /> : null}
            {view === "product" ? <ProductSearchView onSessionStarted={(id) => { setSessionId(id); setView("research"); }} /> : null}
            {view === "agent" ? <AgentView onSessionStarted={(id) => { setSessionId(id); }} /> : null}
            {view === "research" ? <ResearchView activeSessionId={sessionId} onSelect={setSessionId} /> : null}
            {view === "audience" ? <AudienceView /> : null}
            {view === "competitors" ? <CompetitorsView /> : null}
            {view === "campaigns" ? <CampaignView /> : null}
            {view === "findings" ? <FindingsView /> : null}
            {view === "settings" ? <SettingsView /> : null}
          </div>
        </main>
      </div>

      <footer className="border-t bg-white py-3 text-center text-[11px] text-muted-foreground">
        TubeScout AI · official YouTube Data API v3 + Google Ads API only · every result carries a provenance label · recommendation system, never auto-executes campaigns
      </footer>
    </div>
  );
}
