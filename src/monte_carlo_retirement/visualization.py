"""Render precomputed exports; no financial calculations live in the viewer."""

import json
from pathlib import Path


def write_dashboard(data, destination):
    template = Path(__file__).with_name("dashboard.html").read_text()
    # Do not allow user-supplied labels to terminate the embedded JSON script.
    payload = json.dumps(data, allow_nan=False).replace("<", "\\u003c")
    Path(destination).write_text(template.replace("__SIMULATION_DATA__", payload))


def write_static_chart(data, destination):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    with plt.style.context("dark_background"):
        fig, ax = plt.subplots(figsize=(11, 6), layout="constrained")
        colors = ["#62d9c8", "#f6c767", "#a2baff", "#f29bbb"]
        for index, strategy in enumerate(data["strategies"]):
            values = strategy["metrics"]["portfolio"]["real"]
            color = colors[index % len(colors)]
            ax.plot(data["ages"], values["median"], label=strategy["name"], color=color)
            ax.fill_between(
                data["ages"], values["p10"], values["p90"], alpha=0.1, color=color
            )
        ax.axvline(data["retirement_age"], linestyle="--", color="white", alpha=0.5)
        ax.set(
            title="Lifetime account balances · median and 10–90% bands",
            xlabel="Age (balance at year end)",
            ylabel="Starting-year dollars, before future withdrawal taxes",
        )
        ax.legend()
        ax.grid(alpha=0.12)
        fig.savefig(destination, dpi=150, facecolor="#0c1524")
        plt.close(fig)
