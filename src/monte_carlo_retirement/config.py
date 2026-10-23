"""Strict configuration for baseline household accounting."""

from dataclasses import dataclass, fields, replace
from math import isfinite
from pathlib import Path

import yaml


def number(name: str, value: object, minimum: float = 0) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not isfinite(value)
        or value < minimum
    ):
        raise ValueError(f"{name} must be a finite number >= {minimum}")


@dataclass(frozen=True)
class BaselineConfig:
    current_age: int
    retirement_age: int
    planning_end_age: int
    filing_status: str
    working_state: str
    retirement_state: str
    annual_income: float
    annual_after_tax_savings_budget: float
    annual_retirement_spending: float
    traditional_balance: float
    roth_balance: float
    taxable_balance: float
    taxable_basis: float
    employee_contribution_limit: float
    tax_year: int
    tax_policy_files: tuple[str, ...]
    roth_shares: tuple[float, ...]
    random_seed: int
    scenario_count: int

    def __post_init__(self) -> None:
        for name in (
            "current_age",
            "retirement_age",
            "planning_end_age",
            "random_seed",
            "scenario_count",
            "tax_year",
        ):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError(f"{name} must be a nonnegative integer")
        if not self.current_age < self.retirement_age < self.planning_end_age:
            raise ValueError("ages must satisfy current < retirement < planning end")
        if self.scenario_count == 0:
            raise ValueError("scenario_count must be positive")
        for name in ("filing_status", "working_state", "retirement_state"):
            if (
                not isinstance(getattr(self, name), str)
                or not getattr(self, name).strip()
            ):
                raise ValueError(f"{name} must be a nonempty string")
        for name in (
            "annual_income",
            "annual_after_tax_savings_budget",
            "annual_retirement_spending",
            "traditional_balance",
            "roth_balance",
            "taxable_balance",
            "taxable_basis",
            "employee_contribution_limit",
        ):
            number(name, getattr(self, name))
        if self.tax_year < 1:
            raise ValueError("tax_year must be positive")
        if self.filing_status not in {"single", "married_filing_jointly"}:
            raise ValueError(
                "supported filing statuses: single, married_filing_jointly"
            )
        if (
            not isinstance(self.tax_policy_files, (list, tuple))
            or not self.tax_policy_files
            or not all(isinstance(p, str) and p.strip() for p in self.tax_policy_files)
        ):
            raise ValueError("tax_policy_files must be a nonempty sequence of paths")
        object.__setattr__(self, "tax_policy_files", tuple(self.tax_policy_files))
        if not isinstance(self.roth_shares, (tuple, list)) or not self.roth_shares:
            raise ValueError("roth_shares must be a nonempty sequence")
        for share in self.roth_shares:
            number("roth_share", share)
            if share > 1:
                raise ValueError("roth shares must be between 0 and 1")
        object.__setattr__(self, "roth_shares", tuple(self.roth_shares))


def load_config(path: str | Path) -> BaselineConfig:
    with Path(path).open() as stream:
        data = yaml.safe_load(stream)
    if not isinstance(data, dict):
        raise ValueError("configuration must be a YAML mapping")
    expected = {field.name for field in fields(BaselineConfig)}
    missing = expected - data.keys()
    unknown = data.keys() - expected
    if missing or unknown:
        raise ValueError(
            f"invalid configuration keys: missing={missing}, unknown={unknown}"
        )
    config = BaselineConfig(**data)
    return replace(
        config,
        tax_policy_files=tuple(
            str((Path(path).resolve().parent / filename).resolve())
            for filename in config.tax_policy_files
        ),
    )
