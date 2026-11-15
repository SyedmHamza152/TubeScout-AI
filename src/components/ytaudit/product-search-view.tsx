"use client";

import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api } from "@/lib/api";
import { Search } from "lucide-react";

function splitList(value: string) {
  return value.split(",").map((s) => s.trim()).filter(Boolean);
}

export function ProductSearchView({ onSessionStarted }: { onSessionStarted: (id: string) => void }) {
  const [title, setTitle] = useState("");
  const [product, setProduct] = useState("");
  const [country, setCountry] = useState("PK");
  const [mode, setMode] = useState("keyword");
  const [aspectPack, setAspectPack] = useState("product");
  const [days, setDays] = useState("365");
  const [maxVideos, setMaxVideos] = useState("40");
  const [commentsPerVideo, setCommentsPerVideo] = useState("60");
  const [commentCap, setCommentCap] = useState("2000");
  const [keywords, setKeywords] = useState("");
  const [channels, setChannels] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function buildKeywords() {
    const manual = splitList(keywords);
    if (manual.length) return manual.slice(0, 8);
    const p = product.trim();
    if (!p) return [];
    return [
      `${p} price`,
      `${p} review`,
      `${p} ${country.trim().toUpperCase()} price`,
      `${p} viewer comments`,
    ].slice(0, 8);
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    const kws = mode === "keyword" ? buildKeywords() : splitList(keywords);
    const chs = splitList(channels);
    if (mode === "keyword" && !kws.length) {
      setError("Enter keywords or a product name so keywords can be generated.");
      return;
    }
    if (mode === "channel" && !chs.length) {
      setError("Enter at least one channel name, handle, or URL.");
      return;
    }
    const finalTitle = title.trim() || `YouTube research — ${product.trim() || kws[0] || chs[0] || "product"} (${country.trim().toUpperCase() || "global"})`;
    setBusy(true);
    try {
      const res = await api.post<{ id: string }>("/research/sessions", {
        title: finalTitle.slice(0, 300),
        product: product.trim(),
        description: "",
        keywords: kws,
        channels: chs,
        mode,
        country: country.trim().toUpperCase() || "PK",
        language: "",
        published_after_days: Math.max(1, Math.min(3650, parseInt(days) || 365)),
        max_videos: Math.max(5, Math.min(200, parseInt(maxVideos) || 40)),
        comments_per_video: Math.max(10, Math.min(500, parseInt(commentsPerVideo) || 60)),
        comment_total_cap: Math.max(50, Math.min(10000, parseInt(commentCap) || 2000)),
        aspect_pack: aspectPack,
        research_intent: aspectPack === "youtube_content" ? "content" : "product",
      });
      onSessionStarted(res.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start product research.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-bold">Product Search</h1>
        <p className="text-xs text-muted-foreground">Manual product research — official YouTube Data API v3 only</p>
      </div>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-sm">
            <Search className="h-4 w-4 text-indigo-600" /> What do viewers say about this product?
          </CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={submit} className="space-y-3">
            <div className="grid gap-3 md:grid-cols-2">
              <div className="space-y-1.5 md:col-span-2">
                <label className="text-xs font-medium">Title <span className="text-muted-foreground">(optional)</span></label>
                <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Viewer opinions on Samsung phone prices in Pakistan" />
              </div>
              <div className="space-y-1.5">
                <label className="text-xs font-medium">Product / business</label>
                <Input value={product} onChange={(e) => setProduct(e.target.value)} placeholder="Samsung phone prices in Pakistan" />
              </div>
              <div className="space-y-1.5">
                <label className="text-xs font-medium">Market</label>
                <Input value={country} onChange={(e) => setCountry(e.target.value)} placeholder="PK" />
              </div>
              <div className="space-y-1.5">
                <label className="text-xs font-medium">Mode</label>
                <Select value={mode} onValueChange={setMode}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="keyword">keyword</SelectItem>
                    <SelectItem value="channel">channel</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <label className="text-xs font-medium">Aspect pack</label>
                <Select value={aspectPack} onValueChange={setAspectPack}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="product">product</SelectItem>
                    <SelectItem value="youtube_content">youtube_content</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <label className="text-xs font-medium">Recency days</label>
                <Input type="number" min={1} max={3650} value={days} onChange={(e) => setDays(e.target.value)} />
              </div>
              <div className="space-y-1.5">
                <label className="text-xs font-medium">Max videos</label>
                <Input type="number" min={5} max={200} value={maxVideos} onChange={(e) => setMaxVideos(e.target.value)} />
              </div>
              <div className="space-y-1.5">
                <label className="text-xs font-medium">Comments/video</label>
                <Input type="number" min={10} max={500} value={commentsPerVideo} onChange={(e) => setCommentsPerVideo(e.target.value)} />
              </div>
              <div className="space-y-1.5">
                <label className="text-xs font-medium">Comment cap</label>
                <Input type="number" min={50} max={10000} value={commentCap} onChange={(e) => setCommentCap(e.target.value)} />
              </div>
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-medium">Keywords (comma-separated)</label>
              <Input value={keywords} onChange={(e) => setKeywords(e.target.value)} placeholder={mode === "keyword" ? "Samsung phone price Pakistan, Samsung price in Pakistan, Samsung mobile price PK" : "optional for channel mode"} />
              <p className="text-[11px] text-muted-foreground">Leave empty to auto-generate keywords from the product name.</p>
            </div>
            <div className="space-y-1.5">
              <label className="text-xs font-medium">Channels (comma-separated)</label>
              <Input value={channels} onChange={(e) => setChannels(e.target.value)} placeholder="required for channel mode — channel name, @handle, or URL" />
            </div>

            {error ? <p className="text-xs text-red-600">{error}</p> : null}
            <Button type="submit" className="bg-indigo-600 hover:bg-indigo-700" disabled={busy}>
              <Search className="mr-1 h-4 w-4" /> {busy ? "Starting research…" : "Search product on YouTube"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
