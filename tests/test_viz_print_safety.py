"""The figures have to survive a monochrome print.

An IEEE submission is reviewed on screen and read on paper, and reviewers
photocopy. A palette that separates only by hue collapses the moment color is
discarded, and that failure is invisible to whoever authored the figure on a
color monitor. These tests are the check that nobody has to remember to run.

The rule they encode comes from `fragalloc.viz`: three series is the ceiling on
a light surface, every series carries a dash pattern as well as a color, and
anything beyond three is a labeled reference rule rather than a fourth color.
"""

from __future__ import annotations

import itertools

import matplotlib as mpl
import pytest

from fragalloc import viz


# --------------------------------------------------------------------------
# Grayscale separation
# --------------------------------------------------------------------------

@pytest.mark.parametrize("a,b", list(itertools.combinations(viz.SERIES_POLICIES, 2)))
def test_series_policies_separate_in_grayscale(a: str, b: str) -> None:
    ratio = viz.grayscale_ratio(viz.POLICY[a]["color"], viz.POLICY[b]["color"])
    assert ratio >= viz.MIN_GRAYSCALE_RATIO, (
        f"{a} and {b} are {ratio:.2f}:1 apart once color is discarded, below the "
        f"{viz.MIN_GRAYSCALE_RATIO}:1 floor. They will read as the same gray on a "
        f"printed page. Either re-step one of them for lightness or move one to a "
        f"reference rule."
    )


def test_series_budget_is_three() -> None:
    """A fourth series cannot be separated by lightness on a light surface, so
    the budget is a hard constraint rather than a guideline. Raising it means
    re-stepping the whole policy palette and re-running this module."""
    assert len(viz.SERIES_POLICIES) == 3


def test_every_policy_is_either_a_series_or_a_reference() -> None:
    assert set(viz.SERIES_POLICIES) | set(viz.REFERENCE_POLICIES) == set(viz.POLICY)
    assert not set(viz.SERIES_POLICIES) & set(viz.REFERENCE_POLICIES)


def test_agent_is_the_darkest_series() -> None:
    """The learned policy is the subject of every policy figure, so it carries
    the most visual weight. Darkest plus solid plus heaviest line, with the
    baselines receding. This is emphasis form, not categorical color."""
    luminances = {k: viz.relative_luminance(viz.POLICY[k]["color"])
                  for k in viz.SERIES_POLICIES}
    assert min(luminances, key=luminances.get) == "agent"
    assert viz.POLICY["agent"]["lw"] == max(
        viz.POLICY[k]["lw"] for k in viz.SERIES_POLICIES
    )


# --------------------------------------------------------------------------
# The redundant channel
# --------------------------------------------------------------------------

def test_every_policy_has_a_distinct_dash() -> None:
    """Color alone is not allowed to carry the distinction. The dash is what
    works under color vision deficiency and on a photocopy."""
    dashes = [viz.POLICY[k]["dash"] for k in viz.POLICY]
    assert len(set(map(str, dashes))) == len(dashes)


def test_only_the_agent_is_solid() -> None:
    """One solid line, so the eye lands on the subject without reading a
    legend."""
    solid = [k for k in viz.SERIES_POLICIES if viz.POLICY[k]["dash"] == (0, ())]
    assert solid == ["agent"]


def test_policy_kwargs_carries_the_dash() -> None:
    """The dash is easy to drop by reaching for POLICY_COLOR directly. This
    pins the helper that keeps them together."""
    kwargs = viz.policy_kwargs("static")
    assert kwargs["linestyle"] == viz.POLICY["static"]["dash"]
    assert kwargs["color"] == viz.POLICY["static"]["color"]
    assert kwargs["label"] == viz.POLICY["static"]["label"]


def test_policy_kwargs_allows_overrides() -> None:
    assert viz.policy_kwargs("agent", label="_nolegend_")["label"] == "_nolegend_"
    assert viz.policy_kwargs("agent", alpha=0.4)["alpha"] == 0.4


# --------------------------------------------------------------------------
# Back-compatibility with the existing dashboards
# --------------------------------------------------------------------------

