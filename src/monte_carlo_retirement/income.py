"""Seeded nominal career income; event multipliers permanently change earnings."""

import numpy as np


def income_paths(config, ages, prices, rng, *, initial_income=None):
    n, years = prices.shape[0], len(ages)
    result = np.zeros((n, years))
    current = np.full(
        n,
        config.annual_income if initial_income is None else initial_income,
        dtype=float,
    )
    e = config.economics
    for t, age in enumerate(ages):
        if t:
            shock = rng.normal(size=n)
            current *= (
                (1 + e.real_income_growth)
                * np.exp(e.income_volatility * shock - e.income_volatility**2 / 2)
                * prices[:, t]
                / prices[:, t - 1]
            )
        if not (t == 0 and initial_income is not None):
            for event in e.income_events:
                if age == event.age:
                    current *= np.where(
                        rng.random(n) < event.probability, event.multiplier, 1
                    )
        result[:, t] = current if age < config.retirement_age else 0
    return result
