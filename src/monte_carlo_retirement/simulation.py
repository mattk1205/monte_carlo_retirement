"""Vectorized annual cash flows and a gradual, explicit terminal valuation."""

from dataclasses import dataclass

import numpy as np

from .investments import generate_scenarios
from .strategies import configured_strategies
from .taxes import load_tax_timeline

# IRS Publication 590-B, Appendix B, Table III (Uniform Lifetime Table).
# RMD start age is an explicit configuration assumption, not inferred eligibility.
RMD_DIVISORS = dict(
    enumerate(
        (
            26.5,
            25.5,
            24.6,
            23.7,
            22.9,
            22.0,
            21.1,
            20.2,
            19.4,
            18.5,
            17.7,
            16.8,
            16.0,
            15.2,
            14.4,
            13.7,
            12.9,
            12.2,
            11.5,
            10.8,
            10.1,
            9.5,
            8.9,
            8.4,
            7.8,
            7.3,
            6.8,
            6.4,
            6.0,
            5.6,
            5.2,
            4.9,
            4.6,
            4.3,
            4.1,
            3.9,
            3.7,
            3.5,
            3.4,
            3.3,
            3.1,
            3.0,
            2.9,
            2.8,
            2.7,
            2.5,
            2.3,
            2.0,
        ),
        73,
    )
)


class TaxKernel:
    """Array implementation of the scalar policy rules plus flat federal gains.

    Dollar thresholds are optionally indexed to scenario starting-year prices.
    Policy uncertainty scales rates, capped to keep combined marginal tax < 95%.
    """

    def __init__(self, config, policy, state, prices, multiplier):
        self.federal = policy.federal
        if state not in policy.states:
            raise ValueError(f"unsupported state policy: {state}")
        self.state = policy.states[state]
        self.status = config.filing_status
        self.factor = prices if config.economics.index_tax_brackets else 1
        cg = config.economics.capital_gains_rate
        federal_max = max(
            b.rate for b in self.federal.filing_statuses[self.status].brackets
        )
        state_max = max(
            b.rate for b in self.state.filing_statuses[self.status].brackets
        )
        maximum = max(federal_max, cg) + state_max
        self.multiplier = np.minimum(multiplier, 0.94 / max(maximum, 1e-9))
        self.cg_rate = cg

    def _ordinary(self, jurisdiction, income):
        schedule = jurisdiction.filing_statuses[self.status]
        taxable = np.maximum(0, income - schedule.deduction * self.factor)
        total = np.zeros_like(taxable, dtype=float)
        # Difference-of-ramps is equivalent to taxing each bracket's slice.
        previous_rate = 0
        for bracket in schedule.brackets:
            total += np.maximum(0, taxable - bracket.lower * self.factor) * (
                bracket.rate - previous_rate
            )
            previous_rate = bracket.rate
        return total * self.multiplier

    def tax(self, ordinary, traditional=0, gains=0):
        federal = (
            self._ordinary(
                self.federal,
                ordinary + traditional * self.federal.retirement_taxable_fraction,
            )
            + gains * self.cg_rate * self.multiplier
        )
        state = self._ordinary(
            self.state,
            ordinary + traditional * self.state.retirement_taxable_fraction + gains,
        )
        return federal + state


def contribution_arrays(income, budget, limit, shares, tax):
    """Array equivalent of accounts.allocate_contributions; tested against it."""
    cap = np.minimum(income, limit)
    before = tax(income)
    low, high = np.zeros_like(income), cap.copy()
    for _ in range(38):
        middle = (low + high) / 2
        cost = middle - (before - tax(income - middle * (1 - shares)))
        feasible = cost <= budget
        low = np.where(feasible, middle, low)
        high = np.where(feasible, high, middle)
    cap_savings = before - tax(income - cap * (1 - shares))
    total = np.where(cap - cap_savings <= budget, cap, low)
    traditional = total * (1 - shares)
    roth = total * shares
    savings = before - tax(income - traditional)
    taxable = np.maximum(0, budget - total + savings)
    return traditional, roth, taxable, savings


