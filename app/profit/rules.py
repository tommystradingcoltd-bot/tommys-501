"""Tiered alert rules, phase mode, capital check and deal scoring."""
from __future__ import annotations

from dataclasses import dataclass, field

CONF_FACTOR = {"high": 1.0, "medium": 0.8, "low": 0.5}


@dataclass
class RuleConfig:
    tier_rules: list[dict] = field(default_factory=lambda: [
        {"max_days": 14, "min_margin": 0.25}, {"max_days": 30, "min_margin": 0.30}, {"max_days": 60, "min_margin": 0.40}])
    max_days_to_alert: int = 60
    large_deal_threshold: float = 150.0
    large_deal_margin_relief: float = 0.05
    phase_mode: str = "capital_growth"      # capital_growth | steady
    capital_growth_max_days: int = 30
    capital_growth_override_margin: float = 0.50
    min_net_profit: float = 8.0
    low_confidence_min_margin: float = 0.60
    capital_reserve: float = 300.0
    high_priority_score: float = 70.0

    @classmethod
    def from_settings(cls, s: dict) -> "RuleConfig":
        return cls(
            tier_rules=s.get("tier_rules", cls().tier_rules), max_days_to_alert=int(s.get("max_days_to_alert", 60)),
            large_deal_threshold=float(s.get("large_deal_threshold", 150)), large_deal_margin_relief=float(s.get("large_deal_margin_relief", 0.05)),
            phase_mode=s.get("phase_mode", "capital_growth"), capital_growth_override_margin=float(s.get("steady_min_margin_override", 0.5)),
            min_net_profit=float(s.get("min_net_profit", 8)), low_confidence_min_margin=float(s.get("low_confidence_min_margin", 0.6)),
            capital_reserve=float(s.get("capital_reserve", 300)), high_priority_score=float(s.get("high_priority_score", 70)),
        )


@dataclass
class Decision:
    should_alert: bool
    tier: str
    min_margin_required: float
    reason: str
    score: float
    priority: str                 # high | default | low
    check_manually: bool = False
    capital_warning: bool = False


def tier_for(days: int, cfg: RuleConfig) -> tuple[str, float | None]:
    """Return (tier label, min margin) or (label, None) when beyond the last tier."""
    prev = 0
    for rule in sorted(cfg.tier_rules, key=lambda r: r["max_days"]):
        if days <= rule["max_days"]:
            return f"{prev}-{rule['max_days']}d", float(rule["min_margin"])
        prev = rule["max_days"] + 1
    return f"{prev}d+", None


def score_deal(margin: float, days: int, confidence: str, net_profit: float) -> float:
    """margin x speed x confidence, 0-100. Profit magnitude nudges the score so a £40 win beats a £9 win."""
    m = max(0.0, min(margin / 0.6, 1.0))
    speed = max(0.1, min(1.0, 1 - days / 90))
    c = CONF_FACTOR.get(confidence, 0.5)
    magnitude = min(1.0, 0.6 + net_profit / 100)  # £40 profit -> 1.0
    return round(100 * m * speed * c * magnitude, 1)


def evaluate(net_profit: float, net_margin: float, est_days: int, confidence: str, buy_price: float,
             landed_cost: float, cash_available: float | None, cfg: RuleConfig) -> Decision:
    score = score_deal(net_margin, est_days, confidence, net_profit)
    tier, min_margin = tier_for(est_days, cfg)
    capital_warning = cash_available is not None and (cash_available - landed_cost) < cfg.capital_reserve

    def no(reason: str, required: float = 0.0) -> Decision:
        return Decision(False, tier, required, reason, score, "low", False, capital_warning)

    if net_profit < cfg.min_net_profit:
        return no(f"net profit £{net_profit:.2f} below floor £{cfg.min_net_profit:.2f}")
    if min_margin is None or est_days > cfg.max_days_to_alert:
        return no(f"estimated {est_days} days to sell is beyond the {cfg.max_days_to_alert}-day limit")
    required = min_margin
    if buy_price > cfg.large_deal_threshold:
        required = max(0.0, required - cfg.large_deal_margin_relief)
    if cfg.phase_mode == "capital_growth" and est_days > cfg.capital_growth_max_days:
        if net_margin < cfg.capital_growth_override_margin:
            return no(f"capital growth phase: {est_days}d tier needs {cfg.capital_growth_override_margin:.0%} margin", cfg.capital_growth_override_margin)
        required = max(required, cfg.capital_growth_override_margin)
    check_manually = False
    if confidence == "low":
        if net_margin < cfg.low_confidence_min_margin:
            return no(f"low-confidence valuation and margin {net_margin:.0%} < {cfg.low_confidence_min_margin:.0%}", cfg.low_confidence_min_margin)
        check_manually = True
        required = max(required, cfg.low_confidence_min_margin)
    if net_margin < required:
        return no(f"margin {net_margin:.0%} below tier {tier} minimum {required:.0%}", required)
    priority = "high" if score >= cfg.high_priority_score else "default"
    reason = f"margin {net_margin:.0%} >= {required:.0%} for tier {tier}"
    if check_manually:
        reason += " (check manually: low-confidence valuation)"
    return Decision(True, tier, required, reason, score, priority, check_manually, capital_warning)
