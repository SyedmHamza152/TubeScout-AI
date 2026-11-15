"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api } from "@/lib/api";
import type { ChatMessage, ResearchPlan } from "@/lib/types";
import { LabelBadge } from "./bits";
import { Bot, Check, Loader2, Pencil, Plus, Send, Sparkles } from "lucide-react";

interface MessageBody {
  text: string;
  conversation_id?: string | null;
}
interface AgentReply {
  reply: string;
  conversation_id: string;
  payload: Record<string, unknown>;
  plan?: ResearchPlan;
  plan_id?: number;
}

export function AgentView({ onSessionStarted }: { onSessionStarted: (sessionId: string) => void }) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [plan, setPlan] = useState<ResearchPlan | null>(null);
  const [planId, setPlanId] = useState<number | null>(null);
  const [planStatus, setPlanStatus] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [editForm, setEditForm] = useState<Record<string, string>>({});
  const [sessionId, setSessionId] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  async function loadConversation(cid: string) {
    setConversationId(cid);
    const data = await api.get<{ messages: ChatMessage[] }>(`/agent/conversations/${cid}/messages`);
    setMessages(data.messages);
    const planMsg = [...data.messages].reverse().find((m) => m.payload && m.payload["type"] === "plan");
    if (planMsg) {
      setPlan(planMsg.payload["plan"] as ResearchPlan);
      const pid = planMsg.payload["plan_id"];
      setPlanId(typeof pid === "number" ? pid : null);
      setPlanStatus(typeof planMsg.payload["status"] === "string" ? String(planMsg.payload["status"]) : null);
      setEditing(false);
    }
  }

  async function newConversation() {
    const res = await api.post<{ conversation_id: string }>("/agent/conversations");
    setConversationId(res.conversation_id);
    setMessages([]);
    setPlan(null);
    setPlanId(null);
    setPlanStatus(null);
    setEditing(false);
    setSessionId(null);
  }

  async function send(text: string) {
    if (!text.trim() || busy) return;
    setInput("");
    setBusy(true);
    setMessages((m) => [...m, { id: Date.now(), role: "user", content: text, payload: {}, created_at: new Date().toISOString() }]);
    try {
      const body: MessageBody = { text, conversation_id: conversationId };
      const res = await api.post<AgentReply>("/agent/message", body);
      setConversationId(res.conversation_id);
      setMessages((m) => [...m, {
        id: Date.now() + 1, role: "assistant", content: res.reply, payload: res.payload,
        created_at: new Date().toISOString(),
      }]);
      const p = res.payload as Record<string, unknown>;
      if (res.plan) {
        setPlan(res.plan);
        setPlanId(res.plan_id ?? null);
        setPlanStatus(typeof p["status"] === "string" ? String(p["status"]) : "draft");
      }
      if (p["type"] === "plan_cancelled") {
        setPlan(null);
        setPlanId(null);
        setPlanStatus(null);
        setEditing(false);
      }
      if (p["type"] === "execution_started" && typeof p["session_id"] === "string") {
        setSessionId(p["session_id"]);
        onSessionStarted(p["session_id"]);
      }
    } catch (err) {
      setMessages((m) => [...m, {
        id: Date.now() + 2, role: "assistant",
        content: err instanceof Error ? err.message : "Request failed.",
        payload: {}, created_at: new Date().toISOString(),
      }]);
    } finally {
      setBusy(false);
    }
  }

  async function approvePlan() {
    if (!planId) return;
    setBusy(true);
    try {
      const res = await api.post<{ reply: string; payload: Record<string, unknown> }>(
        "/agent/message",
        { text: "Approve this plan and execute the research.", conversation_id: conversationId },
      );
      setMessages((m) => [...m, { id: Date.now() + 3, role: "assistant", content: res.reply, payload: res.payload, created_at: new Date().toISOString() }]);
      setPlanStatus("executed");
      const p = res.payload as Record<string, unknown>;
      if (p["type"] === "execution_started" && typeof p["session_id"] === "string") {
        setSessionId(p["session_id"]);
        onSessionStarted(p["session_id"]);
      }
    } finally {
      setBusy(false);
    }
  }

  function startEditing() {
    if (!plan) return;
    setEditing(true);
    setEditForm({
      title: plan.title,
      country: plan.country,
      mode: plan.mode,
      aspect_pack: plan.aspect_pack,
      date_range_days: String(plan.date_range_days),
      max_videos: String(plan.collection["max_videos"] || 40),
      comments_per_video: String(plan.collection["comments_per_video"] || 60),
      comment_total_cap: String(plan.collection["comment_total_cap"] || 2000),
      keywords: (plan.keywords || []).join(", "),
      channels: (plan.channels || []).join(", "),
    });
  }

  function setEditField(key: string, value: string) {
    setEditForm((f) => ({ ...f, [key]: value }));
  }

  async function saveEdits() {
    if (!planId) return;
    const num = (key: string, fallback: number) => {
      const n = Number(editForm[key]);
      return Number.isFinite(n) ? n : fallback;
    };
    const list = (key: string) => editForm[key].split(",").map((s) => s.trim()).filter(Boolean);
    const edits: Record<string, unknown> = {
      title: editForm.title,
      country: editForm.country,
      mode: editForm.mode,
      aspect_pack: editForm.aspect_pack,
      date_range_days: num("date_range_days", plan?.date_range_days || 90),
      max_videos: num("max_videos", 40),
      comments_per_video: num("comments_per_video", 60),
      comment_total_cap: num("comment_total_cap", 2000),
      keywords: list("keywords"),
      channels: list("channels"),
    };
    setBusy(true);
    try {
      const res = await api.put<{ plan: ResearchPlan; status: string }>(`/agent/plans/${planId}`, edits);
      setPlan(res.plan);
      setPlanStatus(res.status);
      setEditing(false);
    } finally {
      setBusy(false);
    }
  }

  const suggestions = [
    "Recommend a content strategy for a new cosmetics line",
    "What product should I promote first for Samsung phones in Pakistan?",
    "Give me campaign ideas for a beauty brand",
    "What do viewers say about Samsung phone prices in Pakistan?",
  ];

  return (
    <div className="flex h-[calc(100vh-8rem)] flex-col gap-3">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold">AI Research Agent</h1>
          <p className="text-xs text-muted-foreground">
            Chat for recommendations, or ask for live YouTube research — you approve before any data is collected.
          </p>
        </div>
        <div className="flex gap-2">
          {conversationId ? (
            <Select value={conversationId} onValueChange={(v) => loadConversation(v)}>
              <SelectTrigger className="w-44"><SelectValue placeholder="History" /></SelectTrigger>
              <SelectContent>
                <ConversationOptions current={conversationId} />
              </SelectContent>
            </Select>
          ) : null}
          <Button variant="outline" size="sm" onClick={newConversation}>
            <Plus className="mr-1 h-4 w-4" /> New
          </Button>
        </div>
      </div>

      <Card className="flex min-h-0 flex-1 flex-col py-0">
        <ScrollArea className="min-h-0 flex-1 p-4">
          <div className="space-y-3">
            {messages.length === 0 ? (
              <div className="flex flex-col items-center gap-4 py-10">
                <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-indigo-600 text-white">
                  <Bot className="h-6 w-6" />
                </div>
                <p className="max-w-md text-center text-sm text-muted-foreground">
                  Chat with me for recommendations based on your conversation. When you want live evidence,
                  ask for research and I will draft a plan for official YouTube data collection.
                </p>
                <div className="grid max-w-xl gap-2 sm:grid-cols-2">
                  {suggestions.map((s) => (
                    <button key={s} onClick={() => send(s)}
                      className="rounded-lg border px-3 py-2 text-left text-xs transition hover:border-indigo-500 hover:bg-indigo-50">
                      <Sparkles className="mr-1 inline h-3 w-3 text-indigo-600" />
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            ) : null}
            {messages.map((m) => (
              <div key={m.id} className={m.role === "user" ? "flex justify-end" : "flex justify-start"}>
                <div className={
                  m.role === "user"
                    ? "max-w-[85%] rounded-2xl rounded-br-sm bg-indigo-600 px-4 py-2 text-sm text-white"
                    : "max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-bl-sm border bg-white px-4 py-2 text-sm"
                }>
                  {m.role !== "user" && m.payload && (m.payload as Record<string, unknown>)["data_label"] ? (
                    <div className="mb-1"><LabelBadge label={String((m.payload as Record<string, unknown>)["data_label"])} /></div>
                  ) : null}
                  {m.content}
                  {m.role !== "user" && m.payload && (m.payload as Record<string, unknown>)["type"] === "recommendation" && Array.isArray((m.payload as Record<string, unknown>)["recommendations"]) ? (
                    <ul className="mt-2 list-disc space-y-1 pl-4 text-xs text-stone-700">
                      {((m.payload as Record<string, unknown>)["recommendations"] as string[]).map((r, i) => <li key={i}>{r}</li>)}
                    </ul>
                  ) : null}
                </div>
              </div>
            ))}

            {plan && !["executed", "cancelled", "canceled", "rejected"].includes(planStatus ?? "") ? (
              <Card className="border-indigo-200 bg-indigo-50/50">
                <CardContent className="space-y-2 p-4 text-xs">
                  {editing ? (
                    <div className="space-y-2">
                      <div className="flex items-center justify-between">
                        <p className="text-sm font-semibold">Edit research plan</p>
                        <LabelBadge label="USER INPUT" />
                      </div>
                      <div className="grid gap-2 sm:grid-cols-2">
                        <label className="space-y-1">
                          <span className="text-muted-foreground">Title</span>
                          <Input value={editForm.title} onChange={(e) => setEditField("title", e.target.value)} className="h-8 text-xs" />
                        </label>
                        <label className="space-y-1">
                          <span className="text-muted-foreground">Market</span>
                          <Input value={editForm.country} onChange={(e) => setEditField("country", e.target.value)} className="h-8 text-xs" />
                        </label>
                        <label className="space-y-1">
                          <span className="text-muted-foreground">Mode</span>
                          <Select value={editForm.mode} onValueChange={(v) => setEditField("mode", v)}>
                            <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
                            <SelectContent>
                              <SelectItem value="keyword">keyword</SelectItem>
                              <SelectItem value="channel">channel</SelectItem>
                            </SelectContent>
                          </Select>
                        </label>
                        <label className="space-y-1">
                          <span className="text-muted-foreground">Aspect pack</span>
                          <Select value={editForm.aspect_pack} onValueChange={(v) => setEditField("aspect_pack", v)}>
                            <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
                            <SelectContent>
                              <SelectItem value="product">product</SelectItem>
                              <SelectItem value="youtube_content">youtube_content</SelectItem>
                            </SelectContent>
                          </Select>
                        </label>
                        <label className="space-y-1">
                          <span className="text-muted-foreground">Recency days</span>
                          <Input type="number" min={1} max={3650} value={editForm.date_range_days} onChange={(e) => setEditField("date_range_days", e.target.value)} className="h-8 text-xs" />
                        </label>
                        <label className="space-y-1">
                          <span className="text-muted-foreground">Max videos</span>
                          <Input type="number" min={5} max={200} value={editForm.max_videos} onChange={(e) => setEditField("max_videos", e.target.value)} className="h-8 text-xs" />
                        </label>
                        <label className="space-y-1">
                          <span className="text-muted-foreground">Comments/video</span>
                          <Input type="number" min={10} max={500} value={editForm.comments_per_video} onChange={(e) => setEditField("comments_per_video", e.target.value)} className="h-8 text-xs" />
                        </label>
                        <label className="space-y-1">
                          <span className="text-muted-foreground">Comment cap</span>
                          <Input type="number" min={50} max={10000} value={editForm.comment_total_cap} onChange={(e) => setEditField("comment_total_cap", e.target.value)} className="h-8 text-xs" />
                        </label>
                      </div>
                      <label className="block space-y-1">
                        <span className="text-muted-foreground">Keywords (comma-separated)</span>
                        <Input value={editForm.keywords} onChange={(e) => setEditField("keywords", e.target.value)} className="h-8 text-xs" />
                      </label>
                      <label className="block space-y-1">
                        <span className="text-muted-foreground">Channels (comma-separated)</span>
                        <Input value={editForm.channels} onChange={(e) => setEditField("channels", e.target.value)} className="h-8 text-xs" />
                      </label>
                      <div className="flex gap-2 pt-1">
                        <Button size="sm" className="h-8 bg-indigo-600 hover:bg-indigo-700" onClick={saveEdits} disabled={busy || !planId}>Save</Button>
                        <Button size="sm" variant="outline" className="h-8" onClick={() => setEditing(false)}>Cancel</Button>
                      </div>
                    </div>
                  ) : (
                    <>
                      <div className="flex items-center justify-between">
                        <button type="button" onClick={startEditing} className="text-left text-sm font-semibold hover:text-indigo-700" title="Click to edit">{plan.title}</button>
                        <LabelBadge label="USER INPUT" />
                      </div>
                      <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-muted-foreground">
                        <span>Market: <button type="button" onClick={startEditing} className="font-medium text-foreground underline decoration-dotted underline-offset-2 hover:text-indigo-700">{plan.country}</button></span>
                        <span>Mode: <button type="button" onClick={startEditing} className="font-medium text-foreground underline decoration-dotted underline-offset-2 hover:text-indigo-700">{plan.mode}</button></span>
                        <span>Aspect pack: <button type="button" onClick={startEditing} className="font-medium text-foreground underline decoration-dotted underline-offset-2 hover:text-indigo-700">{plan.aspect_pack}</button></span>
                        <span>Recency: <button type="button" onClick={startEditing} className="font-medium text-foreground underline decoration-dotted underline-offset-2 hover:text-indigo-700">{plan.date_range_days} days</button></span>
                      </div>
                      <button type="button" onClick={startEditing} className="block w-full text-left text-muted-foreground hover:text-indigo-700">
                        <span className="font-medium text-foreground">Keywords:</span> {plan.keywords.map((k) => `“${k}”`).join(", ")}
                      </button>
                      {plan.channels.length ? (
                        <button type="button" onClick={startEditing} className="block w-full text-left text-muted-foreground hover:text-indigo-700">
                          <span className="font-medium text-foreground">Channels:</span> {plan.channels.join(", ")}
                        </button>
                      ) : null}
                      <button type="button" onClick={startEditing} className="block w-full text-left text-muted-foreground hover:text-indigo-700">
                        Collection: {plan.collection["max_videos"]} videos · {plan.collection["comments_per_video"]} comments/video
                        (cap {plan.collection["comment_total_cap"]}) · ~{plan.estimated_quota_units} quota units
                      </button>
                      <p className="text-[11px] leading-relaxed text-muted-foreground">{plan.methodology}</p>
                      <div className="flex gap-2 pt-1">
                        <Button size="sm" className="h-8 bg-indigo-600 hover:bg-indigo-700" onClick={approvePlan} disabled={busy}>
                          <Check className="mr-1 h-3 w-3" /> Approve &amp; execute
                        </Button>
                        <Button size="sm" variant="outline" className="h-8" onClick={startEditing} disabled={!planId}>
                          <Pencil className="mr-1 h-3 w-3" /> Edit plan
                        </Button>
                      </div>
                    </>
                  )}
                </CardContent>
              </Card>
            ) : null}

            {sessionId ? (
              <div className="rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-2 text-xs text-indigo-900">
                Research session <b>{sessionId.slice(0, 8)}</b> is running. Track it in the Research module —
                ask “what is the status?” any time.
              </div>
            ) : null}

            {busy ? (
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <Loader2 className="h-3 w-3 animate-spin" /> thinking…
              </div>
            ) : null}
            <div ref={bottomRef} />
          </div>
        </ScrollArea>
        <div className="border-t p-3">
          <form
            onSubmit={(e) => { e.preventDefault(); send(input); }}
            className="flex gap-2"
          >
            <Input value={input} onChange={(e) => setInput(e.target.value)}
              placeholder="Ask anything, or describe what you want to research…"
              disabled={busy} />
            <Button type="submit" size="icon" className="bg-indigo-600 hover:bg-indigo-700" disabled={busy || !input.trim()}>
              <Send className="h-4 w-4" />
            </Button>
          </form>
        </div>
      </Card>
    </div>
  );
}

function ConversationOptions({ current }: { current: string }) {
  const [convs, setConvs] = useState<Array<{ id: string; title: string }>>([]);
  useEffect(() => {
    api.get<{ conversations: Array<{ id: string; title: string }> }>("/agent/conversations")
      .then((d) => setConvs(d.conversations)).catch(() => setConvs([]));
  }, [current]);
  return (
    <>
      {convs.map((c) => (
        <SelectItem key={c.id} value={c.id}>{c.title.slice(0, 40)}</SelectItem>
      ))}
    </>
  );
}
