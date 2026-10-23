# Traditional vs. Roth 401(k) Monte Carlo Simulation

Compare Traditional, Roth, mixed, and adaptive employee contributions at equal
household cash cost across shared randomized lifetimes. Report probabilities,
outcome magnitudes, and downside risk rather than a binary recommendation.

## Run the simulation

From the repository root, use the project interpreter explicitly:

```bash
python3.12 -m venv .venv                          # only if absent
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pip install --no-deps --no-build-isolation -e .
.venv/bin/python -m monte_carlo_retirement.cli --simulate --scenarios 1000 --output outputs/demo
```

Open `outputs/demo/dashboard.html` in a browser. It works offline and supports
animated lifetime paths, uncertainty bands, individual scenarios, nominal/real
views, contribution allocations, spending shortfalls, and PNG export. The static
chart is `outputs/demo/wealth.png`. No website account or server is needed.

```bash
# Faster fixed-strategy run, profiling, and local sensitivity experiments
.venv/bin/python -m monte_carlo_retirement.cli --simulate --scenarios 10000 --no-adaptive --profile --sensitivity
# Alternative future policy
.venv/bin/python -m monte_carlo_retirement.cli --simulate --config configs/scenarios/higher_taxes.yaml --scenarios 1000
# Original one-year tax/accounting demonstration
.venv/bin/python -m monte_carlo_retirement.cli --config configs/baseline.yaml
# Small reproducible example
.venv/bin/python -m monte_carlo_retirement.cli --simulate --config configs/scenarios/quick_demo.yaml --output outputs/quick-demo
```

`retirement` is the installed CLI alias. Without an editable install, prefix module
commands with `PYTHONPATH=src`. The default count comes from the configuration
(10,000 in the baseline). Adaptive planning costs more than fixed allocations;
`--no-adaptive` skips it. No GPU is required. Dependencies are not version-locked;
run metadata records installed versions.

## Illustrative baseline and scope

A synthetic single Texas taxpayer starts at age 35, retires at 65, and plans
through age 94. Initial annual income is $100,000, after-tax savings $15,000, and
retirement spending $60,000 in starting-year dollars. Initial balances are
$100,000 Traditional, $25,000 Roth, and $10,000 taxable with $8,000 basis.

`configs/baseline.yaml` explicitly specifies income growth/volatility and major
income events, nominal return/inflation distributions, spending uncertainty,
hypothetical future rate uncertainty, withdrawal order, indexing, and planning
resolution. The $24,000 contribution limit and flat 15% federal gains rate are
**illustrative assumptions**, not a complete current-law implementation.
Federal ordinary-income brackets and base standard deductions use sourced 2026
data. Texas and a hypothetical progressive state are included. Tax snapshots
persist until replaced; the baseline freezes nominal thresholds explicitly.

Traditional tax savings are reinvested. Working contributions arrive at year end;
retirement withdrawals occur at the beginning. Taxes, taxable basis, RMDs, and
spending shortfalls are tracked. After-tax wealth is valued through a gradual
withdrawal convention, not a flat haircut or one-year liquidation.

The adaptive policy uses separate conditional planning simulations of grouped
current states. It is approximate and can underperform fixed allocations. Increase
its planning count and grouping resolution to assess convergence. Read
[methodology](docs/methodology.md), [accounting](docs/accounting.md), and
[tax limitations](docs/taxes.md) before interpreting results.

## Exported results

Each run saves:

- `summary.csv`, `pairwise.csv`: wealth, risks, wins/ties, and sampling intervals.
- `terminal_wealth.csv`: every scenario's terminal real spendable wealth.
- `annual_samples.csv`, `chart_data.json`: raw sample paths and population bands.
- `allocation_decisions.csv`, `allocation_by_age_income.csv`: planning choices,
  age/income allocations, and switching frequencies.
- `resolved_config.json`, policy snapshots, `metadata.json`: reproducibility inputs.
- `dashboard.html`, `wealth.png`: offline interactive and static graphics.
- Optional `sensitivity.csv`, `profile.txt`, `cpu_profile.prof`.

Example configuration lives in `configs/scenarios/quick_demo.yaml`. Generated
results stay in ignored `outputs/`; rerun the example to reproduce its artifacts.

## Development and roadmap

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check src tests
.venv/bin/python -m ruff format --check src tests
```

Use four-space indentation, `snake_case` functions, `PascalCase` classes, explicit
units, and floating-point tolerances. Node is optional for the JavaScript DOM-stub
smoke test; Python tests cover deterministic and stochastic financial invariants.
A DOM-stub test does not replace a visual browser review.

| Phase | Implemented scope |
|---|---|
| 1 | Strict configuration, immutable balances, equal-cost contributions |
| 2 | Progressive ordinary-income taxes and explicit policy timelines |
| 3 | Seeded economic scenario generation |
| 4 | Annual accumulation, retirement, withdrawal taxes, RMDs, shortfalls |
| 5 | Paired results, after-tax wealth, distributions, reproducible exports |
| 6 | Offline interactive simulation graphic and static export |
| 7 | Approximate adaptive allocation with independent conditional planning |
| 8 | Local sensitivity experiments, CPU profiling, and batched NumPy execution |

`src/monte_carlo_retirement/` contains the implementation; `tests/` contains pytest
checks, `configs/` holds assumptions, `data/tax_policy/` holds versioned schedules,
and `docs/` explains the model. Financial logic is separate from visualization.
Future extensions include richer state rules, age-related deductions, actual
capital-gains brackets, Social Security, employer contributions, and validated GPU
execution. They are not part of the current model.
