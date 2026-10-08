# Bundled data

## world-50m.json

Country outlines at 1:50m from [Natural Earth](https://www.naturalearthdata.com),
public domain, by way of the [world-atlas](https://github.com/topojson/world-atlas)
package. Converted from TopoJSON to flat `[lon, lat, lon, lat, ...]` rings and
rounded to one decimal place, which is about 11 km and plenty at world scale.

`wrapRings` holds the four outlines that cross the antimeridian, Russia, Fiji
and two Antarctic rings. Their longitudes are stored **unwrapped**, so they run
past 180 or below -180 rather than jumping. Each is drawn three times, shifted
by -360, 0 and +360, and the axes clip the copies that fall outside the view.
Drawn once without that, they smear a band right across the map.

Regenerate by running `world-atlas` through `topojson-client`; the conversion is
a dozen lines and lives in this project's history.
