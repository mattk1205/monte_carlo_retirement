"""Independent RNG streams and immutable economic paths shared by all strategies."""

from dataclasses import dataclass

import numpy as np

from .income import income_paths


def lognormal_parameters(mean, std):
    variance = np.log1p((std / (1 + mean)) ** 2)
    return np.log1p(mean) - variance / 2, np.sqrt(variance)


@dataclass(frozen=True)
class Scenarios:
    ages: np.ndarray
    income: np.ndarray
    returns: np.ndarray
    prices: np.ndarray
    spending: np.ndarray
    policy_multiplier: np.ndarray
    start_index: int = 0

    def __post_init__(self):
        shape = self.income.shape
        if len(shape) != 2 or shape[1] != len(self.ages) or not shape[0]:
            raise ValueError("scenario arrays must have shape (scenarios, years)")
        for name in ("income", "returns", "prices", "spending", "policy_multiplier"):
            value = np.array(getattr(self, name), dtype=float, copy=True)
            if value.shape != shape or not np.isfinite(value).all():
                raise ValueError(f"invalid {name} shape or nonfinite values")
            if name == "returns":
                if (value <= -1).any():
                    raise ValueError("returns must exceed -100%")
            elif (value < 0).any() or (
                name in {"prices", "policy_multiplier"} and (value == 0).any()
            ):
                raise ValueError(f"invalid {name} boundaries")
            value.setflags(write=False)
            object.__setattr__(self, name, value)
        ages = np.array(self.ages, dtype=int, copy=True)
        if not np.array_equal(ages, self.ages) or (np.diff(ages) != 1).any():
            raise ValueError("ages must be consecutive integers")
        ages.setflags(write=False)
        object.__setattr__(self, "ages", ages)


def generate_scenarios(
    config,
    *,
    seed=None,
    start_index=0,
    initial_income=None,
    initial_price=1,
    observed_policy_multiplier=None,
):
    e = config.economics
    ages = np.arange(config.current_age + start_index, config.planning_end_age)
    if not len(ages) or start_index < 0:
        raise ValueError("invalid scenario start")
    n = config.scenario_count
    roots = np.random.SeedSequence(config.random_seed if seed is None else seed).spawn(
        5
    )
    economic_rng, income_rng, spending_rng, policy_rng, _ = (
        np.random.default_rng(root) for root in roots
    )
    z = economic_rng.normal(size=(n, len(ages), 2))
    rho = e.return_inflation_correlation
    inflation_z = rho * z[:, :, 0] + np.sqrt(1 - rho**2) * z[:, :, 1]
    mu, sigma = lognormal_parameters(e.return_mean, e.return_volatility)
    returns = np.exp(mu + sigma * z[:, :, 0]) - 1
    mu, sigma = lognormal_parameters(e.inflation_mean, e.inflation_volatility)
    inflation = np.exp(mu + sigma * inflation_z)
    prices = np.empty((n, len(ages) + 1))
    prices[:, 0] = initial_price
    prices[:, 1:] = initial_price * np.cumprod(inflation, axis=1)
    income = income_paths(
        config, ages, prices[:, :-1], income_rng, initial_income=initial_income
    )
    spending = (
        config.annual_retirement_spending
        * prices[:, :-1]
        * np.exp(
            e.spending_volatility * spending_rng.normal(size=income.shape)
            - e.spending_volatility**2 / 2
        )
    )
    multiplier = np.exp(
        e.policy_multiplier_volatility * policy_rng.normal(size=n)
        - e.policy_multiplier_volatility**2 / 2
    )
    if observed_policy_multiplier is not None:
        multiplier[:] = observed_policy_multiplier
    policy = np.where(ages[None, :] >= e.policy_change_age, multiplier[:, None], 1)
    # Last column supplies end-of-final-year purchasing power.
    paths = Scenarios(
        ages, income, returns, prices[:, :-1], spending, policy, start_index
    )
    end_prices = prices[:, -1].copy()
    end_prices.setflags(write=False)
    return paths, end_prices
