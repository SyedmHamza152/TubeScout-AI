// Shared types for TubeScout AI frontend
export interface UserInfo { id: string; email: string; name: string; }
export interface WorkspaceInfo { id: string; name: string; market: string; currency: string; }

export interface SessionStats {
  videos_found?: number; comments_stored?: number; comments_duplicate?: number;
  quota_spent?: number; comments_disabled_videos?: number;
  analytics?: Record<string, unknown>;
}
export interface ResearchSession {
  id: string; title: string; mode: string; status: string; stage: string;
  progress: number; stats?: SessionStats; error?: string | null; data_label: string;
  created_at: string; completed_at?: string | null; running?: boolean; config?: Record<string, unknown>;
}
export interface SentimentMix {
  total: number; positive_pct: number; negative_pct: number; neutral_pct: number;
  mixed_pct: number; uncertain_pct: number; avg_score: number;
  counts?: Record<string, number>;
}
export interface VideoRow {
  video_id: string; title: string; channel_title: string; channel_id: string;
  published_at: string | null; duration_seconds: number; content_type: string;
  views: number; likes: number; comment_count: number; engagement_rate: number;
  matched_keyword: string; url: string; data_label: string;
}
export interface CommentRow {
  comment_id: string; video_id: string; author: string; text: string; translation?: string | null;
  language: string; sentiment: string; sentiment_score: number; sentiment_confidence: number;
  sarcasm_suspect: boolean; intents: Record<string, boolean>; like_count: number;
  reply_count: number; published_at: string | null; url: string | null; is_spam: boolean;
  data_label: string;
}
export interface AspectRow { aspect: string; label: string; scope: string; mentions: number; positive_pct: number; negative_pct: number; neutral_pct: number; }
export interface TopicRow { topic_key: string; label: string; keywords: string[]; comment_count: number; share: number; sentiment_mix: Record<string, number>; }
export interface LanguageMix extends SentimentMix { language: string; }
export interface IntentRow { intent: string; label: string; count: number; share_pct: number; }
export interface Analytics {
  summary: {
    sentiment_overall: SentimentMix; languages: LanguageMix[]; intents: IntentRow[];
    videos: Array<Record<string, unknown>>; trend: Array<{ date: string } & SentimentMix>;
    representative: { positive: EvidenceComment[]; negative: EvidenceComment[] };
    sample_disclaimer: string; data_label: string;
  };
  aspects: { pack: string; pack_label: string; aspects: AspectRow[] };
  topics: TopicRow[];
  session: { id: string; title: string; status: string };
}
export interface EvidenceComment { comment_id: string; text: string; like_count: number; language: string; video_title: string; url: string | null; sentiment: string; }
export interface Cluster {
  id: number; cluster_index: number; label: string; size: number; method: string;
  k: number; silhouette: number; profile: Record<string, number | string>;
  data_label: string; example_authors: Array<{ comment_count: number }>;
}
export interface Anomaly {
  id: number; kind: string; entity_type: string; entity_id: string; entity_title: string;
  score: number; severity: string; baseline: Record<string, unknown>;
  observed: Record<string, unknown>; explanation: string;
  evidence: Array<Record<string, unknown>>; data_label: string; detected_at: string;
}
export interface CompetitorProfile {
  channel_id: string; channel_title: string; videos_in_research: number;
  median_views: number; avg_engagement_rate: number; shorts_share: number;
  upload_cadence_per_week: number; comments_collected: number;
  negative_pct: number; positive_pct: number; data_label: string;
}
export interface TrackedChannelRow {
  channel_id: string; title: string; handle: string; subscribers: number;
  video_count: number; is_competitor: boolean; country: string;
  last_synced_at: string | null; data_label: string;
}
export interface Allocation {
  format_key: string; label: string; share: number; amount: number;
  predicted: Record<string, number | null>; confidence: number;
  reason: string; fit_factors: Record<string, number>;
}
export interface BudgetRun {
  id: number; strategy: string; total_budget: number; currency: string; objective: string;
  cold_start: boolean; confidence: number; algorithm: string; methodology: string;
  source_label: string; predicted_totals: Record<string, number | null>;
  meta: Record<string, unknown>; created_at: string; allocations: Allocation[];
  disclaimer: string;
}
export interface Finding {
  id: number; category: string; title: string; description: string;
  metrics: Record<string, unknown>; evidence: Array<Record<string, unknown>>;
  methodology: string; confidence: number; limitations: string;
  recommended_action: string; data_label: string;
  period_start?: string | null; period_end?: string | null;
}
export interface ChatMessage {
  id: number; role: string; content: string; payload: Record<string, unknown>; created_at: string;
}
export interface ResearchPlan {
  title: string; business: string; country: string; industry: string;
  research_intent: string; mode: string; keywords: string[]; channels: string[];
  filters: Record<string, string>; collection: Record<string, number>;
  aspect_pack: string; date_range_days: number; estimated_quota_units: number; methodology: string;
}
export interface QuotaStatus {
  used_today: number; limit: number; remaining: number;
  by_endpoint: Record<string, number>; last_14_days: Record<string, number>;
}
export interface Finding2 { title: string; category: string; metrics: Record<string, unknown>; action: string; }
export interface EvidencePack {
  session: { id: string; title: string; status: string; collected_comments?: number; videos_found?: number };
  sentiment?: SentimentMix;
  segments: Array<{ label: string; size: number; neg_share?: number; purchase_intent?: number }>;
  findings: Finding2[];
}