def withdraw(balances, basis, spending, other_income, tax, order, rmd):
    """Beginning-year withdrawals; mandatory excess is reinvested in taxable.

    Returns balances, basis, paid spending, income taxes, gross withdrawals,
    realized gains and mandatory distribution. No borrowing or negative balances.
    """
    n = len(basis)
    mandatory = np.minimum(balances[:, 0], rmd)
    available = balances.copy()
    available[:, 0] -= mandatory
    total = available.sum(axis=1)
    basis_fraction = np.divide(
        basis, balances[:, 2], out=np.zeros(n), where=balances[:, 2] > 0
    )
    mapping = {"traditional": 0, "roth": 1, "taxable": 2}

    def amounts(gross):
        remaining = gross.copy()
        taken = np.zeros_like(balances)
        for account in order:
            col = mapping[account]
            taken[:, col] = np.minimum(remaining, available[:, col])
            remaining -= taken[:, col]
        taken[:, 0] += mandatory
        gains = taken[:, 2] * np.maximum(0, 1 - basis_fraction)
        taxes = tax(other_income, taken[:, 0], gains)
        net = other_income + taken.sum(axis=1) - taxes
        return taken, gains, taxes, net

    low, high = np.zeros(n), total.copy()
    for _ in range(38):
        middle = (low + high) / 2
        _, _, _, net = amounts(middle)
        enough = net >= spending
        high = np.where(enough, middle, high)
        low = np.where(enough, low, middle)
    taken, gains, taxes, net = amounts(high)
    # Numerical residuals below one cent do not constitute unmet spending.
    paid = np.minimum(spending, np.maximum(0, net))
    excess = np.maximum(0, net - spending)
    after = np.maximum(0, balances - taken)
    new_basis = np.maximum(0, basis - taken[:, 2] * basis_fraction)
    after[:, 2] += excess
    new_basis += excess
    return after, new_basis, paid, taxes, taken, gains, mandatory


def terminal_value(
    config, balances, basis, prices, multiplier, timeline, *, valuation_age=None
):
    """Real spendable proceeds from equal annual slices, not a bulk liquidation.

    Freeze terminal policy and purchasing power, with no post-horizon growth.
    Charge only incremental taxes above the configured other-income baseline.
    This is a valuation convention, not estate/inheritance taxation.
    """
    e = config.economics
    year = (
        config.tax_year
        + (config.planning_end_age if valuation_age is None else valuation_age)
        - config.current_age
    )
    policy = timeline.for_year(year)
    tax = TaxKernel(config, policy, config.retirement_state, prices, multiplier)
    other = e.retirement_other_income * prices
    trad = balances[:, 0] / e.valuation_years
    gains = np.maximum(0, balances[:, 2] - basis) / e.valuation_years
    incremental = (tax.tax(other, trad, gains) - tax.tax(other)) * e.valuation_years
    return np.maximum(0, balances.sum(axis=1) - incremental) / prices


@dataclass
class SimulationResult:
    config: object
    paths: object
    end_prices: np.ndarray
    strategies: tuple
    annual: dict
    terminal_real: np.ndarray
    cumulative_shortfall_real: np.ndarray
    retirement_real_balances: np.ndarray
    retirement_real_spendable: np.ndarray
    allocation_decisions: list


