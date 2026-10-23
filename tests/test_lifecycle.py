from dataclasses import replace

import numpy as np
import pytest

from monte_carlo_retirement.accounts import allocate_contributions
from monte_carlo_retirement.config import Economics, Optimization, load_config
from monte_carlo_retirement.investments import generate_scenarios
from monte_carlo_retirement.simulation import (
    RMD_DIVISORS,
    TaxKernel,
    contribution_arrays,
    simulate,
    terminal_value,
    withdraw,
)
from monte_carlo_retirement.strategies import Strategy
from monte_carlo_retirement.taxes import TaxIncome, load_tax_timeline


@pytest.fixture
def config():
    return replace(
        load_config("configs/baseline.yaml"),
        current_age=64,
        retirement_age=65,
        planning_end_age=68,
        scenario_count=4,
        economics=Economics(
            income_volatility=0,
            return_mean=0,
            return_volatility=0,
            inflation_mean=0,
            inflation_volatility=0,
            spending_volatility=0,
            policy_multiplier_volatility=0,
            dividend_yield=0,
        ),
        optimization=Optimization(enabled=False),
    )


def test_vector_tax_and_contributions_match_scalar_reference(config):
    policy = load_tax_timeline(config.tax_policy_files).for_year(2026)
    wages = np.array([0.0, 15000, 65000, 70000, 100000, 900000])
    for state in ("TX", "SYNTHETIC_STATE"):
        tax = TaxKernel(config, policy, state, np.ones(6), np.ones(6))
        for i, wage in enumerate(wages):
            assert tax.tax(wages)[i] == pytest.approx(
                policy.calculate(
                    TaxIncome(wages=wage), filing_status="single", state=state
                ).total
            )
        for share in (0, 0.5, 1):
            budgets = np.minimum(wages, 15000)
            plan = contribution_arrays(wages, budgets, 24000, share, tax.tax)
            for i, wage in enumerate(wages):
                scalar = allocate_contributions(
                    income=float(wage),
                    budget=float(budgets[i]),
                    contribution_limit=24000,
                    roth_share=share,
                    income_tax=lambda x: float(tax.tax(np.array([x]))[0]),
                )
                np.testing.assert_allclose(
                    [a[i] for a in plan],
                    [
                        scalar.traditional,
                        scalar.roth,
                        scalar.taxable,
                        scalar.tax_savings,
                    ],
                    atol=1e-5,
                )


def test_withdrawal_grossup_and_cashflow_conservation():
    balances = np.array([[100000.0, 20000, 50000], [0, 0, 1000]])
    basis = np.array([20000.0, 500])
    other = np.array([1000.0, 0])
    spend = np.array([70000.0, 3000])

    def tax(ordinary, traditional=0, gains=0):
        return 0.2 * (ordinary + traditional) + 0.15 * gains

    after, new_basis, paid, taxes, taken, gains, rmd = withdraw(
        balances,
        basis,
        spend,
        other,
        tax,
        ("taxable", "traditional", "roth"),
        np.zeros(2),
    )
    np.testing.assert_allclose(
        balances.sum(axis=1) + other, after.sum(axis=1) + paid + taxes, atol=1e-5
    )
    assert paid[0] == pytest.approx(70000, abs=1e-5)
    assert paid[1] == pytest.approx(925)
    assert new_basis[1] == 0
    assert gains[0] == pytest.approx(30000)
    assert (after >= 0).all()


def test_rmd_excess_reinvests_after_taxes():
    balances = np.array([[100000.0, 0, 0]])
    after, basis, paid, taxes, taken, _, rmd = withdraw(
        balances,
        np.zeros(1),
        np.array([1000.0]),
        np.zeros(1),
        lambda ordinary, traditional=0, gains=0: 0.2 * traditional,
        ("taxable", "traditional", "roth"),
        np.array([10000.0]),
    )
    assert rmd[0] == 10000
    assert after[0, 0] == pytest.approx(90000)
    assert after[0, 2] == pytest.approx(7000)
    assert basis[0] == pytest.approx(7000)
    assert paid[0] == 1000
    assert RMD_DIVISORS[75] == 24.6
    assert RMD_DIVISORS[95] == 8.9
    assert RMD_DIVISORS[120] == 2


def test_losses_preserve_basis_without_creating_tax_credit():
    balances = np.array([[0.0, 0, 1000]])
    out = withdraw(
        balances,
        np.array([2000.0]),
        np.array([500.0]),
        np.zeros(1),
        lambda ordinary, traditional=0, gains=0: 0.15 * gains,
        ("taxable", "traditional", "roth"),
        np.zeros(1),
    )
    assert out[1][0] == pytest.approx(1000)
    assert out[3][0] == 0
    assert out[5][0] == 0


def test_year_end_contributions_and_retirement_timing(config):
    result = simulate(config)
    assert result.paths.ages.tolist() == [64, 65, 66, 67]
    a = result.annual
    assert (a["contributions"][:, :, 1:] == 0).all()
    assert (a["withdrawals"][:, :, 0] == 0).all()
    for s in range(3):
        cost = a["contributions"][s, :, 0] - a["tax_savings"][s, :, 0]
        np.testing.assert_allclose(cost, 15000, atol=1e-5)
        expected = 135000 + a["contributions"][s, :, 0]
        np.testing.assert_allclose(a["portfolio"][s, :, 0], expected)
        np.testing.assert_allclose(result.retirement_real_balances[s], expected)
    assert (result.terminal_real >= 0).all()


def test_no_assets_records_unfunded_retirement_spending(config):
    config = replace(
        config,
        traditional_balance=0,
        roth_balance=0,
        taxable_balance=0,
        taxable_basis=0,
        annual_after_tax_savings_budget=0,
    )
    result = simulate(config)
    np.testing.assert_allclose(result.cumulative_shortfall_real, 180000)
    assert not result.terminal_real.any()


