# Tax methodology and policy inputs

## Supported calculation

`taxes.py` computes ordinary-income tax separately for federal and state policy:

1. Subtract employee Traditional contributions from wages.
2. Add other ordinary income and the jurisdiction's taxable fraction of
   Traditional retirement withdrawals.
3. Subtract the larger of the configured deduction or an explicitly supplied
   jurisdiction-specific itemized deduction; floor taxable income at zero.
4. Apply each marginal rate only to income in its bracket and sum the results.

Qualified Roth withdrawals do not enter the taxable base. The caller must verify
that Roth distributions qualify; early or nonqualified withdrawals are not modeled.
Federal and state amounts are returned separately and as a combined total.
Single and married-filing-jointly households are supported. Other filing statuses
raise an error.

The contribution allocator uses the difference in full annual tax liability
before and after a deduction, including bracket crossings. Its wage-only adapter
is equivalent to an explicit Traditional contribution under the supported policies.
It does not substitute one marginal rate for the entire contribution.

## Baseline and sources

The baseline is an illustrative household in Texas, not an assumption about the
user's residence. Policy values were checked on October 22, 2026.

- The federal schedules and base standard deductions in `us_2026.yaml` come from
  [IRS Revenue Procedure 2025-32, sections 4.01 and 4.14](https://www.irs.gov/irb/2025-45_IRB).
  Tests check rate-table amounts and behavior immediately around every boundary.
- Texas has no personal income tax under
  [Texas Constitution Article VIII, section 24-a](https://statutes.capitol.texas.gov/Docs/CN/htm/CN.8/CN.8.25.htm).
- `SYNTHETIC_STATE` is a configurable example, not a real state: for single filers,
  it deducts $5,000, taxes the first $50,000 of taxable income at 3%, and the rest
  at 5%. Joint thresholds and deductions double. Traditional retirement income
  is fully excluded. Other real states require separately sourced policies and
  possibly additional engine rules.

Each policy records its ID, effective year, description, and source references.
A bracket specifies its inclusive lower bound and rate; the next lower bound is
its upper boundary. The final bracket has no upper limit. Brackets must start at
zero and increase strictly. Combined maximum federal/state rates must be below
100% to preserve the contribution allocator's increasing net-cost assumption.
Unknown policy keys and malformed schedules fail validation.

## Future policy and inflation

`tax_policy_files` lists complete snapshots with unique effective years. Paths
resolve relative to the household YAML file. `TaxPolicyTimeline.for_year(year)`
selects the most recent effective snapshot; years before the first snapshot fail.
Input order does not affect selection.

Holding a policy beyond its effective year freezes its nominal thresholds and
deductions. This is an explicit scenario assumption, not a projection of statutory
indexing. `TaxPolicy.indexed(factor)` returns a hypothetical copy scaling all
thresholds and deductions without changing rates. It does not implement statutory
rounding or select an inflation rate.

`configs/scenarios/higher_taxes.yaml` adds `hypothetical_2036.yaml`: federal rates
rise by five percentage points in 2036; state rules and nominal dollar thresholds
remain unchanged. Switching is tested at the effective-year boundary. The lifecycle engine additionally supports a shared hypothetical rate multiplier;
see [methodology.md](methodology.md) for its distribution and observability.

## Deliberate boundaries

This is an ordinary-income comparison engine, not a full return preparer. It
excludes credits, AMT, payroll taxes, actual capital-gains schedules,
Social Security inclusion formulas, local taxes, state/federal itemization links,
SALT limits, and deduction phaseouts. Callers may supply already-taxable ordinary
income, but must not pass gross Social Security benefits as ordinary income.

Only base standard deductions are supplied: aged/blind additions, dependent
rules, and temporary senior deductions are not implemented. Retirement-income
calculations therefore do not yet model all age-related deductions. Supplied
itemized amounts must already reflect eligibility and statutory limits.
The synthetic state exclusion is a simple fraction, not an age/income eligibility
rule. Nonconforming state contribution rules are unsupported. These limitations
must be addressed before describing retirement projections as comprehensive.

The $24,000 employee contribution limit in household configuration is still a
synthetic assumption. Tax snapshots do not enforce contribution eligibility,
catch-up rules, or employer matching. Amounts are floating-point dollars without
tax-return rounding; tests use numerical tolerances.


## Lifecycle tax extension

The vectorized `TaxKernel` implements the same ordinary-income schedule rules
and is tested against the scalar engine. It adds a configured flat federal gains
rate and ordinary state tax for realized gains and reinvested dividends. This is
an explicitly simplified assumption, not a statutory capital-gains schedule.
Losses reduce asset value but do not generate refunds or loss carryovers. Current
rate multipliers and explicitly configured indexing apply in both planning and
evaluation. See [methodology.md](methodology.md) for RMDs and valuation rules.
