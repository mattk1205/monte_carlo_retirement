from dataclasses import replace

import pytest
import yaml

from monte_carlo_retirement.accounts import allocate_contributions
from monte_carlo_retirement.config import load_config
from monte_carlo_retirement.taxes import (
    JurisdictionPolicy,
    TaxBracket,
    TaxIncome,
    TaxPolicyTimeline,
    TaxSchedule,
    load_tax_policy,
    load_tax_timeline,
)


@pytest.fixture
def policy():
    return load_tax_policy("data/tax_policy/us_2026.yaml")


@pytest.mark.parametrize(
    "status, taxable, expected",
    [
        ("single", 0, 0),
        ("single", 12400, 1240),
        ("single", 50400, 5800),
        ("single", 105700, 17966),
        ("single", 201775, 41024),
        ("single", 256225, 58448),
        ("single", 640600, 192979.25),
        ("single", 700000, 214957.25),
        ("married_filing_jointly", 24800, 2480),
        ("married_filing_jointly", 100800, 11600),
        ("married_filing_jointly", 211400, 35932),
        ("married_filing_jointly", 403550, 82048),
        ("married_filing_jointly", 512450, 116896),
        ("married_filing_jointly", 768700, 206583.50),
        ("married_filing_jointly", 800000, 218164.50),
    ],
)
def test_federal_2026_against_irs_rate_table(policy, status, taxable, expected):
    schedule = policy.federal.filing_statuses[status]
    result = policy.calculate(
        TaxIncome(wages=taxable + schedule.deduction), filing_status=status, state="TX"
    )
    assert result.federal == pytest.approx(expected)
    assert result.state == 0


@pytest.mark.parametrize("status", ["single", "married_filing_jointly"])
def test_every_bracket_boundary_is_continuous(policy, status):
    schedule = policy.federal.filing_statuses[status]
    for previous, bracket in zip(schedule.brackets, schedule.brackets[1:]):
        boundary = bracket.lower + schedule.deduction
        center = schedule.tax(boundary)
        assert center - schedule.tax(boundary - 1) == pytest.approx(previous.rate)
        assert schedule.tax(boundary + 1) - center == pytest.approx(bracket.rate)


def test_deduction_floor_and_itemized_alternative(policy):
    schedule = policy.federal.filing_statuses["single"]
    assert schedule.tax(0) == 0
    assert schedule.tax(16099) == 0
    assert schedule.tax(16100) == 0
    assert schedule.tax(16101) == pytest.approx(0.1)
    assert schedule.tax(20000, itemized_deduction=25000) == 0
    assert schedule.tax(20000, itemized_deduction=1000) == schedule.tax(20000)


def test_synthetic_state_progressive_tax_and_retirement_exclusion(policy):
    result = policy.calculate(
        TaxIncome(wages=60000), filing_status="single", state="SYNTHETIC_STATE"
    )
    assert result.state == pytest.approx(50000 * 0.03 + 5000 * 0.05)
    retired = policy.calculate(
        TaxIncome(traditional_withdrawal=60000),
        filing_status="single",
        state="SYNTHETIC_STATE",
    )
    assert retired.state == 0
    assert retired.federal == pytest.approx(5020)


def test_roth_is_excluded_and_traditional_withdrawals_stack_on_income(policy):
    result = policy.calculate(
        TaxIncome(
            wages=40000,
            ordinary_income=10000,
            traditional_withdrawal=30000,
            qualified_roth_withdrawal=100000,
        ),
        filing_status="single",
        state="TX",
    )
    assert result.total == pytest.approx(8770)
    assert result == policy.calculate(
        TaxIncome(wages=80000), filing_status="single", state="TX"
    )


def test_direct_contribution_deduction_matches_net_wage_adapter(policy):
    direct = policy.calculate(
        TaxIncome(wages=100000, traditional_contribution=20000),
        filing_status="single",
        state="SYNTHETIC_STATE",
    )
    net = policy.calculate(
        TaxIncome(wages=80000), filing_status="single", state="SYNTHETIC_STATE"
    )
    assert direct == net


