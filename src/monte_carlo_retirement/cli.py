"""Display one year's tax-aware contribution accounting."""

import argparse

from .accounts import AccountBalances, allocate_contributions
from .config import load_config
from .taxes import TaxIncome, load_tax_timeline


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/baseline.yaml")
    parser.add_argument("--year", type=int, help="Override the configured tax year")
    args = parser.parse_args()
    config = load_config(args.config)
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
