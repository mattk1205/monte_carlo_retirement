"""Versioned ordinary-income taxes, without payroll taxes or tax credits."""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from types import MappingProxyType

import yaml

from .config import number

FILING_STATUSES = {"single", "married_filing_jointly"}


def _keys(data: object, expected: set[str], context: str) -> Mapping:
    if not isinstance(data, Mapping) or set(data) != expected:
        raise ValueError(f"{context} must contain exactly {sorted(expected)}")
    return data


@dataclass(frozen=True)
class TaxBracket:
    lower: float
    rate: float

    def __post_init__(self) -> None:
        number("bracket lower bound", self.lower)
        number("bracket rate", self.rate)
        if self.rate >= 1:
            raise ValueError("bracket rate must be below 1")


@dataclass(frozen=True)
class TaxSchedule:
    deduction: float
    brackets: tuple[TaxBracket, ...]

    def __post_init__(self) -> None:
        number("deduction", self.deduction)
        brackets = tuple(self.brackets)
        if not brackets or not all(isinstance(b, TaxBracket) for b in brackets):
            raise ValueError("brackets must be a nonempty sequence of TaxBracket")
        if brackets[0].lower != 0 or any(
            left.lower >= right.lower for left, right in zip(brackets, brackets[1:])
        ):
            raise ValueError("brackets must start at zero and strictly increase")
        object.__setattr__(self, "brackets", brackets)

    def tax(self, gross_income: float, *, itemized_deduction: float = 0) -> float:
        number("gross_income", gross_income)
        number("itemized_deduction", itemized_deduction)
        taxable = max(0, gross_income - max(self.deduction, itemized_deduction))
        total = 0.0
        for index, bracket in enumerate(self.brackets):
            upper = (
                self.brackets[index + 1].lower
                if index + 1 < len(self.brackets)
                else taxable
            )
            total += max(0, min(taxable, upper) - bracket.lower) * bracket.rate
        return total

    def indexed(self, factor: float) -> "TaxSchedule":
        number("index factor", factor)
        if factor == 0:
            raise ValueError("index factor must be positive")
        return TaxSchedule(
            self.deduction * factor,
            tuple(TaxBracket(b.lower * factor, b.rate) for b in self.brackets),
        )


@dataclass(frozen=True)
class JurisdictionPolicy:
    filing_statuses: Mapping[str, TaxSchedule]
    retirement_taxable_fraction: float = 1

    def __post_init__(self) -> None:
        profiles = dict(self.filing_statuses)
        if set(profiles) != FILING_STATUSES or not all(
            isinstance(s, TaxSchedule) for s in profiles.values()
        ):
            raise ValueError("each jurisdiction requires single and joint schedules")
        number("retirement_taxable_fraction", self.retirement_taxable_fraction)
        if self.retirement_taxable_fraction > 1:
            raise ValueError("retirement_taxable_fraction must be <= 1")
        object.__setattr__(self, "filing_statuses", MappingProxyType(profiles))


@dataclass(frozen=True)
class TaxIncome:
    wages: float = 0
    traditional_contribution: float = 0
    ordinary_income: float = 0
    traditional_withdrawal: float = 0
    qualified_roth_withdrawal: float = 0

    def __post_init__(self) -> None:
        for name in (
            "wages",
            "traditional_contribution",
            "ordinary_income",
            "traditional_withdrawal",
            "qualified_roth_withdrawal",
        ):
            number(name, getattr(self, name))
        if self.traditional_contribution > self.wages:
            raise ValueError("Traditional employee contributions cannot exceed wages")


@dataclass(frozen=True)
class TaxResult:
    federal: float
    state: float

    @property
    def total(self) -> float:
        return self.federal + self.state


