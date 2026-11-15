"""Budget optimizer service — evidence assembly and run persistence.

Evidence sources (strict policy):
  1. Cold-start priors  — documented PKR assumptions (app/optimization/coldstart.py),
     used as ESTIMATED SCENARIO anchors, blended transparently with real evidence.
  2. ACTUAL Google Ads campaign history — only when a workspace connection is
     authorized and synced (LIVE DATA). Organic YouTube stats are NEVER used
     as advertising performance history.
  3. Live research signal — shorts share / short-vs-long engagement from the
     session's collected videos adjusts format fit (organic signal, labeled).

The optimizer recommends; it never spends money or modifies campaigns.
"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import (
    LABEL_ESTIMATE,
    LABEL_LIVE,
    MARKETING_OBJECTIVES,
    SUPPORTED_FORMATS,
)
from app.models.campaign import (
    AdsCampaign,
    AdsCampaignPerformance,
    BudgetAllocation,
    BudgetRun,
    CampaignBrief,
    GoogleConnection,
)
from app.optimization import engine as opt_engine
from app.optimization.coldstart import AOV_BY_BAND, FORMAT_PRIORS
from app.services.knowledge import FORMAT_OBJECTIVE_FIT, classify_category
from app.services.metrics import MetricSet, merge_metric_sets

logger = logging.getLogger(__name__)

PSEUDO_COUNT_PARAMS = 200_000.0
MIN_SAMPLE_FOR_TRUST = 30_000


def live_history_by_format(db: Session, workspace_id: str) -> dict[str, dict]:
    """Aggregate ACTUAL synced Google Ads performance per format (LIVE only)."""
    rows = db.execute(
        select(AdsCampaignPerformance, AdsCampaign)
        .join(AdsCampaign, AdsCampaignPerformance.campaign_pk == AdsCampaign.id)
        .where(AdsCampaign.workspace_id == workspace_id,
               AdsCampaignPerformance.data_label == LABEL_LIVE)
        .order_by(AdsCampaignPerformance.date.desc())
        .limit(200_000)
    ).all()
    by_format: dict[str, list[MetricSet]] = {}
    for perf, camp in rows:
        ms = MetricSet(
            impressions=perf.impressions,
            clicks=perf.clicks,
            cost=perf.cost_micros / 1_000_000.0,
            conversions=perf.conversions,
            conversion_value=perf.conversion_value,
            video_views=perf.video_views,
            video_impressions=perf.impressions,
            source="live",
        )
        by_format.setdefault(camp.format_key, []).append(ms)
    out: dict[str, dict] = {}
    for key, sets in by_format.items():
        merged = merge_metric_sets(sets)
        out[key] = {"metrics": merged.to_dict(), "sample_size": int(merged.impressions), "source": "live"}
    return out


def _blend(prior: float, historical: float | None, n_hist: float,
           clamp: tuple[float, float] | None = None) -> float:
    num = PSEUDO_COUNT_PARAMS * prior
    den = PSEUDO_COUNT_PARAMS
    if historical is not None and n_hist > 0:
        num += n_hist * historical
        den += n_hist
    val = num / den
    if clamp:
        val = min(max(val, clamp[0]), clamp[1])
    return val


def research_fit_for(format_key: str, videos: list[dict]) -> tuple[float, str]:
    """Live-niche multiplier from REAL collected videos (or neutral 1.0)."""
    if not videos:
        return 1.0, ""
    usable = [v for v in videos if (v.get("views") or 0) > 0 and v.get("duration_seconds", 0) > 0]
    if len(usable) < 5:
        return 1.0, ""
    n = len(usable)
    shorts_rows = [v for v in usable if v["duration_seconds"] <= 65]
    long_rows = [v for v in usable if v["duration_seconds"] > 65]
    shorts_share = len(shorts_rows) / n

    def _med_eng(rows: list[dict]) -> float | None:
        vals = sorted((v.get("engagement_rate") or 0.0) for v in rows)
        if not vals or max(vals) <= 0:
            return None
        m = vals[len(vals) // 2] if len(vals) % 2 else (vals[len(vals) // 2 - 1] + vals[len(vals) // 2]) / 2
        return m

    eng_short, eng_long = _med_eng(shorts_rows), _med_eng(long_rows)
    advantage = 0.0
    if eng_short is not None and eng_long:
        advantage = max(-1.0, min(1.0, (eng_short - eng_long) / max(eng_long, 1e-9)))
    elif eng_short is not None and not long_rows:
        advantage = 0.5

    raw = {
        "shorts": 0.92 + 0.40 * shorts_share + 0.18 * advantage,
        "in_stream": 1.06 - 0.30 * shorts_share - 0.12 * advantage,
        "in_feed": 1.02 - 0.10 * shorts_share,
    }
    mean = sum(raw.values()) / 3.0
    fit = raw[format_key] / mean

    bits = [f"live niche signal: {shorts_share * 100:.0f}% of {n} collected public videos are Shorts-length"]
    if advantage != 0.0:
        direction = "above" if advantage > 0 else "below"
        bits.append(f"short-form engagement {abs(advantage) * 100:.0f}% {direction} long-form")
    note = ", ".join(bits) + " (LIVE DATA)"
    return fit, note


def session_videos_for_fit(db: Session, session_id: str | None) -> list[dict]:
    if not session_id:
        return []
    from app.models.research import TrackedVideo

    rows = db.execute(
        select(TrackedVideo).where(TrackedVideo.session_id == session_id)
    ).scalars().all()
    return [{
        "views": r.views, "likes": r.likes, "comments": r.comment_count,
        "duration_seconds": r.duration_seconds, "engagement_rate": r.engagement_rate,
        "title": r.title,
    } for r in rows]


def build_format_scores(brief: CampaignBrief, history: dict[str, dict],
                        research_videos: list[dict]) -> list[opt_engine.FormatScore]:
    text = f"{brief.product} {brief.description}"
    profile, _conf = classify_category(text)
    aov_band = (brief.total_budget and (brief.total_budget < 5000 and "low") or "medium") or "medium"
    aov = AOV_BY_BAND.get(aov_band, AOV_BY_BAND["medium"])
    objective = brief.objective if brief.objective in MARKETING_OBJECTIVES else "Sales / Conversions"

    # audience age signal from the brief (USER INPUT), not fabricated demographics
    young_audience = any(k in (brief.target_audience or "").lower()
                         for k in ("young", "gen z", "student", "teen", "18-24", "25-34"))
    young_share = 0.65 if young_audience else 0.35

    scores: list[opt_engine.FormatScore] = []
    for key, label in SUPPORTED_FORMATS.items():
        if brief.preferred_formats and key not in brief.preferred_formats:
            continue
        prior = FORMAT_PRIORS[key]
        hist = history.get(key)
        hist_m = hist["metrics"] if hist else None
        n_hist = float(hist["sample_size"]) if hist else 0.0

        unit_cost = _blend(
            prior.unit_cost,
            (hist_m.get("cpv") if prior.pricing_model == "cpv" else hist_m.get("cpc")) if hist_m else None,
            n_hist, clamp=(0.15, 60.0),
        )
        view_rate = _blend(prior.view_rate, (hist_m.get("view_rate") / 100.0 if hist_m and hist_m.get("view_rate") else None),
                           n_hist, clamp=(0.08, 0.55)) if prior.pricing_model == "cpv" else 0.0
        click_rate = _blend(
            prior.click_rate,
            (_ctr_of_views(hist_m) if prior.pricing_model == "cpv" else (hist_m.get("ctr") / 100.0 if hist_m and hist_m.get("ctr") else None)),
            n_hist, clamp=(0.002, 0.5),
        )
        cvr = _blend(prior.cvr, (hist_m.get("conversion_rate") / 100.0 if hist_m and hist_m.get("conversion_rate") else None),
                     n_hist, clamp=(0.001, 0.25))
        aov_eff = aov
        if hist_m and hist_m.get("conversions") and hist_m["conversions"] > 0 and hist_m.get("conversion_value", 0) > 0:
            aov_eff = hist_m["conversion_value"] / hist_m["conversions"]

        if key == "shorts":
            audience_fit = 0.75 + 0.55 * young_share
        elif key == "in_stream":
            audience_fit = 1.20 - 0.30 * young_share
        else:
            audience_fit = 1.05 - 0.10 * young_share
        objective_fit = FORMAT_OBJECTIVE_FIT[key].get(objective, 1.0)
        category_fit = profile.format_affinity.get(key, 1.0)
        research_fit, research_note = research_fit_for(key, research_videos)

        risk = prior.risk * (1.0 - min(n_hist / 200_000.0, 0.5) * 0.6)
        confidence = 0.72 if (hist and n_hist >= MIN_SAMPLE_FOR_TRUST) else 0.35

        evidence = []
        if hist and n_hist > 0:
            evidence.append(
                f"actual Google Ads history: CTR {hist_m['ctr']:.2f}%, "
                f"{'CPV' if prior.pricing_model == 'cpv' else 'CPC'} {unit_cost:.2f}, CVR {cvr * 100:.2f}%"
            )
        if research_note:
            evidence.append(research_note)
        if not evidence:
            evidence.append("cold-start priors (documented assumptions; ESTIMATED SCENARIO)")

        scores.append(opt_engine.FormatScore(
            format_key=key,
            label=label,
            pricing_model=prior.pricing_model,
            unit_cost=round(unit_cost, 4),
            view_rate=round(view_rate, 4),
            click_rate=round(click_rate, 5),
            cvr=round(cvr, 5),
            aov=round(aov_eff, 2),
            objective=objective,
            audience_fit=round(audience_fit, 3),
            objective_fit=round(objective_fit, 3),
            category_fit=round(category_fit, 3),
            research_fit=round(research_fit, 3),
            risk=round(risk, 3),
            sample_size=int(n_hist),
            confidence=confidence,
            data_source_label=LABEL_LIVE if (hist and n_hist > 0) else LABEL_ESTIMATE,
            evidence=evidence,
        ))
    return scores


def _ctr_of_views(hist_m: dict) -> float | None:
    if not hist_m or not hist_m.get("video_views"):
        return None
    return hist_m["clicks"] / hist_m["video_views"]


def run_budget_optimization(db: Session, workspace_id: str, brief: CampaignBrief,
                            strategy: str = "balanced") -> BudgetRun:
    history = live_history_by_format(db, workspace_id)
    cold_start = not history or all(h["sample_size"] < MIN_SAMPLE_FOR_TRUST for h in history.values())
    research_videos = session_videos_for_fit(db, brief.session_id)
    scores = build_format_scores(brief, history, research_videos)
    if not scores:
        raise ValueError("No eligible ad formats for this brief (check preferred formats).")

    result = opt_engine.optimize_budget(
        total_budget=brief.total_budget, scores=scores,
        strategy=strategy, cold_start=cold_start,
    )

    live_sources = [h["source"] for h in history.values() if h["sample_size"] > 0]
    source_label = LABEL_LIVE if (live_sources and all(s == "live" for s in live_sources)) else LABEL_ESTIMATE

    run = BudgetRun(
        brief_id=brief.id, workspace_id=workspace_id, strategy=strategy,
        total_budget=brief.total_budget, currency=brief.currency,
        objective=brief.objective, cold_start=cold_start,
        confidence=result.confidence, algorithm=result.algorithm,
        methodology=result.methodology, source_label=source_label,
        meta=result.meta, predicted_totals=result.predicted_totals,
    )
    db.add(run)
    db.flush()
    for a in result.allocations:
        db.add(BudgetAllocation(
            run_id=run.id, format_key=a.format_key, label=a.label,
            share=a.share, amount=a.amount, predicted=a.predicted,
            confidence=a.confidence, reason=a.reason, fit_factors=a.fit_factors,
        ))
    db.commit()
    db.refresh(run)
    return run


def compare_scenarios(db: Session, workspace_id: str, brief: CampaignBrief) -> dict:
    runs = []
    for strategy in ("balanced", "performance", "exploratory"):
        runs.append(run_budget_optimization(db, workspace_id, brief, strategy))
    return {"runs": runs}
