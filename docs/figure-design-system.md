# Figure and dashboard design system

One visual vocabulary, two targets: the **paper figures** that go into a printed
two-column IEEE submission, and the **live dashboard** that runs on screen whilst
an episode plays. A color means the same thing in both. The code is
`src/shardmind/viz.py`; the rules are enforced by
`tests/test_viz_print_safety.py`.

## Why this exists

The project already had a house style. It had one defect, and it was the kind
that is invisible to whoever authored the figure.

### Audit of the previous palette

Policies were assigned the first three categorical slots: blue, orange, aqua.
Those three are well separated by *hue*, which is what a categorical palette is
chosen for. They are not separated by *lightness*, which is all that survives a
monochrome print.

| Pair | Grayscale contrast | Verdict |
|---|---|---|
| static vs follow | 1.38:1 | **fails** |
| follow vs best | 1.14:1 | **fails** |
| static vs best | 1.57:1 | marginal |

At 1.14:1 two lines are the same gray. A reviewer reading a printout, or a
photocopy, or a grayscale PDF proof, cannot tell which line is the agent. Nobody
authoring on a color monitor would ever notice.

Four further gaps: there was no slot for the learned policy at all, only for the
three baselines; no figure-size tokens, so figure widths were being guessed
against a fixed two-column template; no vector output settings, so figures were
heading for the PDF as raster; and the stated typeface was DejaVu Sans rather
than the project's Roboto.

### What changed

| Before | After | Reason |
|---|---|---|
| Three categorical hues for policies | **Emphasis form**: one chromatic series against graded grays | The agent is the subject and the baselines are context. Categorical color buries the one series that matters |
| Color only | Color **and** a mandatory dash pattern | The redundant channel. Works under color vision deficiency, on a photocopy, and under `forced-colors` |
| No agent slot | `agent` added, darkest and heaviest | The reader's eye should land on it without reading a legend |
| Figure sizes guessed | `FIG_1COL`, `FIG_2COL` and tall variants | Authoring at the wrong width means the typesetter rescales, which changes effective font size |
| One style function | `use_house_style()` for screen, `use_paper_style()` for print | Screen-weight hairlines print heavy; print-weight type is too small on a dashboard |
| DejaVu Sans | Roboto, DejaVu as fallback | The project's typeface, and a Helvetica-alike is the IEEE figure convention |

## Tokens

### Policy encoding

The project's one load-bearing palette decision. Not categorical.

| Role | Color | Lightness | Dash | Weight | Label |
|---|---|---|---|---|---|
| `agent` | `#184f95` | 0.080 | solid | 2.0 | Learned policy |
| `static` | `#898781` | 0.242 | long dash | 1.6 | Static hash |
| `follow` | `#b0aea3` | 0.421 | dotted | 1.6 | Follow traffic |
| `best` | `#52514e` | 0.084 | dash-dot | 1.1 | Best per window |

Grayscale separation between the three series: 2.26:1, 2.00:1 and 4.52:1, all
clear of the 1.5:1 floor.

`best` is the per-turn oracle. It is an **upper bound, not a policy**, and it is
drawn as a labeled horizontal rule by `viz.policy_reference()` rather than as a
fourth series. That is not a presentational nicety: a fourth series cannot be
separated from the other three by lightness on a light surface, and no
reordering fixes it. Three is the budget, `SERIES_POLICIES` states it, and a
test pins it at three so it cannot drift.

Always reach for `viz.policy_kwargs(key)` rather than `POLICY_COLOR[key]`. The
helper carries the dash, the weight and the z-order together; indexing the color
dict alone is how the redundant channel gets silently dropped.

```python
ax.plot(x, y, **viz.policy_kwargs("agent"))
ax.plot(x, y, **viz.policy_kwargs("static"))
viz.policy_reference(ax, 94.0, "best", note="94 ms")
```

### Region color

`viz.SERIES` holds eight categorical slots and `viz.region_color(i)` indexes
them. **The slot ordering is the colorblindness-safety mechanism, not a cosmetic
choice.** Only orderings clearing every adjacent-pair gate were kept, so
reordering silently voids the guarantee. Past eight regions, `region_color`
wraps rather than generating a ninth hue, because a generated hue is
indistinguishable from an existing one under color vision deficiency.

**Region color is for identity, and identity needs a spatial anchor.** It is
sanctioned on the dashboard map, where position and a direct label carry the
distinction and color is a convenience. It is **not** sanctioned for per-region
quantities in the paper: a six-series stacked bar cannot survive print. For
those, use the sequential blue ramp (`viz.BLUES`) ordered by magnitude with
regions in a fixed order and direct labels, or facet into small multiples.

### Sequential and geographic

| Token | Value | Use |
|---|---|---|
| `BLUES` | 7-step blue ramp, light to dark | Continuous magnitude: traffic heatmaps, per-cell concentration, choropleths |
| `SEA` | `#d9e3ef` | Map water |
| `LAND` | `#f9fbfd` | Map land |
| `COAST` | `#a9b8ca` | Coastline hairline |

The lightest ramp step recedes toward the surface, which is correct for
sequential encoding where the lightest step means "near zero". For an **ordinal**
ramp of discrete ordered marks, start no lighter than the third step or the
first category disappears into the background.

### Ink and chrome

