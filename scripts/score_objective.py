"""Score every recorded policy under the training objective.

The objective the agent minimises is

    cost = latency_ms/100  +  w * (gb_moved/2000)  +  0.10 * imbalance

so a policy is only comparable with another policy at the SAME w. This
script exists because scoring a learned run against a baseline evaluated
at a different w is the easiest way to manufacture a win, and it has
already happened once in this project by hand.

Reads results/recorded/*.csv. Writes a markdown table to stdout.
"""
import csv
import pathlib

HERE = pathlib.Path(__file__).resolve().parents[1] / "results" / "recorded"


def rows(name):
    with open(HERE / name, newline="") as fh:
        return list(csv.DictReader(ln for ln in fh if not ln.startswith("#")))


def cost(latency, gb, imbalance, w):
    return latency / 100.0 + w * (gb / 2000.0) + 0.10 * imbalance


def main():
    base = {}
    for r in rows("baselines-heldout.csv"):
        if not r["imbalance"]:
            continue
        base[(float(r["volatility"]), r["policy"])] = (
            float(r["latency_ms"]), float(r["gb_moved"]), float(r["imbalance"]))

    print("| run | vol | w | seed | latency ms | GB | imbalance | agent cost "
          "| follow cost | static cost | vs follow | vs static |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in rows("agent-runs.csv"):
        if not r["agent_imbalance"]:
            continue
        vol, w = float(r["volatility"]), float(r["w_migration"])
        lat, gb, imb = (float(r["agent_latency_ms"]), float(r["agent_gb"]),
                        float(r["agent_imbalance"]))
        a = cost(lat, gb, imb, w)
        f = cost(*base[(vol, "follow")], w)
        s = cost(*base[(vol, "static")], w)
        print(f"| {r['run']} | {vol:g} | {w:.2f} | {r['seed']} | {lat:.2f} | "
              f"{gb:.1f} | {imb:.3f} | {a:.3f} | {f:.3f} | {s:.3f} | "
              f"{a-f:+.3f} | {a-s:+.3f} |")

    print()
    print("Baselines scored against each other, w = 0.30:")
    print("| vol | policy | latency ms | GB | imbalance | cost |")
    print("|---|---|---|---|---|---|")
    for vol in (2.0, 4.0):
        for pol in ("static", "random", "follow", "best"):
            lat, gb, imb = base[(vol, pol)]
            print(f"| {vol:g} | {pol} | {lat:.2f} | {gb:.1f} | {imb:.4f} | "
                  f"{cost(lat, gb, imb, 0.30):.3f} |")


if __name__ == "__main__":
    main()
