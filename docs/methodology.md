# Simulation methodology (phases 3–8)

## Reproducible economic scenarios — phase 3

All strategies receive the same immutable arrays, shaped `(scenarios, years)`.
The ages run from `current_age` inclusive to `planning_end_age` exclusive.
`random_seed` creates separate NumPy streams for returns/inflation, income,
spending, and policy. Strategy order cannot change the paths. Reproduction requires
the saved configuration, source version, policy snapshots, and package versions.

Inputs are illustrative assumptions, not forecasts or fitted historical estimates:

- Total nominal portfolio returns are lognormal gross returns minus one. The
  configured mean and volatility are arithmetic annual return moments. Returns
  remain greater than -100%. A single portfolio is shared across account types.
- Gross inflation is lognormal with configured arithmetic mean and standard
  deviation. The return/inflation correlation applies to their latent normal
  shocks, not exactly to the final arithmetic returns. Price indices start at one.
- Real earnings compound with the configured mean growth and mean-corrected
  lognormal shocks (`income_volatility` is a log standard deviation). Nominal
  earnings also incorporate inflation. First-year income is known. Major events
  are Bernoulli draws at specified ages; their multipliers permanently change
  earnings. Income shocks are independent of investment shocks. Earnings stop at
  retirement; retirement age and longevity are fixed configuration inputs.
- Retirement spending is a base real target times the current price index and
  an independent, mean-one annual lognormal spending shock.
- At `policy_change_age`, a mean-one lognormal rate multiplier becomes observable
  and persists. Its volatility is a log standard deviation. The multiplier affects
  both federal and state rates and the flat federal gains rate. It is capped so
  combined marginal rates remain below 95%. It does not change RMD or eligibility
  rules. This is hypothetical tax uncertainty, not a policy prediction.

Tax snapshots persist until replaced. `index_tax_brackets: true` explicitly scales
all active snapshot thresholds/deductions by cumulative inflation since the initial
tax year, including later snapshots. This is a modeling convention, not statutory
annual indexing or rounding. The baseline explicitly leaves this flag false.
Contribution limits optionally scale by the same price index and remain illustrative.

## Annual cash flows — phase 4

1. At the beginning of a working year, observe income, balances, price index, and
   current policy. Set a shared saving budget: configured real budget times the
   price index times the real-income ratio raised to `savings_income_elasticity`.
   Cap it at income less modeled income tax before contributions. Payroll taxes
   and household living expenses are excluded; this is not a full affordability
   model. Allocate that budget at year end using the current strategy.
2. At the beginning of retirement years, pay spending using configured other
   ordinary income, then accounts in `withdrawal_order`. The default is taxable,
   Traditional, then Roth. A gross-up solver includes taxes on Traditional draws
   and taxable realized gains. Taxable basis is removed proportionally. No assets
   are borrowed; spending not funded is recorded as a shortfall.
