from dataclasses import replace

import numpy as np
import pytest

from monte_carlo_retirement.config import (
    Economics,
    IncomeEvent,
    Optimization,
    load_config,
)
from monte_carlo_retirement.investments import Scenarios, generate_scenarios


@pytest.fixture
def config():
    return replace(load_config("configs/baseline.yaml"), scenario_count=8)


def test_seeded_scenarios_reproduce_without_global_rng(config):
    np.random.seed(123)
    first, end = generate_scenarios(config)
    np.random.seed(456)
    second, end2 = generate_scenarios(config)
    for name in ("income", "returns", "prices", "spending", "policy_multiplier"):
        np.testing.assert_array_equal(getattr(first, name), getattr(second, name))
    np.testing.assert_array_equal(end, end2)
    assert not first.income.flags.writeable
    different, _ = generate_scenarios(config, seed=12)
    assert not np.array_equal(first.returns, different.returns)


def test_zero_volatility_and_event_timing(config):
    e = Economics(
        real_income_growth=0.02,
        income_volatility=0,
        return_mean=0.05,
        return_volatility=0,
        inflation_mean=0.03,
        inflation_volatility=0,
        spending_volatility=0,
        policy_multiplier_volatility=0,
        income_events=(IncomeEvent(36, 0.5),),
    )
    paths, end = generate_scenarios(replace(config, economics=e))
    assert paths.income.shape == (8, 60)
    assert paths.income[0, 0] == 100000
    assert paths.income[0, 1] == pytest.approx(100000 * 1.02 * 1.03 * 0.5)
    assert paths.income[0, 30] == 0
    assert paths.returns[0, 0] == pytest.approx(0.05)
    assert end[0] == pytest.approx(1.03**60)


def test_policy_shock_is_persistent_and_shared(config):
    paths, _ = generate_scenarios(config)
    assert (paths.policy_multiplier[:, :20] == 1).all()
    np.testing.assert_array_equal(
        paths.policy_multiplier[:, 20], paths.policy_multiplier[:, -1]
    )


def test_conditional_planning_uses_observed_income_and_policy(config):
    paths, _ = generate_scenarios(
        config,
        start_index=21,
        initial_income=70000,
        initial_price=2,
        observed_policy_multiplier=1.2,
    )
    assert (paths.income[:, 0] == 70000).all()
    assert (paths.prices[:, 0] == 2).all()
    assert (paths.policy_multiplier == 1.2).all()
    assert paths.ages[0] == 56


@pytest.mark.parametrize(
    "values",
    [
        {"return_mean": -1},
        {"return_volatility": -1},
        {"return_inflation_correlation": 1.1},
        {"index_tax_brackets": 1},
        {"capital_gains_rate": 1},
        {"withdrawal_order": ["roth"]},
        {"valuation_years": 0},
        {"income_events": [dict(age=40, multiplier=1, probability=2)]},
    ],
)
def test_invalid_economic_assumptions(values):
    with pytest.raises(ValueError):
        Economics(**values)


@pytest.mark.parametrize(
    "values",
    [
        {"planning_scenarios": 0},
        {"risk_penalty": -1},
        {"candidate_roth_shares": [1.1]},
        {"enabled": 1},
    ],
)
def test_invalid_optimizer_assumptions(values):
    with pytest.raises(ValueError):
        Optimization(**values)


def test_scenario_boundaries_reject_impossible_returns():
    with pytest.raises(ValueError):
        Scenarios(
            np.array([35]),
            np.zeros((1, 1)),
            -np.ones((1, 1)),
            np.ones((1, 1)),
            np.ones((1, 1)),
            np.ones((1, 1)),
        )