@dataclass(frozen=True)
class TaxPolicy:
    policy_id: str
    effective_year: int
    description: str
    sources: tuple[str, ...]
    federal: JurisdictionPolicy
    states: Mapping[str, JurisdictionPolicy]

    def __post_init__(self) -> None:
        if type(self.effective_year) is not int or self.effective_year < 1:
            raise ValueError("effective_year must be a positive integer")
        if not isinstance(self.policy_id, str) or not self.policy_id.strip():
            raise ValueError("policy_id must be nonempty")
        if not isinstance(self.description, str) or not self.description.strip():
            raise ValueError("description must be nonempty")
        if (
            not isinstance(self.sources, (list, tuple))
            or not self.sources
            or not all(
                isinstance(source, str) and source.strip() for source in self.sources
            )
        ):
            raise ValueError("sources must be a nonempty list of source descriptions")
        if not isinstance(self.federal, JurisdictionPolicy):
            raise ValueError("federal policy must be a JurisdictionPolicy")
        if not self.states or not all(
            isinstance(key, str) and key.strip() and isinstance(p, JurisdictionPolicy)
            for key, p in self.states.items()
        ):
            raise ValueError("states must map state identifiers to policies")
        # Sufficient bound for increasing after-tax contribution costs.
        federal_max = max(
            b.rate for s in self.federal.filing_statuses.values() for b in s.brackets
        )
        for state in self.states.values():
            state_max = max(
                b.rate for s in state.filing_statuses.values() for b in s.brackets
            )
            if federal_max + state_max >= 1:
                raise ValueError("combined marginal income-tax rates must stay below 1")
        object.__setattr__(self, "sources", tuple(self.sources))
        object.__setattr__(self, "states", MappingProxyType(dict(self.states)))

    def calculate(
        self,
        income: TaxIncome,
        *,
        filing_status: str,
        state: str,
        federal_itemized_deduction: float = 0,
        state_itemized_deduction: float = 0,
    ) -> TaxResult:
        if filing_status not in FILING_STATUSES:
            raise ValueError(f"unsupported filing status: {filing_status}")
        if state not in self.states:
            raise ValueError(f"unsupported state policy: {state}")
        ordinary = (
            income.wages - income.traditional_contribution + income.ordinary_income
        )

        def tax(jurisdiction: JurisdictionPolicy, itemized: float) -> float:
            gross = ordinary + (
                income.traditional_withdrawal * jurisdiction.retirement_taxable_fraction
            )
            return jurisdiction.filing_statuses[filing_status].tax(
                gross, itemized_deduction=itemized
            )

        return TaxResult(
            tax(self.federal, federal_itemized_deduction),
            tax(self.states[state], state_itemized_deduction),
        )

    def indexed(self, factor: float) -> "TaxPolicy":
        """Explicit hypothetical scaling of all thresholds and deductions.

        No legal annual rounding or automatic inflation forecast is assumed.
        """

        def jurisdiction(policy: JurisdictionPolicy) -> JurisdictionPolicy:
            return JurisdictionPolicy(
                {
                    key: value.indexed(factor)
                    for key, value in policy.filing_statuses.items()
                },
                policy.retirement_taxable_fraction,
            )

        return replace(
            self,
            policy_id=f"{self.policy_id}:indexed:{factor}",
            description=f"Hypothetical indexed variant: {self.description}",
            federal=jurisdiction(self.federal),
            states={key: jurisdiction(value) for key, value in self.states.items()},
        )


def _jurisdiction(data: object) -> JurisdictionPolicy:
    data = _keys(
        data, {"filing_statuses", "retirement_taxable_fraction"}, "jurisdiction"
    )
    profiles = _keys(data["filing_statuses"], FILING_STATUSES, "filing_statuses")
    parsed = {}
    for name, profile in profiles.items():
        profile = _keys(profile, {"deduction", "brackets"}, "tax schedule")
        brackets = profile["brackets"]
        if not isinstance(brackets, list):
            raise ValueError("brackets must be a list")
        parsed[name] = TaxSchedule(
            profile["deduction"],
            tuple(
                TaxBracket(**_keys(b, {"lower", "rate"}, "bracket")) for b in brackets
            ),
        )
    return JurisdictionPolicy(parsed, data["retirement_taxable_fraction"])


def load_tax_policy(path: str | Path) -> TaxPolicy:
    with Path(path).open() as stream:
        data = yaml.safe_load(stream)
    data = _keys(
        data,
        {"policy_id", "effective_year", "description", "sources", "federal", "states"},
        "policy",
    )
    if not isinstance(data["states"], dict):
        raise ValueError("states must be a mapping")
    return TaxPolicy(
        policy_id=data["policy_id"],
        effective_year=data["effective_year"],
        description=data["description"],
        sources=data["sources"],
        federal=_jurisdiction(data["federal"]),
        states={
            name: _jurisdiction(profile) for name, profile in data["states"].items()
        },
    )


@dataclass(frozen=True)
class TaxPolicyTimeline:
    policies: tuple[TaxPolicy, ...]

    def __post_init__(self) -> None:
        policies = tuple(
            sorted(self.policies, key=lambda policy: policy.effective_year)
        )
        if not policies or len({p.effective_year for p in policies}) != len(policies):
            raise ValueError("timeline requires nonempty, unique effective years")
        object.__setattr__(self, "policies", policies)

    def for_year(self, year: int) -> TaxPolicy:
        if type(year) is not int or year < self.policies[0].effective_year:
            raise ValueError("year predates policy timeline or is not an integer")
        return next(p for p in reversed(self.policies) if p.effective_year <= year)


def load_tax_timeline(paths: tuple[str, ...]) -> TaxPolicyTimeline:
    return TaxPolicyTimeline(tuple(load_tax_policy(path) for path in paths))
