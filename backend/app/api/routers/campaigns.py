"""Campaign intelligence + budget optimizer endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user, get_workspace
from app.core.constants import MARKETING_OBJECTIVES, SUPPORTED_FORMATS
from app.models.campaign import BudgetAllocation, BudgetRun, CampaignBrief
from app.models.identity import User, Workspace
from app.optimization.service import compare_scenarios, run_budget_optimization

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


class BriefBody(BaseModel):
    product: str = Field(min_length=1, max_length=300)
    description: str = ""
    business_category: str = ""
    country: str = "PK"
    currency: str = "PKR"
    total_budget: float = Field(gt=0, le=100_000_000)
    duration_days: int = Field(default=14, ge=1, le=365)
    objective: str = Field(default="Sales / Conversions")
    target_audience: str = ""
    preferred_formats: list[str] = []
    session_id: str | None = None
    strategy: str = Field(default="balanced")


@router.get("/meta")
def meta(user: User = Depends(get_current_user), ws: Workspace = Depends(get_workspace)):
    return {
        "formats": SUPPORTED_FORMATS,
        "objectives": MARKETING_OBJECTIVES,
        "strategies": ["balanced", "performance", "exploratory"],
        "note": "Public YouTube statistics are organic content metrics — they are never used as "
                "advertising spend, paid impressions, conversions or competitor ROAS.",
    }


@router.post("/briefs", status_code=201)
def create_brief(body: BriefBody, user: User = Depends(get_current_user),
                 ws: Workspace = Depends(get_workspace), db: Session = Depends(get_db)):
    if body.objective not in MARKETING_OBJECTIVES:
        raise HTTPException(422, f"objective must be one of: {', '.join(MARKETING_OBJECTIVES)}")
    fmts = [f for f in body.preferred_formats if f in SUPPORTED_FORMATS]
    brief = CampaignBrief(
        workspace_id=ws.id, session_id=body.session_id,
        product=body.product, description=body.description,
        business_category=body.business_category, country=body.country.upper(),
        currency=body.currency.upper(), total_budget=body.total_budget,
        duration_days=body.duration_days, objective=body.objective,
        target_audience=body.target_audience, preferred_formats=fmts,
    )
    db.add(brief)
    db.commit()
    db.refresh(brief)
    return {"id": brief.id, "product": brief.product, "total_budget": brief.total_budget,
            "currency": brief.currency, "objective": brief.objective}


@router.get("/briefs")
def list_briefs(user: User = Depends(get_current_user), ws: Workspace = Depends(get_workspace),
                db: Session = Depends(get_db)):
    rows = db.execute(
        select(CampaignBrief).where(CampaignBrief.workspace_id == ws.id)
        .order_by(CampaignBrief.created_at.desc()).limit(50)
    ).scalars().all()
    return {"briefs": [{
        "id": b.id, "product": b.product, "total_budget": b.total_budget,
        "currency": b.currency, "objective": b.objective, "duration_days": b.duration_days,
        "session_id": b.session_id, "created_at": str(b.created_at),
    } for b in rows]}


@router.post("/briefs/{brief_id}/optimize")
def optimize(brief_id: int, strategy: str = "balanced",
             user: User = Depends(get_current_user), ws: Workspace = Depends(get_workspace),
             db: Session = Depends(get_db)):
    brief = db.get(CampaignBrief, brief_id)
    if brief is None or brief.workspace_id != ws.id:
        raise HTTPException(404, "Brief not found.")
    if strategy not in ("balanced", "performance", "exploratory"):
        raise HTTPException(422, "strategy must be balanced|performance|exploratory")
    run = run_budget_optimization(db, ws.id, brief, strategy)
    allocs = db.execute(
        select(BudgetAllocation).where(BudgetAllocation.run_id == run.id)
        .order_by(BudgetAllocation.amount.desc())
    ).scalars().all()
    return _run_payload(run, allocs)


@router.post("/briefs/{brief_id}/scenarios")
def scenarios(brief_id: int, user: User = Depends(get_current_user),
              ws: Workspace = Depends(get_workspace), db: Session = Depends(get_db)):
    brief = db.get(CampaignBrief, brief_id)
    if brief is None or brief.workspace_id != ws.id:
        raise HTTPException(404, "Brief not found.")
    result = compare_scenarios(db, ws.id, brief)
    out = []
    for run in result["runs"]:
        allocs = db.execute(
            select(BudgetAllocation).where(BudgetAllocation.run_id == run.id)
            .order_by(BudgetAllocation.amount.desc())
        ).scalars().all()
        out.append(_run_payload(run, allocs))
    return {"scenarios": out}


@router.get("/runs")
def list_runs(user: User = Depends(get_current_user), ws: Workspace = Depends(get_workspace),
              db: Session = Depends(get_db)):
    rows = db.execute(
        select(BudgetRun).where(BudgetRun.workspace_id == ws.id)
        .order_by(BudgetRun.created_at.desc()).limit(50)
    ).scalars().all()
    out = []
    for run in rows:
        allocs = db.execute(
            select(BudgetAllocation).where(BudgetAllocation.run_id == run.id)
            .order_by(BudgetAllocation.amount.desc())
        ).scalars().all()
        out.append(_run_payload(run, allocs))
    return {"runs": out}


def _run_payload(run: BudgetRun, allocs: list[BudgetAllocation]) -> dict:
    return {
        "id": run.id, "strategy": run.strategy, "total_budget": run.total_budget,
        "currency": run.currency, "objective": run.objective,
        "cold_start": run.cold_start, "confidence": run.confidence,
        "algorithm": run.algorithm, "methodology": run.methodology,
        "source_label": run.source_label, "predicted_totals": run.predicted_totals,
        "meta": run.meta, "created_at": str(run.created_at),
        "allocations": [{
            "format_key": a.format_key, "label": a.label, "share": a.share,
            "amount": a.amount, "predicted": a.predicted, "confidence": a.confidence,
            "reason": a.reason, "fit_factors": a.fit_factors,
        } for a in allocs],
        "disclaimer": (
            "Recommendation only — this platform never spends money or modifies campaigns. "
            + ("Estimated planning scenario based on documented priors and live research signals." if run.cold_start else
               "Blended with actual connected Google Ads campaign history.")
        ),
    }
