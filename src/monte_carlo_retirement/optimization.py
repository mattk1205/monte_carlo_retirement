"""Approximate receding-horizon choices from independent conditional rollouts."""

from dataclasses import replace

import numpy as np

from .investments import Scenarios, generate_scenarios
from .strategies import Strategy


def choose_allocations(config, paths, t, balances, basis, budget):
    """Group observed states and batch independent planning paths for their medians.

    Candidates use fixed allocations thereafter; the policy replans next year.
    Future evaluation paths are never read. Grouping and finite Monte Carlo make
    this approximate, not globally optimal. All candidates share planning draws.
    """
    from .simulation import simulate

    opt = config.optimization
    income = paths.income[:, t]
    price = paths.prices[:, t]
    wealth = balances.sum(axis=1) / price
    income_edges = np.quantile(
        income / price, np.linspace(0, 1, opt.income_groups + 1)[1:-1]
    )
    wealth_edges = np.quantile(wealth, np.linspace(0, 1, opt.wealth_groups + 1)[1:-1])
    groups = np.searchsorted(income_edges, income / price) * opt.wealth_groups + (
        np.searchsorted(wealth_edges, wealth)
    )
    chosen = np.full(len(income), 0.5)
    decisions, batches, end_batches, balance_batches, basis_batches, masks = (
        [],
        [],
        [],
        [],
        [],
        [],
    )
    candidates = tuple(
        Strategy(f"candidate {share}", share) for share in opt.candidate_roth_shares
    )
    planning_config = replace(config, scenario_count=opt.planning_scenarios)
    start_index = paths.start_index + t
    for group in np.unique(groups):
        mask = (groups == group) & (budget > 0)
        if not mask.any():
            continue
        observed = None
        if paths.ages[t] >= config.economics.policy_change_age:
            observed = float(np.median(paths.policy_multiplier[mask, t]))
        planning_paths, end_prices = generate_scenarios(
            planning_config,
            seed=[config.random_seed, 27011, start_index, int(group)],
            start_index=start_index,
            initial_income=float(np.median(income[mask])),
            initial_price=float(np.median(price[mask])),
            observed_policy_multiplier=observed,
        )
        batches.append(planning_paths)
        end_batches.append(end_prices)
        balance_batches.append(
            np.tile(np.median(balances[mask], axis=0), (opt.planning_scenarios, 1))
        )
        basis_batches.append(np.full(opt.planning_scenarios, np.median(basis[mask])))
        masks.append((group, mask))
    if not batches:
        return chosen, decisions
    combined = Scenarios(
        batches[0].ages,
        *(
            np.concatenate([getattr(p, name) for p in batches], axis=0)
            for name in ("income", "returns", "prices", "spending", "policy_multiplier")
        ),
        start_index,
    )
    estimate = simulate(
        planning_config,
        combined,
        np.concatenate(end_batches),
        strategies=candidates,
        initial_balances=np.concatenate(balance_batches),
        initial_basis=np.concatenate(basis_batches),
        record=False,
    )
    for index, (group, mask) in enumerate(masks):
        section = slice(
            index * opt.planning_scenarios, (index + 1) * opt.planning_scenarios
        )
        terminal = estimate.terminal_real[:, section]
        failures = estimate.cumulative_shortfall_real[:, section]
        score = terminal.mean(axis=1) - opt.risk_penalty * terminal.std(axis=1)
        eligible = np.flatnonzero(np.isclose(score, score.max(), rtol=1e-9, atol=0.01))
        best = min(eligible, key=lambda i: abs(candidates[i].roth_share - 0.5))
        chosen[mask] = candidates[best].roth_share
        for i, candidate in enumerate(candidates):
            decisions.append(
                dict(
                    age=int(paths.ages[t]),
                    group=int(group),
                    households=int(mask.sum()),
                    income_real=float(np.median(income[mask] / price[mask])),
                    wealth_real=float(np.median(wealth[mask])),
                    candidate_roth_share=candidate.roth_share,
                    chosen_roth_share=candidates[best].roth_share,
                    selected=i == best,
                    expected_terminal_real=float(terminal[i].mean()),
                    terminal_std_real=float(terminal[i].std()),
                    spending_failure_probability=float((failures[i] > 0).mean()),
                    score=float(score[i]),
                )
            )
    return chosen, decisions
