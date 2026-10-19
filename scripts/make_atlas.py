#!/usr/bin/env python3
"""Build a standalone Leaflet map of one episode, on real OpenStreetMap tiles.

    python scripts/export_episode.py     # writes results/episode.json
    python scripts/make_atlas.py         # writes results/atlas.html
    start results/atlas.html             # Windows; 'open' on macOS

Why this exists alongside the published web replay: that page runs under a strict
content policy and cannot load map tiles from anywhere, so it draws its own
vector basemap. This file opens straight off your disk with no such limit, so it
gets the real thing: OpenStreetMap raster tiles, proper zoom, pan and scale.

No API key and no account. Tiles come from CARTO's free OpenStreetMap-derived
basemap, which is fine for a single machine looking at one episode. For anything
heavier, point TILE_URL at your own tile source.

Leaflet is inlined from `vendor/leaflet/` rather than loaded from a CDN, so the
output is one self-contained file that works with no network except for the
tiles themselves. Offline, the map still pans, zooms and animates; the tiles
are simply blank.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

TITLE = "Reinforcement Learning for Dynamic Data Fragmentation and Allocation"

TILE_URL = "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png"
TILE_ATTRIBUTION = (
    '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> '
    'contributors &copy; <a href="https://carto.com/attributions">CARTO</a>'
)

SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100",
          "#e87ba4", "#008300", "#4a3aa7", "#e34948"]

VENDOR = Path(__file__).resolve().parent.parent / "vendor" / "leaflet"

TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__ &middot; Atlas</title>
<style>
__LEAFLET_CSS__
</style>
<script>__LEAFLET_JS__</script>
<style>
  :root {
    --ground: #f2f4f7; --panel: #fff; --line: #dfe3e9;
    --ink: #101318; --ink-2: #4d545f; --ink-3: #858c97; --accent: #2a78d6;
    --mono: "IBM Plex Mono", ui-monospace, Consolas, monospace;
    --sans: "IBM Plex Sans", system-ui, "Segoe UI", sans-serif;
  }
  * { box-sizing: border-box; }
  html, body { height: 100%; margin: 0; }
  body {
    display: flex; flex-direction: column;
    background: var(--ground); color: var(--ink);
    font-family: var(--sans); font-size: 14px;
  }
  header {
    padding: 12px 16px; background: var(--panel);
    border-bottom: 1px solid var(--line);
    display: flex; flex-wrap: wrap; align-items: center; gap: 12px;
  }
  h1 { margin: 0; font-size: 14px; font-weight: 600; max-width: 34ch; line-height: 1.25; }
  .meta { font-family: var(--mono); font-size: 11px; color: var(--ink-3); }
  .grow { flex: 1 1 180px; display: flex; align-items: center; gap: 8px; min-width: 160px; }
  input[type=range] { flex: 1; accent-color: var(--accent); min-width: 0; }
  button, select {
    font-family: var(--sans); font-size: 12.5px; color: var(--ink);
    background: var(--panel); border: 1px solid var(--line);
    border-radius: 5px; padding: 6px 12px; cursor: pointer;
  }
  button:hover, select:hover { border-color: var(--ink-3); }
  #map { flex: 1; min-height: 0; }
  .tnow, .stat { font-family: var(--mono); font-size: 12px; color: var(--ink-2); white-space: nowrap; }
  .stat b { color: var(--ink); font-weight: 600; }
  .leaflet-tooltip.pin {
    font-family: var(--sans); font-size: 11px; font-weight: 600;
    background: rgba(255,255,255,.88); border: 1px solid var(--line);
    box-shadow: none; color: var(--ink);
  }
  .leaflet-tooltip.pin::before { display: none; }
</style>
</head>
<body>

<header>
  <h1>__TITLE__</h1>
  <span class="meta">__META__</span>
  <select id="policy" aria-label="Strategy">__OPTIONS__</select>
  <button id="play">Play</button>
  <div class="grow">
    <input type="range" id="scrub" min="0" max="__N__" value="0" step="1" aria-label="Decision window">
    <span class="tnow" id="tnow">turn 0</span>
  </div>
  <span class="stat" id="stat"></span>
</header>

<div id="map"></div>

<script>
const DATA = __DATA__;
const SERIES = __SERIES__;
const M = DATA.meta, N = M.windows;
const PLACES = M.regionMeta;
const KEYS = ["static", "follow", "best"];
const FADE = 8;

const hue = i => SERIES[i % SERIES.length];
const peak = Math.max(...DATA.regionTraffic.map(r => Math.max(...r)));

const map = L.map("map", { worldCopyJump: true, zoomControl: true })
  .setView([26, 8], 2);
L.tileLayer("__TILES__", {
  attribution: '__ATTRIB__', maxZoom: 18, subdomains: "abcd",
}).addTo(map);
L.control.scale({ imperial: false }).addTo(map);

const state = { t: 0, policy: "follow", playing: false, timer: null };

// One circle and one label per data centre. Leaflet keeps them on the map and
// we only resize them as the episode runs, which is much cheaper than redrawing.
const pins = PLACES.map((place, i) => {
  const circle = L.circleMarker([place.lat, place.lon], {
    radius: 8, color: hue(i), weight: 2, fillColor: hue(i), fillOpacity: 0.25,
  }).addTo(map);
  // Dublin and Frankfurt are close enough that same-side labels overlap, so
  // neighbouring pins alternate above and below their circle.
  const below = i % 2 === 0;
  circle.bindTooltip("", {
    className: "pin", permanent: true,
    direction: below ? "bottom" : "top",
    offset: below ? [0, 8] : [0, -8],
  });
  circle.bindPopup("");
  return { circle, place, i };
});

let arcs = [];

/* The path data really crosses, not a straight line on a flat map. */
function greatCircle(a, b, n = 64) {
  const R = Math.PI / 180;
  const la1 = a.lat * R, lo1 = a.lon * R, la2 = b.lat * R, lo2 = b.lon * R;
  const d = 2 * Math.asin(Math.sqrt(
    Math.sin((la2 - la1) / 2) ** 2 +
    Math.cos(la1) * Math.cos(la2) * Math.sin((lo2 - lo1) / 2) ** 2));
  if (!(d > 1e-9)) return [];
  const pts = [];
  for (let k = 0; k <= n; k++) {
    const f = k / n;
    const A = Math.sin((1 - f) * d) / Math.sin(d), B = Math.sin(f * d) / Math.sin(d);
    const x = A * Math.cos(la1) * Math.cos(lo1) + B * Math.cos(la2) * Math.cos(lo2);
    const y = A * Math.cos(la1) * Math.sin(lo1) + B * Math.cos(la2) * Math.sin(lo2);
    const z = A * Math.sin(la1) + B * Math.sin(la2);
    pts.push([Math.atan2(z, Math.hypot(x, y)) / R, Math.atan2(y, x) / R]);
  }
  return pts;
}

function render() {
  const t = state.t;
  const traffic = DATA.regionTraffic[t];
  const p = DATA.policies[state.policy];
  const homes = p.homes[t];
  const accent = SERIES[KEYS.indexOf(state.policy)];

  for (const pin of pins) {
    const share = traffic[pin.i];
    const held = homes.reduce((n, h) => n + (h === pin.i ? 1 : 0), 0);
    pin.circle.setRadius(6 + 30 * Math.sqrt(share / peak));
    pin.circle.setTooltipContent(
      `${pin.place.name} &nbsp;${(share * 100).toFixed(0)}%` +
      (held ? ` &nbsp;· ${held}&#9632;` : ""));
    pin.circle.setPopupContent(
      `<b>${pin.place.name}</b><br>${pin.place.city}<br>` +
      `${(share * 100).toFixed(1)}% of requests<br>` +
      `${held} chunk${held === 1 ? "" : "s"} held<br>` +
      `<span style="color:#858c97">${pin.place.lat.toFixed(1)}, ${pin.place.lon.toFixed(1)}</span>`);
  }

  arcs.forEach(a => map.removeLayer(a));
  arcs = [];
  for (let i = Math.max(1, t - FADE + 1); i <= t; i++) {
    const before = p.homes[i - 1], after = p.homes[i];
    for (let c = 0; c < after.length; c++) {
      if (before[c] === after[c]) continue;
      const age = (t - i) / FADE;
      arcs.push(L.polyline(greatCircle(PLACES[before[c]], PLACES[after[c]]), {
        color: accent, weight: 2.4 * (1 - age) + 0.6, opacity: 0.85 * (1 - age),
      }).addTo(map));
    }
  }

  let moves = 0;
  for (let i = 1; i <= t; i++) {
    for (let c = 0; c < p.homes[i].length; c++) {
      if (p.homes[i][c] !== p.homes[i - 1][c]) moves++;
    }
  }
  const gb = p.gbMoved.slice(0, t + 1).reduce((s, x) => s + x, 0);
  document.getElementById("stat").innerHTML =
    `<b>${p.latency[t].toFixed(0)} ms</b> now &nbsp;·&nbsp; ` +
    `<b>${moves}</b> chunk moves &nbsp;·&nbsp; <b>${gb.toFixed(0)} GB</b> shifted`;

  document.getElementById("scrub").value = String(t);
  document.getElementById("tnow").textContent =
    `turn ${t} / day ${Math.floor(t / M.diurnalPeriodWindows) + 1}`;
}

const playBtn = document.getElementById("play");
function stop() {
  state.playing = false;
  playBtn.textContent = "Play";
  if (state.timer) { clearInterval(state.timer); state.timer = null; }
}
playBtn.addEventListener("click", () => {
  if (state.playing) return stop();
  if (state.t >= N) state.t = 0;
  state.playing = true;
  playBtn.textContent = "Pause";
  state.timer = setInterval(() => {
    state.t += 1;
    if (state.t >= N) { state.t = N; render(); stop(); return; }
    render();
  }, 90);
});
document.getElementById("scrub").addEventListener("input", ev => {
  stop(); state.t = +ev.target.value; render();
});
document.getElementById("policy").addEventListener("change", ev => {
  state.policy = ev.target.value; render();
});

render();
</script>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", type=Path, default=Path("results/episode.json"))
    parser.add_argument("--out", type=Path, default=Path("results/atlas.html"))
    args = parser.parse_args()

    if not args.data.exists():
        raise SystemExit(f"{args.data} not found. Run: python scripts/export_episode.py")

    for part in ("leaflet.min.js", "leaflet.css"):
        if not (VENDOR / part).exists():
            raise SystemExit(f"missing {VENDOR / part}. See vendor/README.md")

    data = json.loads(args.data.read_text(encoding="utf-8"))
    meta = data["meta"]
    if "regionMeta" not in meta:
        raise SystemExit("episode.json predates the map support. Re-run export_episode.py")

    options = "".join(
        f'<option value="{k}"{" selected" if k == "follow" else ""}>'
        f'{data["policies"][k]["label"]}</option>'
        for k in ("static", "follow", "best")
    )
    summary = (f'{len(meta["regions"])} regions · {meta["windows"]} turns · '
               f'volatility {meta["volatility"]:g} · seed {meta["seed"]}')

    html = (TEMPLATE
            .replace("__DATA__", json.dumps(data, separators=(",", ":")))
            .replace("__SERIES__", json.dumps(SERIES))
            .replace("__TILES__", TILE_URL)
            .replace("__ATTRIB__", TILE_ATTRIBUTION)
            .replace("__OPTIONS__", options)
            .replace("__META__", summary)
            .replace("__TITLE__", TITLE)
            .replace("__N__", str(meta["windows"]))
            .replace("__LEAFLET_CSS__", (VENDOR / "leaflet.css").read_text(encoding="utf-8"))
            .replace("__LEAFLET_JS__", (VENDOR / "leaflet.min.js").read_text(encoding="utf-8")))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(html, encoding="utf-8")
    print(f"wrote {args.out} ({args.out.stat().st_size / 1024:.0f} KB)")
    print("open it with:  start " + str(args.out).replace("/", "\\"))


if __name__ == "__main__":
    main()
