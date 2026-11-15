"""Findings & reports endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics.findings import build_findings
from app.core.db import get_db
from app.core.deps import get_current_user, get_workspace
from app.models.campaign import Finding, GeneratedReport
from app.models.identity import User, Workspace
from app.services.reports import generate_pdf_report

router = APIRouter(prefix="/findings", tags=["findings"])


@router.get("/{session_id}")
def list_findings(session_id: str, user: User = Depends(get_current_user),
                  ws: Workspace = Depends(get_workspace), db: Session = Depends(get_db)):
    rows = db.execute(
        select(Finding).where(Finding.workspace_id == ws.id, Finding.session_id == session_id)
        .order_by(Finding.created_at.desc())
    ).scalars().all()
    return {"findings": [{
        "id": f.id, "category": f.category, "title": f.title, "description": f.description,
        "metrics": f.metrics, "evidence": f.evidence, "methodology": f.methodology,
        "confidence": f.confidence, "limitations": f.limitations,
        "recommended_action": f.recommended_action, "data_label": f.data_label,
        "period_start": str(f.period_start) if f.period_start else None,
        "period_end": str(f.period_end) if f.period_end else None,
    } for f in rows]}


@router.post("/{session_id}/run")
def run(session_id: str, user: User = Depends(get_current_user),
        ws: Workspace = Depends(get_workspace), db: Session = Depends(get_db)):
    result = build_findings(db, ws.id, session_id)
    return {"ok": True, **result}


@router.post("/{session_id}/report.pdf")
def report(session_id: str, user: User = Depends(get_current_user),
           ws: Workspace = Depends(get_workspace), db: Session = Depends(get_db)):
    s = db.get(__import__("app.models.research", fromlist=["ResearchSession"]).ResearchSession, session_id)
    if s is None or s.workspace_id != ws.id:
        raise HTTPException(404, "Research session not found.")
    path, size = generate_pdf_report(db, ws, session_id)
    rep = GeneratedReport(workspace_id=ws.id, session_id=session_id, kind="pdf",
                          title=f"Research report — {s.title}", path=str(path), size_bytes=size)
    db.add(rep)
    db.commit()
    return FileResponse(path, media_type="application/pdf", filename=path.name)


@router.get("/reports/list")
def reports_list(user: User = Depends(get_current_user), ws: Workspace = Depends(get_workspace),
                 db: Session = Depends(get_db)):
    rows = db.execute(
        select(GeneratedReport).where(GeneratedReport.workspace_id == ws.id)
        .order_by(GeneratedReport.created_at.desc()).limit(50)
    ).scalars().all()
    return {"reports": [{"id": r.id, "title": r.title, "kind": r.kind, "size_bytes": r.size_bytes,
                         "session_id": r.session_id, "created_at": str(r.created_at)} for r in rows]}


@router.get("/reports/{report_id}/download")
def download(report_id: int, user: User = Depends(get_current_user),
             ws: Workspace = Depends(get_workspace), db: Session = Depends(get_db)):
    rep = db.get(GeneratedReport, report_id)
    if rep is None or rep.workspace_id != ws.id:
        raise HTTPException(404, "Report not found.")
    from pathlib import Path

    path = Path(rep.path)
    if not path.exists():
        raise HTTPException(404, "Report file missing.")
    return FileResponse(path, media_type="application/pdf", filename=path.name)