def test_terminal_valuation_spreads_deductions_across_years(config):
    timeline = load_tax_timeline(config.tax_policy_files)
    wealth = terminal_value(
        config,
        np.array([[100000.0, 0, 0]]),
        np.zeros(1),
        np.ones(1),
        np.ones(1),
        timeline,
    )
    assert wealth[0] == pytest.approx(100000)  # $5k annual slices below deduction


def test_strategy_order_does_not_change_paths_or_outcomes(config):
    strategies = (Strategy("A", 0), Strategy("B", 1))
    first = simulate(config, strategies=strategies)
    second = simulate(config, strategies=tuple(reversed(strategies)))
    np.testing.assert_array_equal(first.paths.income, second.paths.income)
    np.testing.assert_allclose(first.terminal_real, second.terminal_real[::-1])


def test_lifecycle_balance_conservation_without_growth(config):
    result = simulate(config)
    a = result.annual
    for s in range(3):
        before = np.full(4, 135000.0)
        for t in range(4):
            # Wage taxes are paid externally; retirement taxes draw on assets.
            asset_taxes = a["taxes"][s, :, t] if t else 0
            np.testing.assert_allclose(
                before + a["contributions"][s, :, t],
                a["portfolio"][s, :, t] + a["spending"][s, :, t] + asset_taxes,
                atol=1e-4,
            )
            before = a["portfolio"][s, :, t]


def test_adaptive_uses_independent_planning_and_is_reproducible(config):
    config = replace(
        config,
        optimization=Optimization(
            planning_scenarios=2, income_groups=1, wealth_groups=1
        ),
    )
    paths, end = generate_scenarios(config)
    first = simulate(config, paths, end)
    # Alter only the future evaluation returns. Today's choice cannot change.
    from monte_carlo_retirement.investments import Scenarios

    changed_returns = paths.returns.copy()
    changed_returns[:, 1:] = 0.5
    altered = Scenarios(
        paths.ages,
        paths.income,
        changed_returns,
        paths.prices,
        paths.spending,
        paths.policy_multiplier,
    )
    second = simulate(config, altered, end)
    np.testing.assert_array_equal(
        first.annual["roth_share"][-1, :, 0], second.annual["roth_share"][-1, :, 0]
    )
    assert first.allocation_decisions == second.allocation_decisions
    assert first.allocation_decisions


def test_indexed_tax_kernel_matches_indexed_scalar_policy(config):
    config = replace(
        config, economics=replace(config.economics, index_tax_brackets=True)
    )
    policy = load_tax_timeline(config.tax_policy_files).for_year(2026)
    prices = np.array([1.0, 2.0, 3.0])
    wages = np.array([100000.0, 200000.0, 300000.0])
    kernel = TaxKernel(config, policy, "SYNTHETIC_STATE", prices, np.ones(3))
    for i, price in enumerate(prices):
        expected = policy.indexed(float(price)).calculate(
            TaxIncome(wages=float(wages[i])),
            filing_status="single",
            state="SYNTHETIC_STATE",
        )
        assert kernel.tax(wages)[i] == pytest.approx(expected.total)


def test_dividends_are_in_total_return_and_not_double_counted(config):
    config = replace(
        config,
        annual_after_tax_savings_budget=0,
        traditional_balance=0,
        roth_balance=0,
        taxable_balance=10000,
        taxable_basis=10000,
        economics=replace(config.economics, dividend_yield=0.02),
    )
    result = simulate(config, strategies=(Strategy("Roth", 1),))
    # Zero total return includes $200 distributions; $30 tax reduces assets.
    assert result.annual["portfolio"][0, 0, 0] == pytest.approx(9970)
    assert result.annual["basis"][0, 0, 0] == pytest.approx(10170)


def test_taxable_growth_conservation_with_state_dividend_tax(config):
    config = replace(
        config,
        working_state="SYNTHETIC_STATE",
        economics=replace(config.economics, dividend_yield=0.02, return_mean=0.05),
    )
    result = simulate(config)
    a = result.annual
    policy = load_tax_timeline(config.tax_policy_files).for_year(2026)
    tax = TaxKernel(config, policy, "SYNTHETIC_STATE", np.ones(4), np.ones(4))
    for s in range(3):
        contribution = a["traditional_contribution"][s, :, 0]
        actual_asset_tax = a["taxes"][s, :, 0] - tax.tax(100000 - contribution)
        expected = 135000 * 1.05 - actual_asset_tax + a["contributions"][s, :, 0]
        np.testing.assert_allclose(a["portfolio"][s, :, 0], expected, atol=1e-5)


def test_adaptive_choices_do_not_read_future_income_or_policy(config):
    from monte_carlo_retirement.investments import Scenarios

    config = replace(
        config,
        optimization=Optimization(
            planning_scenarios=2, income_groups=1, wealth_groups=1
        ),
    )
    paths, end = generate_scenarios(config)
    first = simulate(config, paths, end)
    future_policy = paths.policy_multiplier.copy()
    future_policy[:, 1:] = 2
    future_income = paths.income.copy()
    future_income[:, 1:] = 0
    altered = Scenarios(
        paths.ages,
        future_income,
        paths.returns,
        paths.prices,
        paths.spending,
        future_policy,
    )
    second = simulate(config, altered, end)
    assert first.allocation_decisions == second.allocation_decisions


def test_nonfinite_or_negative_initial_balances_fail(config):
    for balances in [(-1, 0, 0), (float("nan"), 0, 0), (1, 2)]:
        with pytest.raises(ValueError):
            simulate(config, initial_balances=balances)
