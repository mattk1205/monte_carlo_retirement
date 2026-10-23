"""Paired strategy statistics, reproducible exports, and controlled sensitivity."""

import hashlib
import json
import platform
from dataclasses import asdict, replace
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from time import perf_counter

import numpy as np
import pandas as pd

from .taxes import load_tax_timeline


def _interval(values):
    # Wilson-style bounds retain nonzero uncertainty at observed probabilities
    # of zero and one. Fractional tie credits use the same conservative bound.
    mean = float(np.mean(values))
    n, z = len(values), 1.96
    denominator = 1 + z * z / n
    center = (mean + z * z / (2 * n)) / denominator
    radius = z * np.sqrt(mean * (1 - mean) / n + z * z / (4 * n * n)) / denominator
    return mean, max(0, center - radius), min(1, center + radius)


def outcome_tables(result):
    wealth = result.terminal_real
    maxima = wealth.max(axis=0)
    is_best = np.isclose(wealth, maxima, rtol=1e-9, atol=0.01)
    counts = is_best.sum(axis=0)
    rows, pairwise = [], []
    for s, strategy in enumerate(result.strategies):
        values = wealth[s]
        p5, p10, median, p90 = np.percentile(values, [5, 10, 50, 90])
        credit = is_best[s] / counts
        probability, low, high = _interval(credit)
        rows.append(
            dict(
                strategy=strategy.name,
                expected_terminal_real=float(values.mean()),
                median_terminal_real=float(median),
                p05_terminal_real=float(p5),
                p10_terminal_real=float(p10),
                p90_terminal_real=float(p90),
                worst_decile_mean_real=float(
                    np.sort(values)[: max(1, int(np.ceil(len(values) * 0.1)))].mean()
                ),
                probability_best_tie_split=probability,
                best_ci_low=low,
                best_ci_high=high,
                probability_unique_best=float((is_best[s] & (counts == 1)).mean()),
                probability_tied_best=float((is_best[s] & (counts > 1)).mean()),
                spending_success_probability=float(
                    (result.cumulative_shortfall_real[s] == 0).mean()
                ),
                expected_cumulative_shortfall_real=float(
                    result.cumulative_shortfall_real[s].mean()
                ),
                expected_retirement_spendable_real=float(
                    np.nanmean(result.retirement_real_spendable[s])
                ),
                median_retirement_spendable_real=float(
                    np.nanmedian(result.retirement_real_spendable[s])
                ),
                median_retirement_account_balance_real=float(
                    np.nanmedian(result.retirement_real_balances[s])
                ),
            )
        )
        for j, other in enumerate(result.strategies):
            if j == s:
                continue
            delta = values - wealth[j]
            tie = np.isclose(values, wealth[j], rtol=1e-9, atol=0.01)
            pwin, win_low, win_high = _interval((delta > 0) & ~tie)
            se = float(delta.std(ddof=1) / np.sqrt(len(delta))) if len(delta) > 1 else 0
            pairwise.append(
                dict(
                    strategy=strategy.name,
                    versus=other.name,
                    win_probability=pwin,
                    win_ci_low=win_low,
                    win_ci_high=win_high,
                    tie_probability=float(tie.mean()),
                    mean_difference_real=float(delta.mean()),
                    mean_difference_ci_low=float(delta.mean() - 1.96 * se),
                    mean_difference_ci_high=float(delta.mean() + 1.96 * se),
                )
            )
    return pd.DataFrame(rows), pd.DataFrame(pairwise)


