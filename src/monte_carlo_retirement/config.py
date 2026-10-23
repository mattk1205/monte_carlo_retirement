"""Strict configuration for baseline household accounting."""

from dataclasses import MISSING, dataclass, field, fields, replace
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
class IncomeEvent:
    age: int
    multiplier: float
    probability: float = 1

    def __post_init__(self):
        if type(self.age) is not int or self.age < 0:
            raise ValueError("event age must be a nonnegative integer")
        number("event multiplier", self.multiplier)
        number("event probability", self.probability)
        if self.probability > 1:
            raise ValueError("event probability must be <= 1")


@dataclass(frozen=True)
class Economics:
    real_income_growth: float = 0.01
    income_volatility: float = 0.10
    return_mean: float = 0.065
    return_volatility: float = 0.16
    inflation_mean: float = 0.025
    inflation_volatility: float = 0.01
    return_inflation_correlation: float = 0.1
    savings_income_elasticity: float = 1.0
    spending_volatility: float = 0.08
    retirement_other_income: float = 0
    dividend_yield: float = 0.015
    capital_gains_rate: float = 0.15
    index_tax_brackets: bool = False
    index_contribution_limit: bool = True
    policy_change_age: int = 55
    policy_multiplier_volatility: float = 0.15
    rmd_start_age: int = 75
    valuation_years: int = 20
    withdrawal_order: tuple[str, ...] = ("taxable", "traditional", "roth")
    income_events: tuple[IncomeEvent, ...] = ()

    def __post_init__(self):
        for name in ("real_income_growth", "return_mean", "inflation_mean"):
            number(name, getattr(self, name), -0.99)
        for name in (
            "income_volatility",
            "return_volatility",
            "inflation_volatility",
            "savings_income_elasticity",
            "spending_volatility",
            "retirement_other_income",
            "dividend_yield",
            "capital_gains_rate",
            "policy_multiplier_volatility",
        ):
            number(name, getattr(self, name))
        for name in ("dividend_yield", "capital_gains_rate"):
            if getattr(self, name) >= 1:
                raise ValueError(f"{name} must be below 1")
        number("return_inflation_correlation", self.return_inflation_correlation, -1)
        if self.return_inflation_correlation > 1:
            raise ValueError("correlation must be <= 1")
        for name in ("index_tax_brackets", "index_contribution_limit"):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"{name} must be boolean")
        for name in ("policy_change_age", "rmd_start_age", "valuation_years"):
            if type(getattr(self, name)) is not int or getattr(self, name) < 1:
                raise ValueError(f"{name} must be a positive integer")
        if self.rmd_start_age < 73:
            raise ValueError("supported RMD start ages are 73 or later")
        if not isinstance(self.withdrawal_order, (list, tuple)) or (
            len(self.withdrawal_order) != 3
            or set(self.withdrawal_order) != {"taxable", "traditional", "roth"}
        ):
            raise ValueError("withdrawal_order must name each account exactly once")
        object.__setattr__(self, "withdrawal_order", tuple(self.withdrawal_order))
        if not isinstance(self.income_events, (list, tuple)):
            raise ValueError("income_events must be a sequence")
        events = tuple(
            IncomeEvent(**event) if isinstance(event, dict) else event
            for event in self.income_events
        )
        if not all(isinstance(event, IncomeEvent) for event in events):
            raise ValueError("invalid income event")
        object.__setattr__(self, "income_events", events)


@dataclass(frozen=True)
class Optimization:
    enabled: bool = True
    planning_scenarios: int = 8
    income_groups: int = 3
    wealth_groups: int = 2
    candidate_roth_shares: tuple[float, ...] = (0, 0.5, 1)
    risk_penalty: float = 0

    def __post_init__(self):
        if type(self.enabled) is not bool:
            raise ValueError("optimizer enabled must be boolean")
        for name in ("planning_scenarios", "income_groups", "wealth_groups"):
            if type(getattr(self, name)) is not int or getattr(self, name) < 1:
                raise ValueError(f"{name} must be a positive integer")
        if not isinstance(self.candidate_roth_shares, (list, tuple)) or not (
            self.candidate_roth_shares
        ):
            raise ValueError("candidate_roth_shares must be nonempty")
        for share in self.candidate_roth_shares:
            number("candidate_roth_share", share)
            if share > 1:
                raise ValueError("candidate shares must be <= 1")
        object.__setattr__(
            self, "candidate_roth_shares", tuple(self.candidate_roth_shares)
        )
        number("risk_penalty", self.risk_penalty)


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
    economics: Economics = field(default_factory=Economics)
    optimization: Optimization = field(default_factory=Optimization)

    def __post_init__(self) -> None:
        for name, cls in (("economics", Economics), ("optimization", Optimization)):
            value = getattr(self, name)
            if isinstance(value, dict):
                try:
                    value = cls(**value)
                except TypeError as exc:
                    raise ValueError(f"invalid {name} fields: {exc}") from exc
            if not isinstance(value, cls):
                raise ValueError(f"invalid {name} configuration")
            object.__setattr__(self, name, value)
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
        if self.retirement_age < 60:
            raise ValueError("retirement before age 60 requires early-withdrawal rules")
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
    required = {
        f.name
        for f in fields(BaselineConfig)
        if f.default is MISSING and f.default_factory is MISSING
    }
    missing = required - data.keys()
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