3. Traditional RMDs use beginning-year balances (the previous year-end balance)
   divided by [IRS Publication 590-B, Table III](https://www.irs.gov/publications/p590b).
   `rmd_start_age` is an explicit assumption (75 in the example), not a derived
   birth-cohort eligibility calculation. The first RMD is taken in that year
   without deferral. Excess after-tax RMD proceeds are reinvested in taxable assets.
   Owner-lifetime Roth RMDs are excluded, consistent with
   [IRS guidance](https://www.irs.gov/retirement-plans/retirement-plan-and-ira-required-minimum-distributions-faqs).
4. Apply the same total investment return to the remaining accounts. Taxable
   dividends are included in total return, not added twice. The configured
   dividend yield is capped at available post-return assets. Dividends are
   reinvested after tax, increasing basis by the reinvestment. A **hypothetical
   flat federal capital-gains/qualified-dividend rate** plus ordinary state tax
   applies; federal gains brackets and loss offsets/carryovers are not modeled.
5. Working-year contributions arrive after investment growth. Traditional tax
   savings fund additional deferrals; cash above employee and earned-income caps
   goes to taxable investments. Wage-funded contribution cost is identical across
   strategies. Investment taxes are financed from taxable assets; their interaction
   with contribution deductions is reconciled without counting savings twice.

Starting balances and taxable basis are tracked independently. Basis can exceed
market value after losses. Retirement before age 60 is rejected because early
withdrawal exceptions/penalties are not modeled. Roth distributions are assumed
qualified, including the applicable holding period. No employer contributions,
Social Security inclusion formulas, conversion ladders, or healthcare expenses
beyond the spending target are modeled. See [tax exclusions](taxes.md).

## Wealth, risk, and reporting — phase 5

Account balances are not after-tax spending power. The report provides both
retirement-date and terminal real spendable valuations. Each valuation spreads
remaining Traditional balances and taxable gains over `valuation_years` equal
annual slices, freezes the valuation-date policy and prices, assumes no subsequent
returns, and subtracts incremental taxes above configured retirement other income.
It is a transparent comparison convention, not a forecast of withdrawals or an
estate-tax valuation. It does not liquidate all assets in one tax year.

`summary.csv` reports expected/median spendable wealth, percentiles, worst-decile
mean, spending success, and expected cumulative real shortfall. Best-strategy
probabilities split ties so credits sum to one. Separate unique-win and tied-best
probabilities prevent depleted portfolios from appearing to win outright.
`pairwise.csv` reports wins, ties, mean differences, Wilson-style probability
intervals, and normal paired-mean intervals. Intervals reflect finite Monte Carlo
sampling under the model, not uncertainty about whether assumptions are correct;
adaptive grouping creates dependence, so its intervals are approximate.

Annual balances use end-of-year price indices for real conversion. Annual cash
flows use beginning-year prices. Outcome bands are pointwise 10th/90th percentiles,
not confidence intervals. Cumulative shortfalls are expressed in starting-year
dollars, with no additional time discounting. A sub-cent numerical residual is
not treated as a spending failure.

## Interactive graphic — phase 6

`dashboard.html` is a self-contained offline report. It consumes exported
`chart_data.json` embedded in the HTML; no financial calculations are implemented
in JavaScript. Explore account balances, contributions, taxes, withdrawals,
shortfalls, RMDs, and allocations, switch nominal/real views, select a shared
scenario, animate age, and export the chart as PNG. Retirement, hypothetical
uncertainty, and scheduled policy changes are marked. `wealth.png` is the static
shareable chart. The first 30 scenarios are exported alongside full-population
percentiles and terminal wealth. There is no server or external chart dependency.

## Adaptive allocation — phase 7

Each year, group observed households by real-income and real-wealth quantiles.
For each group's median current income, balances, basis, prices, and observable
policy multiplier, generate independent conditional planning scenarios. Batch the
planning states for performance; every candidate receives the same draws within
its group. Evaluate the candidate Roth shares through the remaining lifetime
using the same lifecycle and tax functions as fixed strategies.

Choose the candidate maximizing expected real terminal spendable wealth minus
`risk_penalty` times its standard deviation (default penalty zero). Report planning
spending-failure probabilities separately. Candidates assume their allocation
remains fixed thereafter; the actual policy replans next year. Numerical ties
prefer a candidate closest to 50% Roth. Zero-budget households do not need planning.
No future evaluation income, returns, spending, inflation, or unrevealed policy
shock enters a decision. Known future snapshots are assumed announced.

This is an approximate grouped receding-horizon policy, **not a globally optimal
solution**. Eight planning paths per group in the baseline are a fast demonstration;
increase planning paths and group resolution and check convergence before drawing
conclusions. Independent planning random streams avoid hindsight optimization,
but grouping uses the current evaluation cohort's states; it is not a fitted
universal policy. It may underperform fixed allocations. `allocation_decisions.csv`
records candidate estimates and selections; `allocation_by_age_income.csv` records
observed allocations and switching frequencies across real-income bands.

## Sensitivity and performance — phase 8

`--sensitivity` runs matched-seed, one-at-a-time perturbations of returns, income
growth, inflation, volatility, policy uncertainty, spending, and retirement age.
It ranks changes in expected Roth-minus-Traditional terminal wealth. The baseline
and perturbations use fixed 0%/100% Roth strategies, irrespective of the display
strategy list. Perturbation sizes differ, so this is a local scenario ranking,
not a scale-free global or causal importance estimate. The CLI limits these runs
to 200 paths; use the Python API for more.

`--profile` saves `cpu_profile.prof` and `profile.txt`. Initial profiling showed
repeated small conditional rollouts dominated adaptive runtime. Batching observed
household groups reduced a profiled 1,000-path, 60-year adaptive run to roughly
16 seconds in this environment. A fixed 1,000-path run took roughly 1.2 seconds.
Timings are illustrative and hardware dependent. The engine vectorizes across
paths with NumPy; TensorFlow/GPU acceleration is deferred until an equivalent
backend is justified by profiling and validated against these cash flows.