def test_legacy_views_cover_every_policy() -> None:
    assert set(viz.POLICY_COLOR) == set(viz.POLICY)
    assert set(viz.POLICY_LABEL) == set(viz.POLICY)
    for key, spec in viz.POLICY.items():
        assert viz.POLICY_COLOR[key] == spec["color"]
        assert viz.POLICY_LABEL[key] == spec["label"]


def test_the_three_dashboard_policies_still_resolve() -> None:
    """`scripts/analysis_dashboard.py` indexes these by name."""
    for key in ("static", "follow", "best"):
        assert key in viz.POLICY_COLOR
        assert key in viz.POLICY_LABEL


# --------------------------------------------------------------------------
# Page geometry
# --------------------------------------------------------------------------

def test_figure_widths_match_the_ieee_two_column_page() -> None:
    """A figure authored at the wrong width is rescaled by the typesetter, which
    changes the effective font size. This is the usual reason axis labels come
    out unreadable in a proof."""
    assert viz.FIG_1COL[0] == pytest.approx(3.50, abs=0.01)
    assert viz.FIG_1COL_TALL[0] == pytest.approx(3.50, abs=0.01)
    assert viz.FIG_2COL[0] == pytest.approx(7.16, abs=0.01)
    assert viz.FIG_2COL_TALL[0] == pytest.approx(7.16, abs=0.01)


@pytest.mark.parametrize("size", ["FIG_1COL", "FIG_1COL_TALL",
                                  "FIG_2COL", "FIG_2COL_TALL"])
def test_figures_are_wider_than_tall_enough_to_read(size: str) -> None:
    w, h = getattr(viz, size)
    assert 0.4 <= h / w <= 1.0, f"{size} aspect {h / w:.2f} is outside the usable band"


# --------------------------------------------------------------------------
# Paper style
# --------------------------------------------------------------------------

def test_paper_style_emits_selectable_vector_text() -> None:
    """fonttype 42 embeds TrueType, so a reviewer can select and search the
    text. Type 3, matplotlib's default, cannot be selected and some venues
    reject it outright."""
    viz.use_paper_style()
    assert mpl.rcParams["savefig.format"] == "pdf"
    assert mpl.rcParams["pdf.fonttype"] == 42
    assert mpl.rcParams["ps.fonttype"] == 42


def test_paper_style_is_smaller_than_dashboard_style() -> None:
    viz.use_house_style()
    dashboard = mpl.rcParams["font.size"]
    viz.use_paper_style()
    assert mpl.rcParams["font.size"] < dashboard


def test_paper_style_tick_labels_stay_legible() -> None:
    """Below about 6 pt, axis labels stop being readable at 1:1 on paper."""
    viz.use_paper_style()
    assert mpl.rcParams["xtick.labelsize"] >= 6
    assert mpl.rcParams["ytick.labelsize"] >= 6
    assert mpl.rcParams["legend.fontsize"] >= 6


def test_roboto_is_the_first_choice_face() -> None:
    viz.use_paper_style()
    assert mpl.rcParams["font.sans-serif"][0] == "Roboto"


# --------------------------------------------------------------------------
# The region palette is for identity, and must not drift
# --------------------------------------------------------------------------

def test_region_slots_are_not_reordered() -> None:
    """The slot ordering is the colorblindness-safety mechanism, not a
    cosmetic choice: only orderings that clear every adjacent-pair gate were
    kept. Reordering silently breaks that guarantee."""
    assert viz.SERIES[:3] == ["#2a78d6", "#eb6834", "#1baf7a"]
    assert len(viz.SERIES) == 8


def test_region_color_wraps_rather_than_inventing_a_hue() -> None:
    """A generated ninth hue is indistinguishable from an existing one under
    color vision deficiency. Wrapping is the honest failure."""
    assert viz.region_color(8) == viz.region_color(0)


def test_policy_reference_draws_a_labeled_rule() -> None:
    import matplotlib.pyplot as plt

    viz.use_paper_style()
    fig, ax = plt.subplots()
    viz.policy_reference(ax, 94.0, "best", note="94 ms")
    assert len(ax.lines) == 1
    assert len(ax.texts) == 1
    assert "94 ms" in ax.texts[0].get_text()
    plt.close(fig)