def simulate(
    config,
    paths=None,
    end_prices=None,
    *,
    strategies=None,
    initial_balances=None,
    initial_basis=None,
    record=True,
):
    if paths is None:
        paths, end_prices = generate_scenarios(config)
    if end_prices is None:
        raise ValueError("end_prices required with supplied scenarios")
    n, years = paths.income.shape
    if (
        end_prices.shape != (n,)
        or not np.isfinite(end_prices).all()
        or (end_prices <= 0).any()
    ):
        raise ValueError("invalid end_prices")
    strategies = (
        configured_strategies(config) if strategies is None else tuple(strategies)
    )
    if not strategies or len({strategy.name for strategy in strategies}) != len(
        strategies
    ):
        raise ValueError("strategies must be nonempty and have unique names")
    timeline = load_tax_timeline(config.tax_policy_files)
    e = config.economics
    metrics = (
        "traditional",
        "roth",
        "taxable",
        "basis",
        "income",
        "contributions",
        "traditional_contribution",
        "roth_contribution",
        "taxable_contribution",
        "budget",
        "tax_savings",
        "taxes",
        "withdrawals",
        "spending",
        "shortfall",
        "roth_share",
        "rmd",
        "gains",
        "portfolio",
    )
    annual = (
        {key: np.zeros((len(strategies), n, years)) for key in metrics}
        if record
        else {}
    )
    terminal = np.zeros((len(strategies), n))
    failures = np.zeros_like(terminal)
    retirement = np.full_like(terminal, np.nan)
    retirement_spendable = np.full_like(terminal, np.nan)
    decisions = []
    for s, strategy in enumerate(strategies):
        initial = (
            config.traditional_balance,
            config.roth_balance,
            config.taxable_balance,
        )
        initial = np.asarray(
            initial if initial_balances is None else initial_balances, dtype=float
        )
        if initial.shape == (3,):
            balances = np.tile(initial, (n, 1))
        elif initial.shape == (n, 3):
            balances = initial.copy()
        else:
            raise ValueError("initial balances must have shape (3,) or (scenarios, 3)")
        basis = np.broadcast_to(
            np.asarray(
                config.taxable_basis if initial_basis is None else initial_basis,
                dtype=float,
            ),
            (n,),
        ).copy()
        if (
            not np.isfinite(balances).all()
            or (balances < 0).any()
            or not np.isfinite(basis).all()
            or (basis < 0).any()
        ):
            raise ValueError(
                "initial balances and basis must be finite and nonnegative"
            )
        for t, age in enumerate(paths.ages):
            price = paths.prices[:, t]
            policy = timeline.for_year(config.tax_year + paths.start_index + t)
            state = (
                config.working_state
                if age < config.retirement_age
                else config.retirement_state
            )
            tax = TaxKernel(config, policy, state, price, paths.policy_multiplier[:, t])
            income = paths.income[:, t]
            trad = roth = taxable = savings = np.zeros(n)
            budget = spending_paid = shortfall = withdrawals = mandatory = gains = (
                np.zeros(n)
            )
            other = np.zeros(n)
            share = np.full(
                n, strategy.roth_share if strategy.roth_share is not None else 0.0
            )
            if age == config.retirement_age:
                retirement[s] = balances.sum(axis=1) / price
                retirement_spendable[s] = terminal_value(
                    config,
                    balances,
                    basis,
                    price,
                    paths.policy_multiplier[:, t],
                    timeline,
                    valuation_age=int(age),
                )
            if age >= config.retirement_age:
                other = e.retirement_other_income * price
                divisor = RMD_DIVISORS.get(int(age), 2.0)
                rmd = (
                    balances[:, 0] / divisor if age >= e.rmd_start_age else np.zeros(n)
                )
                balances, basis, spending_paid, taxes, taken, gains, mandatory = (
                    withdraw(
                        balances,
                        basis,
                        paths.spending[:, t],
                        other,
                        tax.tax,
                        e.withdrawal_order,
                        rmd,
                    )
                )
                withdrawals = taken.sum(axis=1)
                shortfall = np.maximum(0, paths.spending[:, t] - spending_paid)
                shortfall[shortfall < 0.01] = 0
                failures[s] += shortfall / price
                ordinary = other
                retirement_draw = taken[:, 0]
            else:
                ordinary = income
                retirement_draw = np.zeros(n)
                real_ratio = np.divide(
                    income,
                    price * config.annual_income,
                    out=np.zeros(n),
                    where=config.annual_income > 0,
                )
                requested = (
                    config.annual_after_tax_savings_budget
                    * price
                    * (real_ratio**e.savings_income_elasticity)
                )
                # Same conservative cash budget for every allocation; payroll taxes
                # and household living expenses are deliberately outside this model.
                budget = np.minimum(requested, np.maximum(0, income - tax.tax(income)))
                if strategy.roth_share is None:
                    from .optimization import choose_allocations

                    share, rows = choose_allocations(
                        config, paths, t, balances, basis, budget
                    )
                    decisions.extend(rows)
            # Annual total returns include dividends. Taxes on reinvested dividends
            # reduce taxable assets; losses do not create tax refunds or carryovers.
            gross_end = balances[:, 2] * (1 + paths.returns[:, t])
            dividend = np.minimum(balances[:, 2] * e.dividend_yield, gross_end)
            dividend_tax = tax.tax(
                ordinary, retirement_draw, gains + dividend
            ) - tax.tax(ordinary, retirement_draw, gains)
            balances[:, :2] *= 1 + paths.returns[:, t, None]
            balances[:, 2] = np.maximum(0, gross_end - dividend_tax)
            basis += dividend - dividend_tax
            if age < config.retirement_age:
                # Wage-funded saving has identical cash cost. Investment taxes
                # are charged to taxable assets, not the household savings budget.
                wage_tax = tax.tax
                limit = config.employee_contribution_limit * (
                    price if e.index_contribution_limit else 1
                )
                trad, roth, taxable, savings = contribution_arrays(
                    income, budget, limit, share, wage_tax
                )
                # Growth paid provisional dividend tax at pre-contribution income.
                # Refund the difference so contributions still cost exactly budget.
                actual_div_tax = tax.tax(income - trad, gains=dividend) - tax.tax(
                    income - trad
                )
                refund = dividend_tax - actual_div_tax
                balances[:, 2] += refund
                basis += refund
                balances += np.column_stack((trad, roth, taxable))
                basis += taxable
                taxes = tax.tax(income - trad, gains=dividend)
            else:
                taxes += dividend_tax
            if record:
                values = dict(
                    traditional=balances[:, 0],
                    roth=balances[:, 1],
                    taxable=balances[:, 2],
                    basis=basis,
                    income=income,
                    contributions=trad + roth + taxable,
                    traditional_contribution=trad,
                    roth_contribution=roth,
                    taxable_contribution=taxable,
                    budget=budget,
                    tax_savings=savings,
                    taxes=taxes,
                    withdrawals=withdrawals,
                    spending=spending_paid,
                    shortfall=shortfall,
                    roth_share=np.where(age < config.retirement_age, share, np.nan),
                    rmd=mandatory,
                    gains=gains,
                    portfolio=balances.sum(axis=1),
                )
                for key, value in values.items():
                    annual[key][s, :, t] = value
        terminal[s] = terminal_value(
            config,
            balances,
            basis,
            end_prices,
            paths.policy_multiplier[:, -1],
            timeline,
        )
    return SimulationResult(
        config,
        paths,
        end_prices,
        strategies,
        annual,
        terminal,
        failures,
        retirement,
        retirement_spendable,
        decisions,
    )