@pytest.mark.parametrize("share", [0, 0.5, 1])
def test_tax_engine_integrates_with_equal_cost_allocator(policy, share):
    def tax(wages):
        return policy.calculate(
            TaxIncome(wages=wages), filing_status="single", state="TX"
        ).total

    plan = allocate_contributions(
        income=100000,
        budget=15000,
        contribution_limit=24000,
        roth_share=share,
        income_tax=tax,
    )
    assert plan.household_cost == pytest.approx(15000)
    assert plan.tax_savings == pytest.approx(
        tax(100000) - tax(100000 - plan.traditional)
    )
    if share == 0:
        assert plan.traditional == pytest.approx(15000 / 0.78)


def test_allocator_crosses_a_real_federal_bracket(policy):
    def tax(wages):
        return policy.calculate(
            TaxIncome(wages=wages), filing_status="single", state="TX"
        ).total

    plan = allocate_contributions(
        income=70000,
        budget=15000,
        contribution_limit=24000,
        roth_share=0,
        income_tax=tax,
    )
    # Gross income 66,500 starts the 22% bracket; first 3,500 costs 78%.
    assert plan.traditional == pytest.approx(3500 + (15000 - 3500 * 0.78) / 0.88)


def test_timeline_switches_policy_only_at_effective_year():
    config = load_config("configs/scenarios/higher_taxes.yaml")
    timeline = load_tax_timeline(config.tax_policy_files)
    assert timeline.for_year(2035).effective_year == 2026
    higher = timeline.for_year(2036)
    assert higher.effective_year == 2036
    args = dict(filing_status="single", state="TX")
    income = TaxIncome(wages=100000)
    assert (
        higher.calculate(income, **args).total
        > timeline.for_year(2026).calculate(income, **args).total
    )
    assert timeline.for_year(2100) == higher
    with pytest.raises(ValueError):
        timeline.for_year(2025)


def test_explicit_indexing_scales_dollars_not_rates(policy):
    income = TaxIncome(wages=100000)
    args = dict(filing_status="single", state="TX")
    assert policy.indexed(2).calculate(TaxIncome(wages=200000), **args).total == (
        pytest.approx(2 * policy.calculate(income, **args).total)
    )
    assert policy.indexed(1).calculate(income, **args) == policy.calculate(
        income, **args
    )
    with pytest.raises(ValueError):
        policy.indexed(0)


@pytest.mark.parametrize(
    "factory",
    [
        lambda: TaxBracket(0, 1),
        lambda: TaxBracket(-1, 0.2),
        lambda: TaxBracket(0, float("nan")),
        lambda: TaxSchedule(0, ()),
        lambda: TaxSchedule(-1, (TaxBracket(0, 0.1),)),
        lambda: TaxSchedule(0, (TaxBracket(1, 0.1),)),
        lambda: TaxSchedule(0, (TaxBracket(0, 0.1), TaxBracket(0, 0.2))),
        lambda: TaxIncome(wages=100, traditional_contribution=101),
        lambda: TaxIncome(qualified_roth_withdrawal=-1),
        lambda: TaxIncome(ordinary_income=True),
        lambda: TaxPolicyTimeline(()),
    ],
)
def test_invalid_tax_inputs(factory):
    with pytest.raises(ValueError):
        factory()


def test_unsupported_jurisdiction_and_status_fail(policy):
    for args in [
        dict(filing_status="single", state="unknown"),
        dict(filing_status="unknown", state="TX"),
    ]:
        with pytest.raises(ValueError):
            policy.calculate(TaxIncome(), **args)


def test_combined_rates_and_duplicate_policy_years_fail(policy):
    high = JurisdictionPolicy(
        {
            s: TaxSchedule(0, (TaxBracket(0, 0.8),))
            for s in ["single", "married_filing_jointly"]
        }
    )
    with pytest.raises(ValueError):
        replace(policy, states={"high": high})
    with pytest.raises(ValueError):
        TaxPolicyTimeline((policy, policy))


@pytest.mark.parametrize(
    "mutation",
    [
        lambda d: d.update(typo=True),
        lambda d: d.update(effective_year=True),
        lambda d: d.update(sources="not a list"),
        lambda d: d["federal"].update(retirement_taxable_fraction=1.1),
        lambda d: d["federal"]["filing_statuses"]["single"].update(brakets=[]),
        lambda d: d["federal"]["filing_statuses"]["single"].update(brackets=[]),
    ],
)
def test_policy_loader_rejects_malformed_files(tmp_path, mutation):
    from pathlib import Path

    data = yaml.safe_load(Path("data/tax_policy/us_2026.yaml").read_text())
    mutation(data)
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump(data))
    with pytest.raises(ValueError):
        load_tax_policy(path)
