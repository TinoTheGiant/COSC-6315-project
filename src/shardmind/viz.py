"""Shared plotting vocabulary: palette, geography and small helpers.

Keeping this in one place means the live dashboard, the static figures and the
analysis panels all speak the same visual language, so a color means the same
thing wherever it appears.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import matplotlib as mpl
import numpy as np
from matplotlib.collections import PolyCollection
from matplotlib.colors import LinearSegmentedColormap

#: Categorical slots in a fixed, colorblind-checked order. Never reorder or
#: cycle these: the ordering is what keeps adjacent series distinguishable
#: under color vision deficiency.
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100",
          "#e87ba4", "#008300", "#4a3aa7", "#e34948"]

#: Policy encoding, held constant across every figure in the project.
#:
#: These are deliberately NOT categorical slots. The agent is the subject of
#: every policy figure and the baselines are context, so the form is *emphasis*:
#: one chromatic series against graded grays. That choice is what makes the
#: figures survive a grayscale print, which an IEEE submission must assume.
#:
#: Each policy carries a dash pattern as well as a color. The dash is not
#: decoration and must never be dropped: it is the redundant channel that keeps
#: the series apart for a reader with color vision deficiency, on a photocopy,
#: and under `forced-colors`. Grayscale separation between every pair is
#: asserted in tests/test_viz_print_safety.py.
POLICY = {
    "agent":  {"color": "#184f95", "dash": (0, ()),        "lw": 2.0, "z": 5,
               "label": "Learned policy"},
    "static": {"color": "#898781", "dash": (0, (6, 2.5)),  "lw": 1.6, "z": 3,
               "label": "Do nothing"},
    "greedy": {"color": "#b0aea3", "dash": (0, (1.5, 2)),  "lw": 1.6, "z": 2,
               "label": "Chase the traffic"},
    # The oracle is an upper bound, not a policy. Drawn as a reference rule
    # rather than a fourth series, which keeps every figure inside the
    # three-series grayscale budget. See policy_reference().
    "best":   {"color": "#52514e", "dash": (0, (4, 2, 1, 2)), "lw": 1.1, "z": 4,
               "label": "Best possible each turn"},
}

#: The grayscale budget, made explicit so it cannot drift.
#:
#: Three series is the ceiling for a line or bar figure on a light surface: a
#: fourth cannot be separated from the other three by lightness alone once color
#: is discarded, and no reordering fixes that. Anything beyond three is drawn as
#: a labeled reference rule (policy_reference) or faceted into small multiples.
#: Enforced by tests/test_viz_print_safety.py.
SERIES_POLICIES = ("agent", "static", "greedy")
REFERENCE_POLICIES = ("best",)

#: Minimum contrast ratio between two series once color is discarded. Below
#: this they read as the same gray on a monochrome print.
MIN_GRAYSCALE_RATIO = 1.5

#: Back-compatible views onto POLICY. Existing call sites use these.
POLICY_COLOR = {k: v["color"] for k, v in POLICY.items()}
POLICY_LABEL = {k: v["label"] for k, v in POLICY.items()}


def policy_kwargs(key: str, **overrides) -> dict:
    """Plot kwargs for one policy. Always prefer this over POLICY_COLOR alone,
    because it carries the dash pattern that keeps the figure print-safe."""
    spec = POLICY[key]
    kwargs = {
        "color": spec["color"],
        "linestyle": spec["dash"],
        "linewidth": spec["lw"],
        "zorder": spec["z"],
        "label": spec["label"],
    }
    kwargs.update(overrides)
    return kwargs


#: Figure widths in inches for a two-column IEEE page. Heights are a starting
#: point, not a rule; width is fixed by the template and must not be guessed.
#: Figures authored at the wrong width get scaled by the typesetter, which
#: changes the effective font size and is the usual reason axis labels come out
#: unreadable in a proof.
FIG_1COL = (3.50, 2.35)
FIG_1COL_TALL = (3.50, 3.10)
FIG_2COL = (7.16, 3.00)
FIG_2COL_TALL = (7.16, 4.20)


def relative_luminance(hex_color: str) -> float:
    """WCAG relative luminance. The grayscale value a printer sees."""
    h = hex_color.lstrip("#")
    channels = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
              for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def grayscale_ratio(a: str, b: str) -> float:
    """Contrast ratio between two colors once color is discarded. Two series
    below about 1.5 are indistinguishable on a monochrome print."""
    la, lb = relative_luminance(a), relative_luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)

INK = "#101318"
INK_2 = "#4d545f"
MUTED = "#858c97"
GRID = "#e4e6ea"
SURFACE = "#fbfbfc"
PANEL = "#f2f4f7"

BLUE_RAMP = ["#fbfbfc", "#cde2fb", "#9ec5f4", "#5598e7", "#2a78d6", "#184f95", "#0d366b"]
BLUES = LinearSegmentedColormap.from_list("shardmind_blues", BLUE_RAMP)

SEA = "#d9e3ef"
LAND = "#f9fbfd"
COAST = "#a9b8ca"

BASEMAP_PATH = Path(__file__).resolve().parent / "data" / "world-50m.json"
MAX_LAT = 83.0     # Web Mercator runs to infinity at the poles

#: Approximate latitude of each default region, for the map panel only. These
#: never enter the cost model, which knows distance solely through the RTT
#: matrix; they exist so the map looks like the world rather than a row of dots.
#: Label nudges in points, so that regions sitting close together on the map
#: (the two European ones are 15 degrees apart) do not collide.
LABEL_OFFSET = {
    "us-east-1": (0, -30),
    "us-west-2": (0, -30),
    "eu-west-1": (-34, -26),
    "eu-central-1": (30, -34),
    "ap-southeast-1": (0, -30),
    "ap-northeast-1": (0, -30),
    "sa-east-1": (0, -30),
    "af-south-1": (0, -30),
    "ap-south-1": (32, -30),
    "me-south-1": (-32, -22),
}

REGION_LATLON = {
    "us-east-1": (37.5, -77.5),
    "us-west-2": (45.8, -122.7),
    "eu-west-1": (53.3, -6.3),
    "eu-central-1": (50.1, 8.7),
    "ap-southeast-1": (1.3, 103.8),
    "ap-northeast-1": (35.7, 139.7),
    "sa-east-1": (-23.5, -46.6),
    "af-south-1": (-33.9, 18.4),
}


def use_house_style() -> None:
    """Apply the project's matplotlib defaults. Call once, before plotting."""
    mpl.rcParams.update({
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
        "font.family": "sans-serif",
        "font.sans-serif": ["Roboto", "DejaVu Sans", "Segoe UI", "Helvetica", "Arial"],
        "font.size": 9,
        "text.color": INK,
        "axes.labelcolor": INK_2,
        "axes.labelsize": 9,
        "axes.titlesize": 10,
        "axes.titleweight": "bold",
        "axes.titlelocation": "left",
        "axes.titlepad": 8,
        "axes.edgecolor": GRID,
        "axes.linewidth": 0.8,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "grid.color": GRID,
        "grid.linewidth": 0.6,
        "legend.frameon": False,
        "legend.fontsize": 8.5,
        "lines.linewidth": 1.8,
        "lines.solid_capstyle": "round",
    })


