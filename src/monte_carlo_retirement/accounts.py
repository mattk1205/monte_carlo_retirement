"""Account balances and equal-household-cost employee contributions."""

from collections.abc import Callable
from dataclasses import dataclass

from .config import number


@dataclass(frozen=True)
class ContributionPlan:
    traditional: float
    roth: float
    taxable: float
    tax_savings: float

    def __post_init__(self) -> None:
        for name in ("traditional", "roth", "taxable", "tax_savings"):
            number(name, getattr(self, name))
        if self.tax_savings > self.traditional:
            raise ValueError("tax savings cannot exceed the Traditional contribution")

    @property
    def household_cost(self) -> float:
        return self.traditional + self.roth + self.taxable - self.tax_savings


@dataclass(frozen=True)
class AccountBalances:
    traditional: float = 0
    roth: float = 0
    taxable: float = 0
    taxable_basis: float = 0

    def __post_init__(self) -> None:
        for name in ("traditional", "roth", "taxable", "taxable_basis"):
            number(name, getattr(self, name))
        # Basis can exceed market value after investment losses.

    def contribute(self, plan: ContributionPlan) -> "AccountBalances":
        return AccountBalances(
            traditional=self.traditional + plan.traditional,
            roth=self.roth + plan.roth,
            taxable=self.taxable + plan.taxable,
            taxable_basis=self.taxable_basis + plan.taxable,
        )


def allocate_contributions(
    *,
    income: float,
    budget: float,
    contribution_limit: float,
    roth_share: float,
    income_tax: Callable[[float], float],
) -> ContributionPlan:
    """Maximize deferrals for a fixed cash budget, investing excess in taxable.

    roth_share is the Roth fraction of employee deferral dollars. income_tax
    must be deterministic, continuous and nondecreasing, with marginal rates
    in [0, 1). It returns annual income-tax liability, excluding payroll taxes.
    This guarantees increasing contribution cost and permits bracket crossings.
    The caller supplies policy and eligibility rules; no tax law is assumed here.
    """
    for name, value in (
        ("income", income),
        ("budget", budget),
        ("contribution_limit", contribution_limit),
        ("roth_share", roth_share),
    ):
        number(name, value)
    if roth_share > 1:
        raise ValueError("roth_share must be between 0 and 1")
    baseline_tax = income_tax(income)
    number("income_tax result", baseline_tax)

    def savings(total: float) -> float:
        traditional = total * (1 - roth_share)
        liability = income_tax(income - traditional)
        number("income_tax result", liability)
        saved = baseline_tax - liability
        if saved < -1e-8 or (traditional > 0 and saved >= traditional):
            raise ValueError(
                "income_tax violates the supported marginal-rate assumptions"
            )
        return max(0.0, saved)

    cap = min(income, contribution_limit)
    cap_savings = savings(cap)
    if cap - cap_savings <= budget:
        total = cap
        tax_savings = cap_savings
        taxable = budget - (total - tax_savings)
    else:
        low, high = 0.0, cap
        for _ in range(100):
            mid = (low + high) / 2
            if mid - savings(mid) <= budget:
                low = mid
            else:
                high = mid
        total = low
        tax_savings = savings(total)
        taxable = max(0.0, budget - (total - tax_savings))
    return ContributionPlan(
        traditional=total * (1 - roth_share),
        roth=total * roth_share,
        taxable=taxable,
        tax_savings=tax_savings,
    )
