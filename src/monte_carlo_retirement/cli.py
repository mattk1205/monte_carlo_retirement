"""Display one year's tax-aware contribution accounting."""

import argparse
from dataclasses import replace
from pathlib import Path
from time import perf_counter

from .accounts import AccountBalances, allocate_contributions
from .config import load_config
from .taxes import TaxIncome, load_tax_timeline


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/baseline.yaml")
    parser.add_argument("--year", type=int, help="Override the configured tax year")
    parser.add_argument(
        "--simulate", action="store_true", help="Run all lifecycle phases"
    )
    parser.add_argument("--scenarios", type=int, help="Override Monte Carlo path count")
    parser.add_argument("--output", default="outputs/latest")
    parser.add_argument(
        "--no-adaptive", action="store_true", help="Only fixed allocations"
    )
    parser.add_argument(
        "--sensitivity", action="store_true", help="Run paired assumption perturbations"
    )
    parser.add_argument(
        "--profile", action="store_true", help="Save CPU profile and timing"
    )
    args = parser.parse_args()
    config = load_config(args.config)
    if args.scenarios is not None:
        config = replace(config, scenario_count=args.scenarios)
    if args.no_adaptive:
        config = replace(
            config, optimization=replace(config.optimization, enabled=False)
        )
    if args.simulate:
        from .analysis import export_result, sensitivity_analysis
        from .simulation import simulate

        output = Path(args.output)
        output.mkdir(parents=True, exist_ok=True)
        if args.year is not None:
            config = replace(config, tax_year=args.year)
        profiler = None
        if args.profile:
            import cProfile

            profiler = cProfile.Profile()
            profiler.enable()
        start = perf_counter()
        print(f"Simulating {config.scenario_count:,} shared paths...", flush=True)
        result = simulate(config)
        elapsed = perf_counter() - start
        if profiler:
            profiler.disable()
            profiler.dump_stats(str(output / "cpu_profile.prof"))
            import pstats

            with (output / "profile.txt").open("w") as stream:
                pstats.Stats(profiler, stream=stream).sort_stats(
                    "cumulative"
                ).print_stats(25)
        summary = export_result(result, output, elapsed_seconds=elapsed)
        print(
            summary[
                [
                    "strategy",
                    "median_terminal_real",
                    "probability_best_tie_split",
                    "spending_success_probability",
                ]
            ].to_string(index=False)
        )
        if args.sensitivity:
            print("Running paired sensitivity experiments...", flush=True)
            sensitivity_analysis(
                config, output, scenarios=min(200, config.scenario_count)
            )
        print(
            f"Simulation: {elapsed:.2f}s. Open {(output / 'dashboard.html').resolve()}"
        )
        return
    year = config.tax_year if args.year is None else args.year
    policy = load_tax_timeline(config.tax_policy_files).for_year(year)
    if config.retirement_state not in policy.states:
        parser.error(f"unsupported retirement state: {config.retirement_state}")

    def taxes(net_wages: float) -> float:
        return policy.calculate(
            TaxIncome(wages=net_wages),
            filing_status=config.filing_status,
            state=config.working_state,
        ).total

    before = policy.calculate(
        TaxIncome(wages=config.annual_income),
        filing_status=config.filing_status,
        state=config.working_state,
    )
    balances = AccountBalances(
        config.traditional_balance,
        config.roth_balance,
        config.taxable_balance,
        config.taxable_basis,
    )
    print("Illustrative one-year accounting; limited income-tax model, no simulation.")
    print(f"Tax year: {year}; policy: {policy.policy_id}")
    print(f"Policy assumptions: {policy.description}")
    if year != policy.effective_year:
        print(
            f"Reusing {policy.effective_year} nominal thresholds and deductions; "
            "no automatic inflation indexing."
        )
    print(
        f"Income tax before contributions: federal ${before.federal:,.2f}; "
        f"state ${before.state:,.2f}"
    )
    print(
        f"Annual household savings cost: ${config.annual_after_tax_savings_budget:,.2f}"
    )
    print("Roth share | Traditional | Roth | Taxable | Tax savings | Household cost")
    for share in config.roth_shares:
        plan = allocate_contributions(
            income=config.annual_income,
            budget=config.annual_after_tax_savings_budget,
            contribution_limit=config.employee_contribution_limit,
            roth_share=share,
            income_tax=taxes,
        )
        print(
            f"{share:>9.0%} | {plan.traditional:>11,.2f} | {plan.roth:>9,.2f} | "
            f"{plan.taxable:>9,.2f} | {plan.tax_savings:>11,.2f} | "
            f"{plan.household_cost:>14,.2f}"
        )
        after = balances.contribute(plan)
        print(
            f"  Balances: Traditional ${after.traditional:,.2f}; "
            f"Roth ${after.roth:,.2f}; "
            f"taxable ${after.taxable:,.2f}; basis ${after.taxable_basis:,.2f}"
        )


if __name__ == "__main__":
    main()
