"""Audience intelligence endpoints: clusters + anomalies."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audience.anomalies import detect_session_anomalies
from app.audience.clustering import cluster_session
from app.core.db import get_db
from app.core.deps import get_current_user, get_workspace
from app.models.identity import User, Workspace
from app.models.audience import AnomalyDetection, AudienceCluster, ClusterMember
from app.models.research import ResearchSession

router = APIRouter(prefix="/audience", tags=["audience"])


def _own_session(db: Session, ws_id: str, session_id: str) -> ResearchSession:
    s = db.get(ResearchSession, session_id)
    if s is None or s.workspace_id != ws_id:
        raise HTTPException(404, "Research session not found.")
    return s


@router.get("/clusters/{session_id}")
def list_clusters(session_id: str, user: User = Depends(get_current_user),
                  ws: Workspace = Depends(get_workspace), db: Session = Depends(get_db)):
    _own_session(db, ws.id, session_id)
    rows = db.execute(
        select(AudienceCluster).where(AudienceCluster.session_id == session_id)
        .order_by(AudienceCluster.size.desc())
    ).scalars().all()
    out = []
    for c in rows:
        example_members = db.execute(
            select(ClusterMember).where(ClusterMember.cluster_id == c.id)
            .order_by(ClusterMember.comment_count.desc()).limit(5)
        ).scalars().all()
        out.append({
            "id": c.id, "cluster_index": c.cluster_index, "label": c.label, "size": c.size,
            "method": c.method, "k": c.k, "silhouette": c.silhouette,
            "profile": c.profile, "data_label": c.data_label,
            "example_authors": [{"comment_count": m.comment_count} for m in example_members],
        })
    if not rows:
        return {"clusters": [], "note": "No clusters yet — run the clustering analysis for this session."}
    return {"clusters": out}


@router.post("/clusters/{session_id}/run")
def run_clustering(session_id: str, user: User = Depends(get_current_user),
                   ws: Workspace = Depends(get_workspace), db: Session = Depends(get_db)):
    _own_session(db, ws.id, session_id)
    result = cluster_session(db, ws.id, session_id)
    if result.get("clusters", 0) == 0:
        return {"ok": False, "reason": result.get("reason", "clustering produced no results")}
    return {"ok": True, **result}


@router.get("/anomalies/{session_id}")
def list_anomalies(session_id: str, user: User = Depends(get_current_user),
                   ws: Workspace = Depends(get_workspace), db: Session = Depends(get_db)):
    _own_session(db, ws.id, session_id)
    rows = db.execute(
        select(AnomalyDetection).where(AnomalyDetection.session_id == session_id)
        .order_by(AnomalyDetection.detected_at.desc())
    ).scalars().all()
    return {"anomalies": [{
        "id": a.id, "kind": a.kind, "entity_type": a.entity_type, "entity_id": a.entity_id,
        "entity_title": a.entity_title, "score": a.score, "severity": a.severity,
        "baseline": a.baseline, "observed": a.observed, "explanation": a.explanation,
        "evidence": a.evidence, "data_label": a.data_label,
        "detected_at": str(a.detected_at),
    } for a in rows]}


@router.post("/anomalies/{session_id}/run")
def run_anomalies(session_id: str, user: User = Depends(get_current_user),
                  ws: Workspace = Depends(get_workspace), db: Session = Depends(get_db)):
    _own_session(db, ws.id, session_id)
    result = detect_session_anomalies(db, ws.id, session_id)
    return {"ok": True, **result}
