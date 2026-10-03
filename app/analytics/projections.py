"""Cash-flow / capital-growth projection from current turnover and margin (best / expected / worst)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ProjectionInputs:
    starting_capital: float = 5000.0
    current_capital: float = 5000.0          # cash + stock at cost
    net_margin: float = 0.30                  # of sale price
    avg_days_to_sell: float = 30.0
    deploy_ratio: float = 0.7                 # share of capital actually in stock at any time
    reinvest_ratio: float = 1.0               # share of profit reinvested
    monthly_fixed_costs: float = 0.0
    monthly_buying_capacity: float = 4000.0   # one person can only source/test/photograph so much stock per month


def project(inp: ProjectionInputs, months: tuple[int, ...] = (3, 6, 12)) -> dict:
    """Each month the deployed stock turns over 30/avg_days times; each turn earns margin on sale price.
    ROI per turn = margin / (1 - margin). Worst = half the turns and 60% margin; best = 1.3x turns and 1.2x margin.
    Purchases per month are capped by `monthly_buying_capacity` (grows 10%/month as the operation matures)."""
    def run(turns_per_month: float, margin: float) -> list[dict]:
        cap = inp.current_capital
        rows = []
        max_m = max(months)
        for m in range(1, max_m + 1):
            roi = margin / (1 - margin) if margin < 1 else 1
            deployed = min(cap * inp.deploy_ratio * turns_per_month, inp.monthly_buying_capacity * (1 + 0.1 * m))
            profit = deployed * roi - inp.monthly_fixed_costs
            cap += profit * inp.reinvest_ratio
            if m in months:
                rows.append({"month": m, "capital": round(cap, 2), "monthly_profit": round(profit, 2),
                             "growth_pct": round((cap - inp.starting_capital) / inp.starting_capital, 3)})
        return rows
    base_turns = 30 / max(inp.avg_days_to_sell, 1)
    return {
        "inputs": inp.__dict__,
        "expected": run(base_turns, inp.net_margin),
        "best": run(base_turns * 1.3, min(0.6, inp.net_margin * 1.2)),
        "worst": run(base_turns * 0.5, inp.net_margin * 0.6),
    }
