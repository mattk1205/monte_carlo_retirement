import math

import pytest

from monte_carlo_retirement.accounts import (
    AccountBalances,
    allocate_contributions,
)


def allocate(**overrides):
    arguments = dict(
        income=100000,
        budget=15000,
        contribution_limit=24000,
        roth_share=0,
        income_tax=lambda income: income * 0.29,
    )
    arguments.update(overrides)
    return allocate_contributions(**arguments)


@pytest.mark.parametrize("share", [0, 0.25, 0.5, 0.75, 1])
def test_equal_cash_cost_and_deferral_split(share):
    plan = allocate(roth_share=share)
    assert plan.household_cost == pytest.approx(15000)
    assert plan.roth == pytest.approx(share * (plan.traditional + plan.roth))
    assert plan.traditional + plan.roth <= 24000


def test_traditional_grosses_up_and_roth_uses_budget():
    assert allocate().traditional == pytest.approx(15000 / 0.71)
    assert allocate(roth_share=1).roth == pytest.approx(15000)


def test_contribution_cap_sends_tax_savings_to_taxable():
    plan = allocate(budget=24000)
    assert plan.traditional == 24000
    assert plan.taxable == pytest.approx(6960)
    assert plan.household_cost == 24000
    before = AccountBalances(100, 200, 300, 400)
    after = before.contribute(plan)
    assert after.traditional == 24100
    assert after.taxable == pytest.approx(7260)
    assert after.taxable_basis == pytest.approx(7360)
    assert before.taxable == 300


def test_progressive_tax_bracket_crossing():
    def tax(income):
        return min(income, 50000) * 0.1 + max(0, income - 50000) * 0.3

    plan = allocate(
        income=60000, budget=20000, contribution_limit=50000, income_tax=tax
    )
    # First 10,000 of deductions save 30%; remaining deductions save 10%.
    assert plan.traditional == pytest.approx(10000 + 13000 / 0.9)
    assert plan.household_cost == pytest.approx(20000)


@pytest.mark.parametrize(
    "overrides",
    [
        {"budget": 0},
        {"income": 0},
        {"contribution_limit": 0},
    ],
)
def test_zero_boundaries(overrides):
    plan = allocate(**overrides)
    assert plan.household_cost == pytest.approx(overrides.get("budget", 15000))
    assert plan.traditional == 0


def test_income_limits_employee_deferrals():
    plan = allocate(income=5000)
    assert plan.traditional == 5000
    assert plan.household_cost == pytest.approx(15000)


@pytest.mark.parametrize(
    "overrides",
    [
        {"budget": -1},
        {"income": math.nan},
        {"roth_share": 1.1},
        {"contribution_limit": math.inf},
        {"budget": True},
        {"income_tax": lambda income: -1},
        {"income_tax": lambda income: income * 1.1},
    ],
)
def test_invalid_inputs(overrides):
    with pytest.raises(ValueError):
        allocate(**overrides)


def test_equal_tax_rates_produce_equal_spending_value_without_caps():
    traditional = allocate(contribution_limit=100000)
    roth = allocate(roth_share=1, contribution_limit=100000)
    growth = 1.07**30
    assert traditional.traditional * growth * 0.71 == pytest.approx(roth.roth * growth)
