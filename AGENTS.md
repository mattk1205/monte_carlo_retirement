# Repository Guidelines

## Project Objective and Current Status

Build a Python Monte Carlo simulation comparing Traditional, Roth, fixed mixed,
and adaptive 401(k) contribution strategies at equal after-tax household cost.
Quantify probabilities, magnitudes, and downside risk rather than producing a
binary recommendation.

Phases 1–8 have initial implementations: validated configuration, account and tax
engines, seeded economic paths, annual lifecycle simulation, paired reporting,
an offline interactive graphic, approximate adaptive allocation, local sensitivity,
and CPU profiling. The original one-year CLI demonstration remains available.
Adaptive grouping and simplified tax features are deliberate scope limits; see
`docs/methodology.md` and `docs/taxes.md` before interpreting outputs. GPU execution
and broader financial features remain future extensions, not implemented claims.

## Project Structure

- `src/monte_carlo_retirement/`: Python application package.
  - `config.py`: validated household and scenario configuration.
  - `accounts.py`: balances, taxable basis, and contribution cash flows.
  - `taxes.py`: progressive taxes and versioned policy timelines.
  - `cli.py`: accounting demo, lifecycle runs, exports, sensitivity, profiling.
  - `income.py`: career income paths and permanent major income events.
  - `investments.py`: seeded returns, inflation, and immutable shared scenarios.
  - `strategies.py`: fixed and adaptive contribution strategy identities.
  - `simulation.py`: annual accumulation, withdrawals, taxes, RMDs, and valuation.
  - `optimization.py`: grouped conditional annual allocation evaluation.
  - `analysis.py`: paired statistics, exports, and local sensitivity analysis.
  - `visualization.py`, `dashboard.html`: static and offline interactive graphics.
- `tests/`: configuration validation, accounting, and tax tests; pytest settings
  live in `pyproject.toml`.
- `configs/`: synthetic baseline and scenario YAML inputs.
- `data/tax_policy/`: versioned tax snapshots with source descriptions.
- `docs/`: accounting assumptions and tax methodology.
- `outputs/`: generated results, excluded from version control.

Keep sample inputs separate from generated results. Update `README.md` when
introducing modules, commands, configuration fields, or changes in supported scope.

## Implementation Roadmap

1. **Configuration and accounting — implemented.** Strict inputs, immutable
   balances, taxable basis, and equal-household-cost employee contributions.
2. **Tax engine — implemented.** Progressive ordinary-income federal/state taxes,
   deductions, and explicit policy timelines. See `docs/taxes.md` for limitations.
3. **Economic scenario generation — implemented.** Configurable income growth,
   volatility, major income events, investment returns, and inflation. Generate
   seeded annual paths through the planning horizon. Document distributions,
   units, indexing, and event timing. Validate deterministic cases, reproducibility,
   valid income/return boundaries, and scenario dimensions.
4. **Annual lifecycle simulation — implemented.** Connect scenarios to contributions,
   compounding, retirement withdrawals, taxes, and spending shortfalls. Compare
   fixed allocations against shared scenario paths. Define annual cash-flow timing
   and withdrawal order explicitly.
5. **Results and reporting — implemented.** Export paired strategy win/tie probabilities,
   expected and median after-tax wealth, downside percentiles, spending success,
   outcome tables, and charts.
6. **Interactive simulation graphic — implemented.** Animate lifetime wealth paths with median
   curves and uncertainty bands. Support nominal/real-dollar views, individual
   scenario exploration, retirement and policy-change markers, and allocation
   switches as adaptive strategies become available. Show contributions, taxes,
   withdrawals, spending shortfalls, distributions, and strategy win probabilities.
   Consume the simulation's exported results; do not duplicate financial logic.
   Include reproducible example data and a static export for sharing.
7. **Adaptive allocation and optimization — approximate implementation.** Evaluate annual Traditional/Roth
   allocations using current income, marginal taxes, expected future income,
   remaining horizon, and uncertainty. Use only information available at the
   decision date, with separate conditional planning simulations. Compare dynamic
   strategies with fixed strategies and analyze switching by age and income.
