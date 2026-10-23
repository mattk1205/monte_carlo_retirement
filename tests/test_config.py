from dataclasses import replace

import pytest

from monte_carlo_retirement.config import load_config


def test_load_baseline():
    config = load_config("configs/baseline.yaml")
    assert config.current_age == 35
    assert config.roth_shares == (0, 0.5, 1)


@pytest.mark.parametrize(
    "updates",
    [
        {"current_age": 65},
        {"retirement_age": 96},
        {"scenario_count": 0},
        {"random_seed": True},
        {"annual_income": float("nan")},
        {"roth_shares": [1.1]},
        {"roth_shares": []},
        {"tax_year": 0},
        {"taxable_basis": -1},
        {"filing_status": ""},
        {"filing_status": "unknown"},
        {"tax_policy_files": []},
        {"tax_policy_files": [1]},
    ],
)
def test_invalid_values(updates):
    with pytest.raises(ValueError):
        replace(load_config("configs/baseline.yaml"), **updates)


@pytest.mark.parametrize("content", ["", "[]", "annual_incom: 1", "annual_income: 1"])
def test_bad_yaml_shape_and_keys(tmp_path, content):
    path = tmp_path / "invalid.yaml"
    path.write_text(content)
    with pytest.raises(ValueError):
        load_config(path)


def test_policy_paths_resolve_relative_to_configuration(tmp_path, monkeypatch):
    from pathlib import Path

    config_path = Path("configs/baseline.yaml").resolve()
    monkeypatch.chdir(tmp_path)
    config = load_config(config_path)
    assert Path(config.tax_policy_files[0]).is_file()
