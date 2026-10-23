"""Strategy identities do not own or consume economic random streams."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Strategy:
    name: str
    roth_share: float | None

    def __post_init__(self):
        if not self.name or (
            self.roth_share is not None and not 0 <= self.roth_share <= 1
        ):
            raise ValueError("invalid strategy")


def configured_strategies(config):
    strategies = [Strategy(f"Roth {share:.0%}", share) for share in config.roth_shares]
    if config.optimization.enabled:
        strategies.append(Strategy("Adaptive", None))
    if len({s.name for s in strategies}) != len(strategies):
        raise ValueError("strategy names must be unique")
    return tuple(strategies)