def allocation_table(result):
    """Observed evaluation allocations by age and real-income band."""
    rows = []
    edges = np.array([0, 50000, 100000, 150000, 250000, np.inf])
    for s, strategy in enumerate(result.strategies):
        for t, age in enumerate(result.paths.ages):
            if age >= result.config.retirement_age:
                continue
            income = result.paths.income[:, t] / result.paths.prices[:, t]
            shares = result.annual["roth_share"][s, :, t]
            for lower, upper in zip(edges, edges[1:]):
                mask = (income >= lower) & (income < upper)
                if not mask.any():
                    continue
                switches = (
                    np.zeros(mask.sum())
                    if t == 0
                    else ~np.isclose(
                        shares[mask], result.annual["roth_share"][s, mask, t - 1]
                    )
                )
                rows.append(
                    dict(
                        strategy=strategy.name,
                        age=int(age),
                        income_lower_real=lower,
                        income_upper_real=upper,
                        scenarios=int(mask.sum()),
                        mean_roth_share=float(shares[mask].mean()),
                        median_roth_share=float(np.median(shares[mask])),
                        switching_fraction=float(switches.mean()),
                    )
                )
    return pd.DataFrame(rows)


def _prices_at_end(result):
    return np.column_stack((result.paths.prices[:, 1:], result.end_prices))


def chart_data(result, *, sample_count=30):
    """Export all financial values; the viewer only selects and draws them."""
    prices = result.paths.prices
    end_prices = _prices_at_end(result)
    n = prices.shape[0]
    sample = np.arange(min(n, sample_count))
    output = dict(
        ages=result.paths.ages.tolist(),
        retirement_age=result.config.retirement_age,
        policy_change_age=result.config.economics.policy_change_age,
        policy_change_ages=[
            result.config.current_age + p.effective_year - result.config.tax_year
            for p in load_tax_timeline(result.config.tax_policy_files).policies
            if p.effective_year > result.config.tax_year
        ],
        scenario_count=n,
        sample_ids=sample.tolist(),
        strategies=[],
        valuation=(
            "Terminal real spendable wealth: equal slices over "
            f"{result.config.economics.valuation_years} years"
        ),
    )
    summary, _ = outcome_tables(result)
    for s, strategy in enumerate(result.strategies):
        entry = dict(name=strategy.name, summary=summary.iloc[s].to_dict(), metrics={})
        for key, array in result.annual.items():
            if key == "roth_share":
                # Null retirement allocations become zero in export with age labels.
                nominal = np.nan_to_num(array[s])
                real = nominal
            else:
                nominal = array[s]
                real = nominal / (
                    end_prices
                    if key in {"portfolio", "traditional", "roth", "taxable", "basis"}
                    else prices
                )
            entry["metrics"][key] = {
                units: dict(
                    p10=np.percentile(values, 10, axis=0).tolist(),
                    median=np.median(values, axis=0).tolist(),
                    p90=np.percentile(values, 90, axis=0).tolist(),
                    samples=values[sample].tolist(),
                )
                for units, values in (("nominal", nominal), ("real", real))
            }
        entry["terminal_real"] = np.histogram(result.terminal_real[s], bins=30)[
            0
        ].tolist()
        entry["histogram_edges"] = np.histogram(result.terminal_real[s], bins=30)[
            1
        ].tolist()
        output["strategies"].append(entry)
    return output


