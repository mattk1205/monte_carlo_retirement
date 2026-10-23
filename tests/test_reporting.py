import json
from dataclasses import replace

import numpy as np

from monte_carlo_retirement.analysis import chart_data, export_result, outcome_tables
from monte_carlo_retirement.config import Economics, Optimization, load_config
from monte_carlo_retirement.simulation import simulate
from monte_carlo_retirement.strategies import Strategy


def small_result():
    config = replace(
        load_config("configs/baseline.yaml"),
        current_age=64,
        retirement_age=65,
        planning_end_age=67,
        scenario_count=3,
        economics=Economics(),
        optimization=Optimization(enabled=False),
    )
    return simulate(config, strategies=(Strategy("A", 0), Strategy("B", 0)))


def test_identical_strategies_split_ties_and_pairwise_probabilities():
    result = small_result()
    summary, pairwise = outcome_tables(result)
    np.testing.assert_allclose(summary.probability_best_tie_split, 0.5)
    np.testing.assert_allclose(summary.probability_tied_best, 1)
    np.testing.assert_allclose(pairwise.tie_probability, 1)
    np.testing.assert_allclose(pairwise.win_probability, 0)
    np.testing.assert_allclose(pairwise.mean_difference_real, 0)


def test_export_creates_offline_report_and_reproducible_data(tmp_path):
    result = small_result()
    export_result(result, tmp_path)
    data = json.loads((tmp_path / "chart_data.json").read_text())
    assert data == chart_data(result)
    assert (tmp_path / "wealth.png").stat().st_size > 1000
    html = (tmp_path / "dashboard.html").read_text()
    assert "__SIMULATION_DATA__" not in html
    assert "https://" not in html
    assert 'type="application/json"' in html
    metadata = json.loads((tmp_path / "metadata.json").read_text())
    assert metadata["seed"] == 42
    assert metadata["policies"][0]["sha256"]
    assert len(data["strategies"][0]["metrics"]["portfolio"]["real"]["median"]) == 3


def test_report_escapes_script_closing_labels(tmp_path):
    from monte_carlo_retirement.visualization import write_dashboard

    data = chart_data(small_result())
    data["strategies"][0]["name"] = "</script><script>alert(1)</script>"
    write_dashboard(data, tmp_path / "test.html")
    assert "</script><script>alert(1)" not in (tmp_path / "test.html").read_text()


def test_dashboard_controls_with_node_dom_stub(tmp_path):
    import shutil
    import subprocess
    from pathlib import Path

    import pytest

    from monte_carlo_retirement.visualization import write_dashboard

    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is optional for dashboard JavaScript smoke test")
    path = tmp_path / "dashboard.html"
    write_dashboard(chart_data(small_result()), path)
    subprocess.run(
        [node, str(Path(__file__).with_name("dashboard_smoke.cjs")), str(path)],
        check=True,
        capture_output=True,
        text=True,
    )


def test_exported_configuration_reloads_with_local_policy_snapshots(tmp_path):
    result = small_result()
    export_result(result, tmp_path)
    config = load_config(tmp_path / "resolved_config.json")
    assert config.tax_policy_files[0].startswith(str(tmp_path))
    from monte_carlo_retirement.taxes import load_tax_timeline

    assert (
        load_tax_timeline(config.tax_policy_files).for_year(2026).effective_year == 2026
    )


def test_allocation_table_uses_observed_ages_and_shares():
    from monte_carlo_retirement.analysis import allocation_table

    result = small_result()
    table = allocation_table(result)
    assert table.age.unique().tolist() == [64]
    assert (table.mean_roth_share == 0).all()
    assert (table.switching_fraction == 0).all()
