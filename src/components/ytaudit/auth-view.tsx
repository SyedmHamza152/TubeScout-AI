"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, setAuth } from "@/lib/api";
import type { UserInfo, WorkspaceInfo } from "@/lib/types";
import { Loader2 } from "lucide-react";

interface LoginResponse {
  token: string;
  user: UserInfo;
  workspace: WorkspaceInfo;
}

export function AuthView({ onDone }: { onDone: () => void }) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [workspaceName, setWorkspaceName] = useState("My workspace");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const path = mode === "login" ? "/auth/login" : "/auth/register";
      const body = mode === "login" ? { email, password } : { email, password, name, workspace_name: workspaceName };
      const res = await api.post<LoginResponse>(path, body);
      setAuth(res.token, res.user, res.workspace);
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Authentication failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-b from-indigo-50 via-white to-white px-4">
      <div className="w-full max-w-md">
        <div className="mb-8 text-center">
          <div className="mx-auto mb-3 flex h-14 w-14 items-center justify-center rounded-2xl bg-indigo-600 text-2xl font-black text-white">
            T
          </div>
          <h1 className="text-2xl font-bold tracking-tight">TubeScout AI</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            YouTube-powered intelligent product discovery.
          </p>
        </div>
        <Card>
          <CardHeader className="pb-3">
            <div className="flex gap-2">
              <Button variant={mode === "login" ? "default" : "outline"} size="sm" onClick={() => setMode("login")} className="flex-1">
                Sign in
              </Button>
              <Button variant={mode === "register" ? "default" : "outline"} size="sm" onClick={() => setMode("register")} className="flex-1">
                Create account
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            <form onSubmit={submit} className="space-y-4">
              {mode === "register" ? (
                <>
                  <div className="space-y-1.5">
                    <Label htmlFor="name">Name</Label>
                    <Input id="name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Your name" />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="ws">Workspace name</Label>
                    <Input id="ws" value={workspaceName} onChange={(e) => setWorkspaceName(e.target.value)} />
                  </div>
                </>
              ) : null}
              <div className="space-y-1.5">
                <Label htmlFor="email">Email</Label>
                <Input id="email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com" />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="password">Password</Label>
                <Input id="password" type="password" required minLength={8} value={password} onChange={(e) => setPassword(e.target.value)} placeholder="min. 8 characters" />
              </div>
              {error ? <p className="text-sm text-red-600">{error}</p> : null}
              <Button type="submit" className="w-full bg-indigo-600 hover:bg-indigo-700" disabled={busy}>
                {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : mode === "login" ? "Sign in" : "Create account & workspace"}
              </Button>
            </form>
          </CardContent>
        </Card>
        <p className="mt-4 text-center text-[11px] text-muted-foreground">
          Official YouTube Data API v3 · Google Ads API · Multilingual sentiment (English / Urdu / Roman Urdu)
        </p>
      </div>
    </div>
  );
}
