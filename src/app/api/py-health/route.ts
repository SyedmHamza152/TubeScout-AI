import { NextResponse } from "next/server";
import { spawn, execSync } from "child_process";
import { existsSync } from "fs";
import path from "path";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const BACKEND_PORT = 8321;
const BACKEND_BASE = (process.env.BACKEND_URL || `http://127.0.0.1:${BACKEND_PORT}`).replace(/\/$/, "");
const BACKEND_URL = `${BACKEND_BASE}/api/v1/health`;
const BACKEND_DIR = path.join(process.cwd(), "backend");

async function healthy(): Promise<boolean> {
  try {
    const res = await fetch(BACKEND_URL, { signal: AbortSignal.timeout(1500) });
    if (!res.ok) return false;
    const data = await res.json();
    return !!data.ok;
  } catch {
    return false;
  }
}

async function waitForHealth(seconds: number): Promise<boolean> {
  for (let i = 0; i < seconds * 2; i++) {
    if (await healthy()) return true;
    await new Promise((r) => setTimeout(r, 500));
  }
  return false;
}

async function ensureEnvironment() {
  const envScript = path.join(BACKEND_DIR, "scripts", "ensure_env.sh");
  if (existsSync(envScript)) {
    try {
      execSync(`bash ${envScript}`, { timeout: 120000, stdio: "ignore" });
    } catch {
      // best effort — backend startup will report DB errors honestly
    }
  }
}

function spawnBackend(): void {
  const venv = "/home/z/.venv/bin";
  const useVenv = existsSync(`${venv}/python`);
  const cmd = useVenv ? `${venv}/python` : "python";
  const child = spawn(
    cmd,
    ["-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", String(BACKEND_PORT)],
    {
      cwd: BACKEND_DIR,
      env: { ...process.env, PYTHONUNBUFFERED: "1" },
      detached: true,
      stdio: "ignore",
    },
  );
  child.unref();
}

export async function GET() {
  if (process.env.BACKEND_URL) {
    try {
      const res = await fetch(BACKEND_URL, { signal: AbortSignal.timeout(5000) });
      const data = await res.json();
      const ok = res.ok && !!data.ok;
      return NextResponse.json({ ok, status: ok ? "healthy" : "unhealthy" }, { status: ok ? 200 : 503 });
    } catch {
      return NextResponse.json({ ok: false, status: "unreachable" }, { status: 503 });
    }
  }
  if (process.env.NODE_ENV === "production") {
    const ok = await healthy();
    return NextResponse.json({ ok, status: ok ? "healthy" : "backend_not_configured" }, { status: ok ? 200 : 503 });
  }
  if (await healthy()) {
    return NextResponse.json({ ok: true, status: "healthy" });
  }
  await ensureEnvironment();
  spawnBackend();
  const ok = await waitForHealth(45);
  return NextResponse.json({ ok, status: ok ? "started" : "starting" }, { status: ok ? 200 : 503 });
}