def use_paper_style() -> None:
    """Apply the house style, then the overrides a printed two-column paper
    needs. Call instead of use_house_style() for anything going into the PDF.

    Three differences from the dashboard style, each for a reason:

    * **Smaller type.** A 3.5 inch figure placed at 1:1 in a two-column layout
      shows its labels at their authored size. 9 pt body in a figure sits beside
      10 pt body text and reads correctly; the dashboard's sizes would shout.
    * **Vector output, no raster fallback.** PDF keeps the type selectable and
      the lines crisp at any zoom the reviewer applies.
    * **Thinner rules.** Hairlines that look faint on a backlit screen print
      correctly; screen-weight rules print heavy and crowd the data.
    """
    use_house_style()
    mpl.rcParams.update({
        "figure.figsize": FIG_1COL,
        "figure.dpi": 150,
        "savefig.dpi": 600,
        "savefig.format": "pdf",
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.02,
        "pdf.fonttype": 42,          # TrueType, so reviewers can select text
        "ps.fonttype": 42,
        "font.size": 8,
        "axes.labelsize": 8,
        "axes.titlesize": 8.5,
        "axes.linewidth": 0.6,
        "xtick.labelsize": 7,
        "ytick.labelsize": 7,
        "legend.fontsize": 7,
        "grid.linewidth": 0.4,
        "lines.linewidth": 1.4,
        "patch.linewidth": 0.6,
    })


