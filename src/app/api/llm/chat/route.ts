import { NextResponse } from "next/server";
import ZAI from "z-ai-web-dev-sdk";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * LLM bridge for the Python research agent (server-side only).
 * POST { messages: [{role, content}], json_mode?: boolean } -> { content }
 */
interface BridgeBody {
  messages?: Array<{ role: string; content: string }>;
  json_mode?: boolean;
}

export async function POST(request: Request) {
  try {
    const body = (await request.json()) as BridgeBody;
    const messages = (body.messages || []).slice(-16).map((m) => ({
      role: m.role === "system" || m.role === "assistant" || m.role === "user" ? m.role : "user",
      content: String(m.content || "").slice(0, 16000),
    }));
    if (messages.length === 0) {
      return NextResponse.json({ error: "messages required" }, { status: 422 });
    }
    const zai = await ZAI.create();
    const completion = await zai.chat.completions.create({
      messages,
      ...(body.json_mode ? { response_format: { type: "json_object" as const } } : {}),
    });
    const content =
      completion && typeof completion === "object" && "choices" in (completion as Record<string, unknown>)
        ? ((completion as unknown as { choices?: Array<{ message?: { content?: string } }> }).choices?.[0]?.message?.content ?? "")
        : String(completion ?? "");
    return NextResponse.json({ content });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "LLM bridge failed" },
      { status: 502 },
    );
  }
}
