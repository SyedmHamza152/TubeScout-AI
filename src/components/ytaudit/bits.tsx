"use client";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export function LabelBadge({ label, className }: { label: string; className?: string }) {
  const styles: Record<string, string> = {
    "LIVE DATA": "bg-emerald-100 text-emerald-800 border-emerald-300",
    "MODEL PREDICTION": "bg-violet-100 text-violet-800 border-violet-300",
    "ESTIMATED SCENARIO": "bg-amber-100 text-amber-800 border-amber-300",
    INFERENCE: "bg-sky-100 text-sky-800 border-sky-300",
    "USER INPUT": "bg-stone-100 text-stone-700 border-stone-300",
    "INSUFFICIENT DATA": "bg-red-100 text-red-800 border-red-300",
  };
  return (
    <Badge variant="outline" className={cn("text-[10px] font-semibold tracking-wide", styles[label] ?? "", className)}>
      {label}
    </Badge>
  );
}

export function SentimentBadge({ sentiment }: { sentiment: string }) {
  const styles: Record<string, string> = {
    positive: "bg-emerald-100 text-emerald-800",
    negative: "bg-red-100 text-red-800",
    neutral: "bg-stone-100 text-stone-700",
    mixed: "bg-amber-100 text-amber-800",
    uncertain: "bg-sky-100 text-sky-800",
  };
  return <Badge className={cn("text-[11px]", styles[sentiment] ?? "")}>{sentiment}</Badge>;
}

export function StatCard({ title, value, sub, className }: { title: string; value: string | number; sub?: string; className?: string }) {
  return (
    <Card className={cn("py-4", className)}>
      <CardHeader className="pb-1">
        <CardTitle className="text-xs font-medium text-muted-foreground">{title}</CardTitle>
      </CardHeader>
      <CardContent className="pb-1">
        <div className="text-2xl font-bold tabular-nums">{value}</div>
        {sub ? <div className="mt-0.5 text-xs text-muted-foreground">{sub}</div> : null}
      </CardContent>
    </Card>
  );
}

export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-lg border border-dashed px-6 py-12 text-center">
      <p className="text-sm font-medium">{title}</p>
      {hint ? <p className="mt-1 max-w-md text-xs text-muted-foreground">{hint}</p> : null}
    </div>
  );
}

export function Disclaimer({ children }: { children: React.ReactNode }) {
  return (
    <p className="rounded-md border border-stone-200 bg-stone-50 px-3 py-2 text-[11px] leading-relaxed text-stone-600">
      {children}
    </p>
  );
}