def policy_reference(ax, level: float, key: str = "best",
                     note: str = "", side: str = "right") -> None:
    """Draw a policy as a horizontal reference rule with a direct label, rather
    than as a series.

    Use this for bounds: the per-turn oracle, a service-level target, the
    published figure from a baseline paper. It keeps a figure inside the
    three-series grayscale budget whilst still showing the fourth quantity, and
    a direct label removes one legend lookup for the reader.
    """
    spec = POLICY[key] if key in POLICY else {"color": MUTED, "dash": (0, (4, 2)),
                                              "lw": 1.1, "label": key}
    ax.axhline(level, color=spec["color"], linestyle=spec["dash"],
               linewidth=spec["lw"], zorder=2)
    text = spec["label"] if not note else f"{spec['label']} — {note}"
    x, ha = (0.99, "right") if side == "right" else (0.01, "left")
    ax.annotate(text, xy=(x, level), xycoords=("axes fraction", "data"),
                xytext=(0, 3), textcoords="offset points",
                ha=ha, va="bottom", fontsize=7, color=spec["color"])


def region_color(index: int) -> str:
    """Color for a region. Eight distinct slots; past that, colors repeat.

    Eight is the ceiling of the categorical palette, not an arbitrary cap: a
    ninth generated hue is indistinguishable from an existing one under color
    vision deficiency. With more than eight regions, read the map by its labels
    rather than by color, or facet the figures.
    """
    return SERIES[index % len(SERIES)]


def latlon_for(name: str) -> tuple[float, float]:
    """Map position for a region, falling back to the equator if unknown.

    A region absent from REGION_LATLON still simulates correctly, since the cost
    model knows distance only through the RTT matrix. It just lands on the
    equator on the map until a latitude and longitude are added here.
    """
    return REGION_LATLON.get(name, (0.0, 0.0))


def mercator_y(lat: float | np.ndarray) -> float | np.ndarray:
    """Web Mercator northing, in the same degree-like units as longitude.

    Using ``asinh(tan(lat))`` in degrees keeps x and y on one scale, so an axes
    with ``aspect="equal"`` is a true Mercator plot and shapes come out right.
    This is the projection every slippy map uses, so the figures agree with the
    interactive map in ``results/atlas.html``.
    """
    clipped = np.clip(lat, -MAX_LAT, MAX_LAT)
    return np.degrees(np.arcsinh(np.tan(np.radians(clipped))))


def project(lat: float, lon: float) -> tuple[float, float]:
    """A latitude and longitude as plot coordinates."""
    return float(lon), float(mercator_y(lat))


@lru_cache(maxsize=1)
def load_basemap() -> dict | None:
    """Country outlines, or None when the bundled data file is missing."""
    if not BASEMAP_PATH.exists():
        return None
    return json.loads(BASEMAP_PATH.read_text(encoding="utf-8"))