8. **Sensitivity and performance — local experiments and CPU profiling implemented.** Identify influential assumptions and allocation
   patterns. Profile realistic workloads before adding acceleration. Broaden
   financial features as explicitly scoped and document their assumptions.

Preserve these phase numbers when referring to work. Record scope changes in this
roadmap and the README. Planning a phase does not mean its features exist.

## Simulation Methodology and Constraints

- Evaluate all strategies on the same generated income, return, inflation, and
  tax-policy paths so comparisons are paired.
- Support explicit random seeds. Keep scenario generation separate from strategy
  decisions so changing strategies does not change the economic paths.
- Model annual accumulation and retirement periods. Document whether each cash
  flow occurs before or after investment growth.
- Preserve equal after-tax economic cost: reinvest Traditional tax savings and
  deposit cash exceeding employee contribution limits into taxable investments.
- Preserve contribution caps, earned-income constraints, nonnegative balances,
  and cash-flow conservation. Taxable basis may exceed value after losses.
- Use identical asset allocations across tax strategies initially. State return
  distributions and dependencies explicitly rather than assuming forecasts.
- Distinguish nominal dollars, constant starting-year dollars, account balances,
  and spendable after-tax wealth. Specify which inputs are inflation-indexed.
- Tax snapshots persist until replaced; indexing is explicit, not automatic.
  Label hypothetical policies and illustrative limits accordingly.
- Specify retirement spending and withdrawal order, calculate associated taxes,
  and record unmet spending when assets run out.
- Avoid treating Traditional balances as fully spendable or implicitly assuming
  all retirement assets are liquidated in one year.
- Adaptive decisions must not use future realized outcomes. Make the optimization
  objective explicit and configurable; the proposed initial objective is expected
  real after-tax terminal wealth, with spending failure and downside risk reported
  separately.
- Consult `docs/accounting.md` and `docs/taxes.md` before extending financial logic.
  Document model exclusions and new assumptions alongside implementation.

## Environment and Development Commands

Python 3.12 or newer is required. From the repository root, create the environment
if absent and install dependencies and the editable package:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pip install --no-deps --no-build-isolation -e .
```

Run the existing demonstration, lifecycle simulation, and checks:

```bash
.venv/bin/python -m monte_carlo_retirement.cli --config configs/baseline.yaml
.venv/bin/python -m monte_carlo_retirement.cli --simulate --scenarios 1000 --output outputs/demo
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check src tests
.venv/bin/python -m ruff format --check src tests
```

Use the project interpreter explicitly across shell invocations. `pyproject.toml`
registers the `retirement` CLI and configures pytest and Ruff. Runtime dependencies
are in `requirements.txt`; development dependencies are in `requirements-dev.txt`.
Versions are not locked. TensorFlow's CUDA extra is declared for future work;
the current NumPy lifecycle engine does not import TensorFlow or require a GPU.
Do not assume GPU availability in the execution environment.

## Coding Style and Testing

Use four-space indentation, descriptive `snake_case` names, `PascalCase` classes,
and Ruff formatting/linting. State units explicitly for currency, percentages,
returns, ages, and time periods. Keep financial calculations separate from CLI,
reporting, and visualization code.

Add tests with new functionality in `tests/test_*.py`. Use descriptive behavior
names. For stochastic features, test seeded reproducibility, deterministic and
boundary cases, and numerical invariants. Use tolerances for floating-point money;
round only for display. Test accounting conservation, tax bracket crossings,
policy transitions, and contribution constraints when affected. No coverage
threshold is configured. Run the relevant tests and Ruff checks before completion.

## Commits, Pull Requests, and Security

Inspect available Git history for commit conventions. If none are established,
use concise imperative subjects, such as `Add seeded income paths`.
PRs should describe behavior, financial assumptions, validation, and changes to
numerical outputs. Link relevant issues and include screenshots for UI changes.

Keep credentials, personal financial data, and local configuration out of version
control. Use synthetic examples and document configuration without secrets.