def export_result(result, directory, *, elapsed_seconds=None):
    from .visualization import write_dashboard, write_static_chart

    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    summary, paired = outcome_tables(result)
    summary.to_csv(directory / "summary.csv", index=False)
    allocation_table(result).to_csv(
        directory / "allocation_by_age_income.csv", index=False
    )
    paired.to_csv(directory / "pairwise.csv", index=False)
    terminal = pd.DataFrame(
        result.terminal_real.T, columns=[s.name for s in result.strategies]
    )
    terminal.index.name = "scenario"
    terminal.to_csv(directory / "terminal_wealth.csv")
    pd.DataFrame(result.allocation_decisions).to_csv(
        directory / "allocation_decisions.csv", index=False
    )
    # Selected raw annual paths complement percentile exports without enormous CSVs.
    rows = []
    for s, strategy in enumerate(result.strategies):
        for scenario in range(min(30, result.paths.income.shape[0])):
            for t, age in enumerate(result.paths.ages):
                row = dict(
                    strategy=strategy.name,
                    scenario=scenario,
                    age=int(age),
                    price_index=float(result.paths.prices[scenario, t]),
                )
                row.update(
                    {
                        key: float(value[s, scenario, t])
                        for key, value in result.annual.items()
                    }
                )
                rows.append(row)
    pd.DataFrame(rows).to_csv(directory / "annual_samples.csv", index=False)
    resolved = asdict(result.config)
    versions = {}
    for package in ("numpy", "pandas", "matplotlib", "monte-carlo-retirement"):
        try:
            versions[package] = version(package)
        except PackageNotFoundError:
            versions[package] = "source checkout"
    sources = []
    for name in result.config.tax_policy_files:
        path = Path(name)
        destination = directory / ("policy_" + path.name)
        destination.write_bytes(path.read_bytes())
        sources.append(
            dict(
                file=destination.name,
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            )
        )
    resolved["tax_policy_files"] = [source["file"] for source in sources]
    (directory / "resolved_config.json").write_text(json.dumps(resolved, indent=2))
    metadata = dict(
        schema_version=1,
        python=platform.python_version(),
        versions=versions,
        seed=result.config.random_seed,
        elapsed_seconds=elapsed_seconds,
        policies=sources,
        valuation_years=result.config.economics.valuation_years,
        limitations=(
            "See docs/methodology.md and docs/taxes.md; illustrative inputs, "
            "approximate adaptive policy."
        ),
    )
    (directory / "metadata.json").write_text(json.dumps(metadata, indent=2))
    data = chart_data(result)
    (directory / "chart_data.json").write_text(json.dumps(data, allow_nan=False))
    write_dashboard(data, directory / "dashboard.html")
    write_static_chart(data, directory / "wealth.png")
    return summary


def sensitivity_analysis(config, directory, *, scenarios=200):
    """One-at-a-time paired perturbations; not causal/global importance estimates."""
    from .simulation import simulate
    from .strategies import Strategy

    strategies = (Strategy("Traditional", 0), Strategy("Roth", 1))
    config = replace(
        config,
        scenario_count=scenarios,
        optimization=replace(config.optimization, enabled=False),
    )
    baseline = simulate(config, strategies=strategies, record=False)
    contrast = baseline.terminal_real[-1] - baseline.terminal_real[0]
    specs = [
        ("return_mean", 0.01),
        ("real_income_growth", 0.01),
        ("inflation_mean", 0.01),
        ("return_volatility", 0.04),
        ("policy_multiplier_volatility", 0.10),
        ("annual_retirement_spending", config.annual_retirement_spending * 0.1),
        ("retirement_age", 2),
    ]
    rows = []
    for name, delta in specs:
        for direction in (-1, 1):
            shift = delta * direction
            if hasattr(config.economics, name):
                previous = getattr(config.economics, name)
                floor = 0 if "volatility" in name else -0.99
                value = max(floor, previous + shift)
                shift = value - previous
                changed = replace(
                    config, economics=replace(config.economics, **{name: value})
                )
            else:
                previous = getattr(config, name)
                value = previous + shift
                if name == "retirement_age":
                    value = min(
                        config.planning_end_age - 1,
                        max(60, config.current_age + 1, value),
                    )
                shift = value - previous
                changed = replace(config, **{name: value})
            if shift == 0:
                continue
            start = perf_counter()
            result = simulate(changed, strategies=strategies, record=False)
            difference = result.terminal_real[-1] - result.terminal_real[0]
            rows.append(
                dict(
                    variable=name,
                    perturbation=shift,
                    change_in_roth_minus_traditional_mean_real=float(
                        (difference - contrast).mean()
                    ),
                    mean_roth_minus_traditional_real=float(difference.mean()),
                    scenarios=scenarios,
                    elapsed_seconds=perf_counter() - start,
                )
            )
    table = pd.DataFrame(rows)
    table["absolute_effect"] = table.change_in_roth_minus_traditional_mean_real.abs()
    table = table.sort_values("absolute_effect", ascending=False)
    table.to_csv(Path(directory) / "sensitivity.csv", index=False)
    return table
