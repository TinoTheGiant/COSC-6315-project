# Vendored third-party code

## leaflet/

[Leaflet](https://leafletjs.com) 1.9.4, BSD-2-Clause, copyright Vladimir
Agafonkin and CloudMade. The upstream licence is kept beside the files.

It is checked in rather than pulled from a CDN so that
`scripts/make_atlas.py` can inline it into a single self-contained HTML file.
That file then opens straight off disk with no network needed for the map
itself. Only the basemap tiles are fetched at view time, so the map works
offline apart from the tiles, which appear as blank squares.

To update, replace `leaflet.min.js`, `leaflet.css` and `LICENSE` from
`npm pack leaflet@<version>` and change the version recorded here.