def draw_basemap(ax, latlons: list[tuple[float, float]] | None = None) -> None:
    """Draw the world under everything else, and frame the regions in play.

    The outlines go in as a single PolyCollection so the artist can be created
    once and left alone; only the traffic and migrations are redrawn each frame.
    Falls back to a plain graticule if the data file is unavailable.
    """
    ax.set_facecolor(SEA)
    ax.set_xticks([])
    ax.set_yticks([])
    for side in ("top", "right", "left", "bottom"):
        ax.spines[side].set_visible(False)

    world = load_basemap()
    if world is None:
        for lon in range(-180, 181, 30):
            ax.axvline(lon, color=GRID, lw=0.5, zorder=0)
        for lat in range(-60, 91, 30):
            ax.axhline(mercator_y(lat), color=GRID, lw=0.5, zorder=0)
    else:
        polys = []
        for ring in world["rings"]:
            flat = np.asarray(ring, dtype=float).reshape(-1, 2)
            polys.append(np.column_stack([flat[:, 0], mercator_y(flat[:, 1])]))
        # Russia, Fiji and Antarctica wrap the antimeridian; their coordinates
        # are stored unwrapped, so each is drawn three times and the axes clip
        # whichever copies fall outside the view.
        for ring in world["wrapRings"]:
            flat = np.asarray(ring, dtype=float).reshape(-1, 2)
            y = mercator_y(flat[:, 1])
            for shift in (-360.0, 0.0, 360.0):
                polys.append(np.column_stack([flat[:, 0] + shift, y]))

        ax.add_collection(PolyCollection(
            polys, facecolors=LAND, edgecolors=COAST, linewidths=0.4, zorder=0))

    ax.axhline(0, color=MUTED, lw=0.6, ls=(0, (4, 4)), alpha=0.5, zorder=1)

    ax.set_xlim(-168, 178)
    if latlons:
        ys = [mercator_y(lat) for lat, _ in latlons]
        pad = max(22.0, (max(ys) - min(ys)) * 0.30)
        ax.set_ylim(max(mercator_y(-72), min(ys) - pad),
                    min(mercator_y(80), max(ys) + pad))
    else:
        ax.set_ylim(mercator_y(-58), mercator_y(74))
    # datalim, not box: widen the view to fill the panel rather than
    # shrinking the map into a letterboxed strip when more latitude is in play.
    ax.set_aspect("equal", adjustable="datalim")


def great_circle(a: tuple[float, float], b: tuple[float, float], n: int = 64):
    """Projected segments of the great circle between two (lat, lon) points.

    Returns a list of ``(xs, ys)`` arrays rather than one path, because a route
    crossing the antimeridian has to be broken or it draws straight back across
    the whole map.
    """
    lat1, lon1 = np.radians(a)
    lat2, lon2 = np.radians(b)
    d = 2 * np.arcsin(np.sqrt(
        np.sin((lat2 - lat1) / 2) ** 2
        + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2))
    if not d > 1e-9:
        return []

    f = np.linspace(0.0, 1.0, n)
    A = np.sin((1 - f) * d) / np.sin(d)
    B = np.sin(f * d) / np.sin(d)
    x = A * np.cos(lat1) * np.cos(lon1) + B * np.cos(lat2) * np.cos(lon2)
    y = A * np.cos(lat1) * np.sin(lon1) + B * np.cos(lat2) * np.sin(lon2)
    z = A * np.sin(lat1) + B * np.sin(lat2)

    lons = np.degrees(np.arctan2(y, x))
    lats = np.degrees(np.arctan2(z, np.hypot(x, y)))
    ys = mercator_y(lats)

    breaks = np.flatnonzero(np.abs(np.diff(lons)) > 180.0) + 1
    return [(seg_lon, seg_y) for seg_lon, seg_y
            in zip(np.split(lons, breaks), np.split(ys, breaks))
            if len(seg_lon) > 1]


def arc(p0: tuple[float, float], p1: tuple[float, float], n: int = 24, lift: float = 0.28):
    """A quadratic bezier between two projected points, bowed toward the pole.

    Straight lines between regions read as chords through the map; a slight bow
    makes a migration legible as travel.
    """
    (x0, y0), (x1, y1) = p0, p1
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2 + abs(x1 - x0) * lift
    t = np.linspace(0, 1, n)
    x = (1 - t) ** 2 * x0 + 2 * (1 - t) * t * mx + t ** 2 * x1
    y = (1 - t) ** 2 * y0 + 2 * (1 - t) * t * my + t ** 2 * y1
    return x, y


def strip_spines(ax, keep: tuple[str, ...] = ("left", "bottom")) -> None:
    for side in ("top", "right", "left", "bottom"):
        ax.spines[side].set_visible(side in keep)