| Role | Value | Use |
|---|---|---|
| `INK` | `#101318` | Titles, primary text |
| `INK_2` | `#4d545f` | Axis labels |
| `MUTED` | `#858c97` | Tick labels, annotations |
| `GRID` | `#e4e6ea` | Gridlines, axis spines |
| `SURFACE` | `#fbfbfc` | Figure and axes background |
| `PANEL` | `#f2f4f7` | Dashboard panel fill |

Top and right spines are off everywhere. Titles are left-aligned and bold, which
reads as a label rather than a caption and leaves the figure's top-right free for
a direct label.

### Type

Roboto, with DejaVu Sans, Segoe UI, Helvetica and Arial as fallbacks. No serif
and no display face in a figure: Bebas Neue is for dashboard headings only, where
a display face has a job, and it is wrong for an axis label at 7 pt.

| | Dashboard | Paper |
|---|---|---|
| Body | 9 | 8 |
| Axis label | 9 | 8 |
| Title | 10 bold | 8.5 bold |
| Tick label | 8 | 7 |
| Legend | 8.5 | 7 |

Six points is the floor. Below it, axis labels stop being readable at 1:1 on
paper, and a test asserts the paper style stays above it.

### Geometry

| Token | Inches | Use |
|---|---|---|
| `FIG_1COL` | 3.50 x 2.35 | Single-column figure, the default |
| `FIG_1COL_TALL` | 3.50 x 3.10 | Single column with a stacked second panel |
| `FIG_2COL` | 7.16 x 3.00 | Full width, up to three panels side by side |
| `FIG_2COL_TALL` | 7.16 x 4.20 | Full width, two rows |

Widths are fixed by the IEEE two-column template and must not be guessed.
Heights are a starting point. Output is PDF at `fonttype 42`, so the type is
selectable and searchable; matplotlib's default Type 3 cannot be selected and
some venues reject it.

## Choosing the form

The data's job picks the chart. In this project the jobs recur, so the mapping
can be fixed once.

| What the reader must do | Form | Color job |
|---|---|---|
| Compare the agent against baselines over an episode | Line, **emphasis** | agent accent, baselines gray |
| Show the latency distribution, not just its center | ECDF or violin, emphasis | same |
| Show where traffic is concentrated across the keyspace | Heatmap, cells by windows | sequential `BLUES` |
| Show which regions serve what share | Small multiples, one per region | sequential, or one accent + gray |
| Show the volatility sweep | Three stacked panels: latency, tracking gap, migration volume | one accent per panel |
| Show placement on the world | Map, region markers | categorical `SERIES`, with labels |
| Report a single headline number | Stat tile, hero figure | none |

Two forms to avoid, for reasons specific to this project:

- **No pie charts.** A pie shows part-to-whole at one instant. The project's
  central empirical claim is that concentration *moves*, and an
  episode-averaged pie would flatten exactly the signal the paper is about,
  implying the workload is not localized when it is.
- **No six-series categorical anything in the paper.** Past three series, fold
  the tail into "other", facet into small multiples, or switch to a table. Never
  solve it by generating more hues.

## Rules

1. **Every series carries a dash as well as a color.** Not negotiable, and the
   reason `policy_kwargs` exists.
2. **Three series maximum on a light surface.** The fourth quantity becomes a
   reference rule, a facet, or a table row.
3. **Direct-label anything below 3:1 against the surface.** `follow` at 2.15:1
   is below the comfortable band by design, and its dash plus a direct label is
   the mitigation.
4. **The agent is always darkest, solid and heaviest.** Emphasis form, applied
   consistently, means a reader never hunts the legend to find the subject.
5. **Never reorder `SERIES`.** The ordering is the safety mechanism.
6. **A measured number and a modeled number never share an encoding.** Once the
   CockroachDB harness lands, simulator output and cluster output appear in the
   same figures. Modeled series take a lighter weight and a dotted dash;
   measured series are solid. Getting this wrong is worse than an ugly figure,
   because it misleads about provenance.
7. **`use_paper_style()` for anything entering the PDF**, `use_house_style()` for
   the dashboard. Call once, before plotting.

## Enforcement

`tests/test_viz_print_safety.py`, 24 tests, under a second. It asserts
pairwise grayscale separation for every series pair, that the series budget is
three, that every policy has a distinct dash and only the agent is solid, that
`policy_kwargs` carries the dash, that figure widths match the template, that
the paper style emits selectable vector text and keeps type above 6 pt, that
Roboto leads the font stack, and that the region slots have not been reordered.

The point is that none of this depends on anyone remembering. A palette change
that breaks print safety fails the suite.

## Dashboard-specific

The dashboard shares the vocabulary and adds what a live surface needs:

- **`PANEL` for panel fill**, `SURFACE` for the figure, so panels read as
  grouped without a border.
- **Bebas Neue for panel headings only.** Condensed, all-caps, a display face
  doing display work. Roboto everywhere else.
- **The map basemap is drawn once** as a single `PolyCollection` and never
  redrawn; only dynamic artists are removed and re-added per frame. 78,000
  coastline points per frame is the difference between 53 ms and unusable.
- **Status color is reserved** and never themed. A status hue must never
  impersonate a series, so it always appears with an icon or a label and never
  relies on hue alone.

Both targets import the same module. That is the whole point: a color means the
same thing wherever it appears, which is what makes a dashboard screenshot and a
paper figure recognizable as the same work.
