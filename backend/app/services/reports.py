"""PDF research report generator (ReportLab)."""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics.competitors import compare_workspace_channels
from app.analytics.sentiment_stats import aspect_summary, session_summary
from app.core.config import settings
from app.models.audience import AnomalyDetection, AudienceCluster
from app.models.campaign import Finding
from app.models.identity import Workspace
from app.models.research import ResearchSession, TopicRecord, TrackedVideo

logger = logging.getLogger(__name__)


def generate_pdf_report(db: Session, ws: Workspace, session_id: str) -> tuple[Path, int]:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import HRFlowable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    session = db.get(ResearchSession, session_id)
    summary = session_summary(db, session)
    aspects = aspect_summary(db, session, (session.config or {}).get("aspect_pack", "product"))
    topics = db.execute(select(TopicRecord).where(TopicRecord.session_id == session_id)
                        .order_by(TopicRecord.comment_count.desc()).limit(8)).scalars().all()
    clusters = db.execute(select(AudienceCluster).where(AudienceCluster.session_id == session_id)
                          .order_by(AudienceCluster.size.desc())).scalars().all()
    anomalies = db.execute(select(AnomalyDetection).where(AnomalyDetection.session_id == session_id)
                           .order_by(AnomalyDetection.score.desc()).limit(8)).scalars().all()
    findings = db.execute(select(Finding).where(Finding.session_id == session_id)
                          .order_by(Finding.id.desc())).scalars().all()
    videos = db.execute(select(TrackedVideo).where(TrackedVideo.session_id == session_id)
                        .order_by(TrackedVideo.views.desc()).limit(10)).scalars().all()
    competitors = compare_workspace_channels(db, ws.id, session_id)

    out_dir = Path(settings.DATA_DIR if hasattr(settings, "DATA_DIR") else "data") / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"report_{session_id[:8]}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"

    doc = SimpleDocTemplate(str(path), pagesize=A4, topMargin=18 * mm, bottomMargin=16 * mm)
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("H1", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=20, spaceAfter=4)
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=13, spaceBefore=10, spaceAfter=4)
    body = ParagraphStyle("Body", parent=styles["BodyText"], fontSize=9.5, leading=13)
    small = ParagraphStyle("Small", parent=body, fontSize=8, textColor=colors.HexColor("#555555"))
    accent = colors.HexColor("#0F766E")

    story = []
    story.append(Paragraph("AudienceLens — YouTube Audience & Campaign Intelligence", h1))
    story.append(Paragraph(f"Research report: {session.title}", ParagraphStyle("sub", parent=body, fontSize=11)))
    story.append(Spacer(1, 4))
    so = summary.get("sentiment_overall", {})
    story.append(Paragraph(
        f"Sample: {so.get('total', 0)} public comments from {(session.stats or {}).get('videos_found', 0)} videos "
        f"(mode: {session.mode}; market: {(session.config or {}).get('country') or '—'}). "
        f"Status: {session.status}. Generated: {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}.", small))
    story.append(HRFlowable(width="100%", color=accent, thickness=1))
    story.append(Paragraph(
        "All figures describe the collected sample of public YouTube data (LIVE DATA). They are NOT "
        "advertising performance, and not the entire YouTube audience.", small))

    # sentiment
    story.append(Paragraph("1. Sentiment overview", h2))
    story.append(Paragraph(
        f"Positive {so.get('positive_pct')}% · Negative {so.get('negative_pct')}% · Neutral {so.get('neutral_pct')}% · "
        f"Mixed {so.get('mixed_pct')}% · Uncertain {so.get('uncertain_pct')}% · mean score {so.get('avg_score')}", body))
    langs = summary.get("languages", [])[:5]
    if langs:
        story.append(Paragraph("Language mix: " + ", ".join(
            f"{l['language']} {l['total']}" for l in langs), body))
    intents = summary.get("intents", [])[:5]
    if intents:
        story.append(Paragraph("Intent signals: " + ", ".join(
            f"{i['label']} {i['count']}" for i in intents), body))

    # aspects
    if aspects.get("aspects"):
        story.append(Paragraph("2. Aspect-based sentiment", h2))
        rows = [["Aspect", "Mentions", "Positive %", "Negative %"]]
        rows += [[a["label"], str(a["mentions"]), str(a["positive_pct"]), str(a["negative_pct"])]
                 for a in aspects["aspects"][:8]]
        t = Table(rows, colWidths=[70 * mm, 25 * mm, 30 * mm, 30 * mm])
        t.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CCCCCC")),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E6F4F1")),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
        ]))
        story.append(t)
        story.append(Paragraph(f"Aspect pack: {aspects.get('pack_label')} — selected by research topic.", small))

    # topics
    if topics:
        story.append(Paragraph("3. Discussion topics", h2))
        story.append(Paragraph(" · ".join(f"{t.label} ({t.comment_count})" for t in topics[:6]), body))

    # clusters
    if clusters:
        story.append(Paragraph("4. Audience segments (INFERENCE)", h2))
        story.append(Paragraph(
            f"K-Means clustering (k={clusters[0].k}, silhouette {clusters[0].silhouette}) over author-level "
            "behavioural features produced the following analytical segments — behaviour patterns of "
            "public commenters, NOT verified demographics:", body))
        for c in clusters[:6]:
            story.append(Paragraph(
                f"<b>{c.label}</b> — {c.size} commenters; negative share {c.profile.get('neg_share')}; "
                f"purchase-intent rate {c.profile.get('intent_purchase_intent')}", body))

    # competitors
    profs = competitors.get("channels", [])[:8]
    if len(profs) >= 2:
        story.append(Paragraph("5. Channel comparison", h2))
        rows = [["Channel", "Videos", "Median views", "Engagement", "Shorts share", "Negative %"]]
        rows += [[p["channel_title"][:28], str(p["videos_in_research"]), f"{p['median_views']:,.0f}",
                  f"{p['avg_engagement_rate']:.4f}", f"{p['shorts_share']:.0%}", str(p["negative_pct"])]
                 for p in profs]
        t = Table(rows, colWidths=[42 * mm, 18 * mm, 28 * mm, 28 * mm, 24 * mm, 22 * mm])
        t.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CCCCCC")),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E6F4F1")),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
        ]))
        story.append(t)

    # anomalies
    if anomalies:
        story.append(Paragraph("6. Unusual patterns", h2))
        for a in anomalies[:6]:
            story.append(Paragraph(f"<b>{a.kind}</b> ({a.severity}) — {a.entity_title[:70]}: {a.explanation}", body))

    # findings
    if findings:
        story.append(Paragraph("7. Findings & recommended actions", h2))
        for f in findings[:10]:
            story.append(Paragraph(f"<b>{f.title}</b> [{f.data_label}, confidence {f.confidence:.2f}]", body))
            story.append(Paragraph(f.description, body))
            if f.recommended_action:
                story.append(Paragraph(f"<b>Recommended action:</b> {f.recommended_action}", body))
            story.append(Spacer(1, 4))

    story.append(Paragraph("Methodology & limitations", h2))
    story.append(Paragraph(
        "Collection: official YouTube Data API v3 (search/playlistItems/videos/channels/commentThreads) with "
        "region/recency filters; public comments only. Analysis: language detection (EN/Roman Urdu/Urdu/mixed), "
        "lexicon+clause sentiment with negation/intensifiers/mixed/sarcasm heuristics and uncertainty flagging; "
        "aspect-based sentiment with topic-selected pack; rule-based trilingual intent detection; TF-IDF topic "
        "clustering; K-Means audience clustering over behavioural features; robust-z / binomial-z / "
        "IsolationForest anomaly detection. Limitations: comment samples are capped and skewed toward "
        "engaged viewers; sentiment rules are transparent but not transformer-grade; segments are behavioural "
        "inferences; organic statistics never represent ad performance.", body))

    doc.build(story)
    return path, path.stat().st_size
