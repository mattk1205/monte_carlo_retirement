# Contribution accounting assumptions

## Equal economic cost

For employee Traditional contribution T, Roth contribution R, taxable deposit B,
and annual income-tax liability function Tax:

```text
income tax savings = Tax(income) - Tax(income - T)
household cost = T + R + B - income tax savings
```

A fixed Roth share means `R / (T + R)`, not the share of household cash cost.
The allocator maximizes employee contributions for the supplied cash budget,
subject to the shared employee limit and annual earned income. It deposits
remaining budget in taxable investments, increasing both balance and basis.
Tax savings are assumed available in the same year, with no cash-flow delay.

The one-year demo treats the supplied savings budget as available cash, which
could include outside funds. It does not validate household living expenses or
net-pay affordability. It adds contributions without applying investment returns.
Employer contributions and withdrawals are outside the current implementation.

## Tax interface

The allocator accepts a tax-liability callable rather than hard-coding a tax
rate. It uses bracket-aware differences and bisection to solve the cash budget.
The callable must be deterministic, continuous, and nondecreasing with marginal
rates between zero (inclusive) and one (exclusive). Tax cliffs, refundable credits,
phaseouts producing unsupported effective rates, and negative tax liabilities
require extensions. Checks at evaluated points catch some violations; they do
not prove the callable satisfies the contract over all incomes.

The example uses the progressive tax engine described in [taxes.md](taxes.md).
Payroll taxes are excluded from the difference calculation. The policy assumes
employee Traditional deferrals reduce both federal and modeled state ordinary
income. Nonconforming state treatment requires a policy-engine extension.
Eligibility, catch-ups, legal contribution limits, and employer-plan rules are
not yet modeled. The configured employee limit remains illustrative.

## Balances and validation

Account snapshots are immutable; contributing produces a new snapshot.
Contributions are nonnegative. Taxable basis may exceed market value after losses.
Money uses floating-point dollars for future numerical simulation; tests compare
with tolerances, and reports round only for display.

The current example uses nominal 2026 dollars; the future annual simulation will
convert nominal policy inputs and report real outcomes explicitly. Ages, spending,
filing status, states, seed, and scenario count are validated configuration inputs
but do not affect this single-year accounting demonstration.

## Validation

Tests cover equal cash cost across allocations, hand-calculated flat-rate
contributions, progressive bracket crossings, zero and capped contributions,
income limits, taxable basis tracking, invalid inputs, and the simplified
same-tax-rate Traditional/Roth equivalence after investment growth. Tests include both
synthetic progressive fixtures and the published 2026 federal rate tables.
