#!/usr/bin/env python3
"""Watch the simulation run, and change the world without leaving the window.

Three strategies are stepped in lockstep on the same seeded workload, so what
you see is one world handled three different ways. The map follows whichever
strategy you pick; the latency panel always shows all three.

    python scripts/live_dashboard.py
    python scripts/live_dashboard.py --volatility 4 --regions 8
    python scripts/live_dashboard.py --windows 90 --save results/figures/live.gif

Controls along the bottom
-------------------------
Sliders set volatility, seed, chunk count, episode length and playback speed.
Nothing takes effect until you press **Apply and restart**, so dragging a slider
never disturbs a run in progress. The region buttons add and remove data centres
one at a time and restart immediately, since the whole cluster changes shape.

Panels
------
map       Bubble size is the share of requests from that region. Squares are the
          chunks living there. An arc is a migration, drawn as it happens and
          fading over the next few turns.
donut     The same request shares as a part-to-whole, this turn only.
bar       How many chunks each region currently holds.
line      Mean request latency so far, for all three strategies.
bar       Cumulative data moved, which is what chasing the traffic costs.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.animation import FuncAnimation, PillowWriter
from matplotlib.gridspec import GridSpec
from matplotlib.widgets import Button, Slider

from shardmind import topologies, viz
from shardmind.actions import ActionSpace
from shardmind.config import ShardMindConfig
from shardmind.cost import evaluate
from shardmind.policies import FollowTrafficPolicy, StaticHashPolicy
from shardmind.simulator import ClusterSimulator

TITLE = "Reinforcement Learning for Dynamic Data Fragmentation and Allocation"

FADE_WINDOWS = 8
POLICY_ORDER = ("static", "follow", "best")


def build_config(volatility: float, windows: int, regions: int,
                 chunks: int, seed: int) -> ShardMindConfig:
    """A configuration from the five dials the dashboard exposes."""
    base = ShardMindConfig()
    topology = topologies.topology_for(regions)
    return base.evolve(
        topology=topology,
        workload=replace(base.workload, volatility=volatility),
        catalog=replace(
            base.catalog,
            initial_fragments=min(chunks, base.catalog.max_fragments),
            max_replicas=min(base.catalog.max_replicas, regions),
            min_replicas=min(base.catalog.min_replicas, regions),
        ),
        episode=replace(base.episode, windows_per_episode=windows),
        seed=seed,
    )


class BestPerWindow:
    """Re-home every chunk optimally each turn, with migration made free.

    A moving target rather than an upper bound: it ignores migration cost,
    transaction co-location and fragmentation, so a policy that keeps its extra
    copies can beat it on some turns.
    """

    def __init__(self, action_space: ActionSpace) -> None:
        self.action_space = action_space

    def act(self, sim: ClusterSimulator) -> int:
        return self.action_space.noop_index

    def reset(self) -> None:
        return None

    @staticmethod
    def evaluate(sim: ClusterSimulator, cfg: ShardMindConfig) -> tuple[float, np.ndarray]:
        window = sim.last.window
        catalog = sim.catalog.copy()
        demand = catalog.aggregate_cells(window.reads + window.writes)
        target = (demand @ sim.topology.rtt).argmin(axis=1)
        for fragment in range(catalog.n_fragments):
            catalog.set_primary(fragment, int(target[fragment]))
        cost = evaluate(catalog, window, sim.generator, sim.topology, cfg.cost)
        return cost.mean_latency_ms, target


class Dashboard:
    """The figure, its widgets, and the three simulations behind them."""

    def __init__(self, cfg: ShardMindConfig, shown: str, interactive: bool = True) -> None:
        self.cfg = cfg
        self.shown = shown
        self.interactive = interactive
        self.playing = False
        self.timer = None
        self.dynamic = []

        self._build_figure()
        self.load(cfg)

    # --------------------------------------------------------------- the run

    def load(self, cfg: ShardMindConfig) -> None:
        """Point the dashboard at a new configuration and start the episode over."""
        self.cfg = cfg
        self.regions = list(cfg.topology.region_names)
        self.n_windows = cfg.episode.windows_per_episode
        self.latlon = [viz.latlon_for(r) for r in self.regions]
        self.xy = [viz.project(lat, lon) for lat, lon in self.latlon]

        space = ActionSpace(cfg.catalog.max_fragments, cfg.n_regions)
        self.space = space
        self.sims = {k: ClusterSimulator(cfg) for k in POLICY_ORDER}
        self.policies = {
            "static": StaticHashPolicy(space),
            "follow": FollowTrafficPolicy(space),
            "best": BestPerWindow(space),
        }
        for sim in self.sims.values():
            sim.reset(seed=cfg.seed)

        self.latency = {k: [] for k in POLICY_ORDER}
        self.cum_gb = {k: 0.0 for k in POLICY_ORDER}
        self.moves = {k: 0 for k in POLICY_ORDER}
        self.prev_homes = {k: list(s.catalog.primary) for k, s in self.sims.items()}
        self.best_homes = list(self.sims["best"].catalog.primary)
        self.flashes = []
        self.t = 0

        self.ax_lat.set_xlim(0, self.n_windows)
        self._rebuild_region_nodes()
        self._reset_map()
        self.draw()

    def step(self) -> None:
        if self.t >= self.n_windows:
            return

        best_latency, best_target = BestPerWindow.evaluate(self.sims["best"], self.cfg)
        for key, sim in self.sims.items():
            sim.step(self.policies[key].act(sim))
            self.cum_gb[key] += sim.last.bytes_moved

        for key, sim in self.sims.items():
            if key == "best":
                self.latency[key].append(best_latency)
                homes = [int(t) for t in best_target]
            else:
                self.latency[key].append(sim.last.cost.mean_latency_ms)
                homes = [int(p) for p in sim.catalog.primary]

            for chunk, (old, new) in enumerate(zip(self.prev_homes[key], homes)):
                if old == new:
                    continue
                self.moves[key] += 1
                if key == self.shown:
                    self.flashes.append({"src": old, "dst": new, "t": self.t})
            self.prev_homes[key] = homes

        self.best_homes = [int(t) for t in best_target]
        self.flashes = [f for f in self.flashes if self.t - f["t"] < FADE_WINDOWS]
        self.t += 1

    # ---------------------------------------------------------------- figure

    def _build_figure(self) -> None:
        viz.use_house_style()
        self.fig = plt.figure(figsize=(16, 9.6))
        try:
            self.fig.canvas.manager.set_window_title(f"{TITLE} - live")
        except AttributeError:
            pass

        top, bottom = (0.862, 0.235) if self.interactive else (0.848, 0.07)
        gs = GridSpec(3, 4, figure=self.fig,
                      height_ratios=[0.95, 0.72, 1.0], width_ratios=[1, 1, 1, 0.92],
                      hspace=0.46, wspace=0.30,
                      left=0.035, right=0.975, top=top, bottom=bottom)
        self.ax_map = self.fig.add_subplot(gs[0:2, 0:3])
        self.ax_pie = self.fig.add_subplot(gs[0, 3])
        self.ax_hold = self.fig.add_subplot(gs[1, 3])
        self.ax_lat = self.fig.add_subplot(gs[2, 0:3])
        self.ax_gb = self.fig.add_subplot(gs[2, 3])

        self.fig.text(0.035, 0.962, TITLE, fontsize=13, fontweight="bold", color=viz.INK)
        self.subtitle = self.fig.text(0.035, 0.933, "", fontsize=9, color=viz.MUTED)
        self.banner = self.fig.text(0.975, 0.903, "", fontsize=9.5, color=viz.INK_2,
                                    ha="right", family="monospace")

        self.ax_lat.set_title("Mean request latency, turn by turn")
        self.ax_lat.set_xlabel("turn")
        self.ax_lat.set_ylabel("ms")
        self.ax_lat.grid(axis="y")
        self.ax_lat.set_axisbelow(True)
        self.lat_lines = {
            k: self.ax_lat.plot([], [], color=viz.POLICY_COLOR[k], label=viz.POLICY_LABEL[k])[0]
            for k in ("static", "best", "follow")
        }
        self.lat_dots = {
            k: self.ax_lat.plot([], [], "o", ms=5, color=viz.POLICY_COLOR[k],
                                mec=viz.SURFACE, mew=1.2)[0]
            for k in POLICY_ORDER
        }
        self.ax_lat.legend(loc="upper right", ncols=3)

        if self.interactive:
            self._build_controls()

    def _rebuild_region_nodes(self) -> None:
        """Region count can change, so anything sized by it is rebuilt here."""
        self.ax_hold.set_yticks(range(len(self.regions)))

    # -------------------------------------------------------------- controls

    def _build_controls(self) -> None:
        fig = self.fig
        fig.text(0.035, 0.186, "W O R L D", fontsize=8.5, color=viz.MUTED,
                 family="monospace")

        def slider(x, width, label, lo, hi, init, step, fmt="%g"):
            ax = fig.add_axes((x, 0.148, width, 0.026))
            ax.set_facecolor(viz.PANEL)
            s = Slider(ax, label, lo, hi, valinit=init, valstep=step,
                       color=viz.SERIES[0], initcolor="none", valfmt=fmt)
            s.label.set_fontsize(8.5)
            s.label.set_color(viz.INK_2)
            s.valtext.set_fontsize(8.5)
            s.valtext.set_family("monospace")
            s.valtext.set_color(viz.INK)
            return s

        cfg = self.cfg
        self.s_vol = slider(0.095, 0.115, "volatility ", 0.0, 8.0,
                            cfg.workload.volatility, 0.5)
        self.s_seed = slider(0.285, 0.085, "seed ", 0, 20, cfg.seed, 1)
        self.s_chunks = slider(0.445, 0.085, "chunks ", 2, 16,
                               cfg.catalog.initial_fragments, 1)
        self.s_turns = slider(0.605, 0.085, "turns ", 50, 400,
                              cfg.episode.windows_per_episode, 25)
        self.s_speed = slider(0.775, 0.085, "ms/turn ", 20, 400, 70, 10)
        self.s_speed.on_changed(self._on_speed)

        def button(x, width, label, on_click, primary=False):
            ax = fig.add_axes((x, 0.052, width, 0.046))
            b = Button(ax, label,
                       color=viz.SERIES[0] if primary else viz.PANEL,
                       hovercolor=viz.GRID if not primary else "#1c5cab")
            b.label.set_fontsize(9)
            b.label.set_color("white" if primary else viz.INK)
            b.label.set_fontweight("600" if primary else "normal")
            for spine in b.ax.spines.values():
                spine.set_edgecolor(viz.SERIES[0] if primary else viz.GRID)
            b.on_clicked(on_click)
            return b

        self.b_play = button(0.035, 0.085, "Play", self._on_play, primary=True)
        self.b_apply = button(0.128, 0.128, "Apply and restart", self._on_apply)
        self.b_minus = button(0.268, 0.048, "− region", self._on_minus)
        self.b_plus = button(0.320, 0.048, "+ region", self._on_plus)

        fig.text(0.392, 0.107, "M A P   F O L L O W S", fontsize=8.5, color=viz.MUTED,
                 family="monospace")
        self.policy_buttons = {}
        for i, key in enumerate(POLICY_ORDER):
            label = viz.POLICY_LABEL[key].replace(" each turn", "")
            self.policy_buttons[key] = button(
                0.392 + i * 0.118, 0.110, label,
                lambda _e, k=key: self._on_policy(k))
        self._paint_policy_buttons()

        self.status = fig.text(0.975, 0.075, "", fontsize=9, color=viz.MUTED,
                               ha="right", family="monospace")
        self.hint = fig.text(0.975, 0.045, "", fontsize=8.5, color=viz.SERIES[1], ha="right")

    def _paint_policy_buttons(self) -> None:
        for key, button in self.policy_buttons.items():
            chosen = key == self.shown
            button.ax.set_facecolor(viz.POLICY_COLOR[key] if chosen else viz.PANEL)
            button.color = viz.POLICY_COLOR[key] if chosen else viz.PANEL
            button.label.set_color("white" if chosen else viz.INK_2)
            button.label.set_fontweight("600" if chosen else "normal")

    def _pending(self) -> bool:
        return (self.s_vol.val != self.cfg.workload.volatility
                or int(self.s_seed.val) != self.cfg.seed
                or int(self.s_chunks.val) != self.cfg.catalog.initial_fragments
                or int(self.s_turns.val) != self.cfg.episode.windows_per_episode)

    # --------------------------------------------------------------- handlers

    def _on_play(self, _event=None) -> None:
        if self.t >= self.n_windows:
            self.load(self.cfg)
        self.playing = not self.playing
        self.b_play.label.set_text("Pause" if self.playing else "Play")
        self.fig.canvas.draw_idle()

    def _on_apply(self, _event=None) -> None:
        self.playing = False
        self.b_play.label.set_text("Play")
        self.load(build_config(
            volatility=float(self.s_vol.val),
            windows=int(self.s_turns.val),
            regions=self.cfg.n_regions,
            chunks=int(self.s_chunks.val),
            seed=int(self.s_seed.val),
        ))
        self.fig.canvas.draw_idle()

    def _change_regions(self, delta: int) -> None:
        target = self.cfg.n_regions + delta
        if not 2 <= target <= topologies.MAX_REGIONS:
            return
        self.playing = False
        self.b_play.label.set_text("Play")
        self.load(build_config(
            volatility=float(self.s_vol.val),
            windows=int(self.s_turns.val),
            regions=target,
            chunks=int(self.s_chunks.val),
            seed=int(self.s_seed.val),
        ))
        self.fig.canvas.draw_idle()

    def _on_minus(self, _event=None) -> None:
        self._change_regions(-1)

    def _on_plus(self, _event=None) -> None:
        self._change_regions(+1)

    def _on_policy(self, key: str) -> None:
        self.shown = key
        self.flashes = []
        self._paint_policy_buttons()
        self.draw()
        self.fig.canvas.draw_idle()

    def _on_speed(self, value) -> None:
        if self.timer is not None:
            self.timer.interval = int(value)

    def tick(self) -> None:
        if not self.playing:
            return
        if self.t >= self.n_windows:
            self.playing = False
            self.b_play.label.set_text("Replay")
            self.fig.canvas.draw_idle()
            return
        self.step()
        self.draw()
        self.fig.canvas.draw_idle()

    # ---------------------------------------------------------------- drawing

    def draw(self) -> None:
        cfg, t = self.cfg, self.t
        sim = self.sims[self.shown]
        window = sim.last.window
        demand = (window.reads + window.writes).sum(axis=0)
        share = demand / demand.sum()
        homes = self.best_homes if self.shown == "best" else [int(p) for p in sim.catalog.primary]

        self._draw_map(share, homes)
        self._draw_donut(share)
        self._draw_holdings(homes)
        self._draw_latency()
        self._draw_migration()
        self._draw_text()

    def _reset_map(self) -> None:
        """Lay the world down once. Only the traffic on top of it is redrawn."""
        self.ax_map.clear()
        viz.draw_basemap(self.ax_map, self.latlon)
        self.dynamic = []

    def _draw_map(self, share, homes) -> None:
        """Replace the moving parts: bubbles, chunks, migrations and labels.

        The coastlines are ~78,000 points, far too many to redraw every frame,
        so the basemap artist is created once in _reset_map and left alone.
        """
        ax = self.ax_map
        for artist in self.dynamic:
            artist.remove()
        self.dynamic = []

        ax.set_title(f"Live map \u2014 {viz.POLICY_LABEL[self.shown]}",
                     color=viz.POLICY_COLOR[self.shown])

        for flash in self.flashes:
            age = (self.t - flash["t"]) / FADE_WINDOWS
            for xs, ys in viz.great_circle(self.latlon[flash["src"]], self.latlon[flash["dst"]]):
                line, = ax.plot(xs, ys, color=viz.POLICY_COLOR[self.shown],
                                lw=2.2 * (1 - age) + 0.4, alpha=0.8 * (1 - age),
                                solid_capstyle="round", zorder=4)
                self.dynamic.append(line)

        peak = max(0.30, float(share.max()))
        labels = []

        for i, (x, y) in enumerate(self.xy):
            self.dynamic.append(ax.scatter(
                [x], [y], s=180 + 2100 * (share[i] / peak), color=viz.region_color(i),
                alpha=0.24, lw=0, zorder=5))
            self.dynamic.append(ax.scatter(
                [x], [y], s=40, color=viz.region_color(i),
                edgecolor=viz.SURFACE, lw=1.3, zorder=7))

            held = [c for c, home in enumerate(homes) if home == i]
            for j, chunk in enumerate(held):
                row, col = divmod(j, 4)
                span = min(len(held), 4)
                cx = x + (col - (span - 1) / 2) * 5.6
                cy = y + 9 + row * 6.5
                self.dynamic.append(ax.scatter(
                    [cx], [cy], s=44, marker="s", color=viz.region_color(i),
                    edgecolor=viz.SURFACE, lw=0.9, zorder=8))
                self.dynamic.append(ax.annotate(
                    str(chunk), (cx, cy), ha="center", va="center",
                    fontsize=5.2, color="white", zorder=9))

            dx, dy = viz.LABEL_OFFSET.get(self.regions[i], (0, -30))
            labels.append((x, y, dx, dy, f"{self.regions[i]}\n{share[i] * 100:.0f}%"))

        for x, y, dx, dy, text in labels:
            self.dynamic.append(ax.annotate(
                text, (x, y), xytext=(dx, dy), textcoords="offset points",
                ha="center", fontsize=7.5, color=viz.INK_2, zorder=10,
                bbox=dict(boxstyle="round,pad=0.18", fc=viz.SURFACE, ec="none", alpha=0.78)))

    def _draw_donut(self, share) -> None:
        ax = self.ax_pie
        ax.clear()
        ax.set_title("Share of requests", fontsize=9.5)
        order = np.argsort(share)[::-1]
        ax.pie(share[order], colors=[viz.region_color(i) for i in order],
               startangle=90, counterclock=False,
               wedgeprops={"width": 0.42, "edgecolor": viz.SURFACE, "linewidth": 1.5})
        top = int(order[0])
        ax.text(0, 0.08, self.regions[top], ha="center", fontsize=8, color=viz.INK_2)
        ax.text(0, -0.24, f"{share[top] * 100:.0f}%", ha="center", fontsize=17,
                fontweight="bold", color=viz.region_color(top))

    def _draw_holdings(self, homes) -> None:
        ax = self.ax_hold
        ax.clear()
        ax.set_title("Chunks held", fontsize=9.5)
        counts = [sum(1 for h in homes if h == i) for i in range(len(self.regions))]
        ypos = np.arange(len(self.regions))[::-1]
        ax.barh(ypos, counts, height=0.62,
                color=[viz.region_color(i) for i in range(len(self.regions))])
        short = [r.rsplit("-", 1)[0] for r in self.regions]
        ax.set_yticks(ypos, short, fontsize=7 if len(self.regions) > 7 else 7.5)
        ax.set_xlim(0, max(3, len(homes)))
        viz.strip_spines(ax, ("bottom",))
        ax.tick_params(left=False)

    def _draw_latency(self) -> None:
        for key, line in self.lat_lines.items():
            y = self.latency[key]
            line.set_data(range(len(y)), y)
            self.lat_dots[key].set_data([len(y) - 1], [y[-1]] if y else [])
        values = [v for ys in self.latency.values() for v in ys]
        if values:
            self.ax_lat.set_ylim(0, max(values) * 1.12)

    def _draw_migration(self) -> None:
        ax = self.ax_gb
        ax.clear()
        ax.set_title("Data moved so far", fontsize=9.5)
        gb = [self.cum_gb[k] / 1e9 for k in POLICY_ORDER]
        bars = ax.bar(range(3), gb, width=0.58,
                      color=[viz.POLICY_COLOR[k] for k in POLICY_ORDER])
        ax.set_xticks(range(3), ["nothing", "chase", "free"], fontsize=8)
        ax.set_ylim(0, max(60, max(gb) * 1.3))
        ax.set_ylabel("GB", fontsize=8)
        viz.strip_spines(ax, ("left",))
        ax.tick_params(bottom=False)
        for rect, value in zip(bars, gb):
            ax.annotate(f"{value:.0f}", (rect.get_x() + rect.get_width() / 2, value),
                        xytext=(0, 3), textcoords="offset points",
                        ha="center", fontsize=8, color=viz.INK_2)

    def _draw_text(self) -> None:
        cfg = self.cfg
        modelled = " · modelled latencies" if topologies.is_modelled(cfg.n_regions) else ""
        self.subtitle.set_text(
            f"{cfg.n_regions} regions · {cfg.catalog.initial_fragments} chunks · "
            f"{self.n_windows} turns · 1 day = {cfg.workload.diurnal_period_windows} turns · "
            f"volatility {cfg.workload.volatility:g} · seed {cfg.seed}{modelled}")

        day = self.t // cfg.workload.diurnal_period_windows + 1
        parts = [f"turn {self.t:>3d}/{self.n_windows}   day {day}"]
        for key in POLICY_ORDER:
            if self.latency[key]:
                parts.append(f"{viz.POLICY_LABEL[key]}: {np.mean(self.latency[key]):5.0f} ms avg")
        self.banner.set_text("     ".join(parts))

        if not self.interactive:
            return
        self.status.set_text(
            f"{self.space.n} actions · "
            f"{self.moves['follow']} chunk moves · "
            f"regions {cfg.n_regions}/{topologies.MAX_REGIONS}")
        self.hint.set_text("settings changed — press Apply and restart" if self._pending() else "")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--policy", choices=list(POLICY_ORDER), default="follow",
                        help="which strategy the map follows at startup")
    parser.add_argument("--config", type=Path, default=None,
                        help="a saved ShardMindConfig JSON to start from (see configs/)")
    parser.add_argument("--volatility", type=float, default=1.0)
    parser.add_argument("--regions", type=int, default=6,
                        help=f"2 to {topologies.MAX_REGIONS}; beyond 6 the latencies are modelled")
    parser.add_argument("--chunks", type=int, default=6)
    parser.add_argument("--windows", type=int, default=200)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--interval", type=int, default=70, help="milliseconds per turn")
    parser.add_argument("--save", type=str, default=None,
                        help="write a GIF and exit, with no window and no controls")
    args = parser.parse_args()

    if args.config:
        cfg = ShardMindConfig.load(args.config).evolve(
            workload=replace(ShardMindConfig.load(args.config).workload,
                             volatility=args.volatility),
            episode=replace(ShardMindConfig.load(args.config).episode,
                            windows_per_episode=args.windows),
            seed=args.seed,
        )
    else:
        cfg = build_config(args.volatility, args.windows, args.regions, args.chunks, args.seed)

    if args.save:
        board = Dashboard(cfg, args.policy, interactive=False)

        def frame(_):
            board.step()
            board.draw()

        anim = FuncAnimation(board.fig, frame, frames=args.windows,
                             interval=args.interval, repeat=False, blit=False)
        anim.save(args.save, writer=PillowWriter(fps=max(4, int(1000 / args.interval))), dpi=80)
        print(f"wrote {args.save}")
        return

    board = Dashboard(cfg, args.policy, interactive=True)
    board.timer = board.fig.canvas.new_timer(interval=args.interval)
    board.timer.add_callback(board.tick)
    board.timer.start()
    board.playing = True
    board.b_play.label.set_text("Pause")
    plt.show()


if __name__ == "__main__":
    main()
