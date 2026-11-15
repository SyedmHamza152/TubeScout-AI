"""Optimizer property tests — allocation must sum EXACTLY to the budget."""
import random

import pytest

from app.optimization.engine import FormatScore, optimize_budget


def _scores(**overrides) -> list[FormatScore]:
    base = [
        FormatScore("in_stream", "In-Stream Ads", "cpv", 1.10, 0.28, 0.06, 0.012, 3500),
        FormatScore("shorts", "Shorts Ads", "cpv", 0.55, 0.20, 0.03, 0.010, 3200),
        FormatScore("in_feed", "In-Feed Video Ads", "cpc", 10.0, 0.0, 0.010, 0.007, 3900),
    ]
    for s in base:
        for k, v in overrides.items():
            setattr(s, k, v)
    return base


@pytest.mark.parametrize("budget", [900, 5000, 12345.67, 100000, 999999])
def test_exact_budget(budget):
    result = optimize_budget(budget, _scores(), strategy="balanced")
    total = sum(a.amount for a in result.allocations)
    assert abs(total - budget) < 0.01


def test_no_negative_allocations():
    result = optimize_budget(5000, _scores())
    assert all(a.amount >= 0 for a in result.allocations)


def test_share_bounds_respected():
    for strategy in ("balanced", "performance", "exploratory"):
        result = optimize_budget(50000, _scores(), strategy=strategy)
        for a in result.allocations:
            assert a.share <= 0.80 + 1e-6


def test_all_in_forbidden():
    result = optimize_budget(10000, _scores())
    assert len(result.allocations) >= 2  # bounds force diversification


def test_random_budgets_exact_sum():
    rng = random.Random(42)
    for _ in range(25):
        budget = rng.uniform(500, 200000)
        result = optimize_budget(budget, _scores(), strategy=rng.choice(["balanced", "performance", "exploratory"]))
        total = sum(a.amount for a in result.allocations)
        assert abs(total - budget) < 0.01
        assert all(a.amount >= 0 for a in result.allocations)


def test_methodology_and_explanations():
    result = optimize_budget(20000, _scores(), cold_start=True)
    assert "COLD START" in result.methodology
    for a in result.allocations:
        assert len(a.reason) > 10
