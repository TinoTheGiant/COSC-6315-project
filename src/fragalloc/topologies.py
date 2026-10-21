"""Ready-made cluster geographies, so region count can be a dial rather than a rewrite.

The first six regions carry the hand-set latency table from :mod:`fragalloc.topology`,
chosen to match commonly observed inter-region round-trip times. Regions beyond
those six use a distance model instead:

    RTT_ms = 10.4 + 0.01430 * great_circle_km        (about 70 km per millisecond)

fitted by least squares to those fifteen measured pairs. The fit is decent but
not tight: median error 20%, worst 36%, R-squared 0.74. Real internet paths are
not great circles, so eu-central-1 to ap-northeast-1 really runs 225 ms where the
model says 144.

What that means in practice: use the default six regions for any number you
intend to report. The extra regions are for exploring how the problem changes
with cluster size, and any figure built on them must say that their latencies are
modelled rather than measured.
"""

from __future__ import annotations

import numpy as np

from fragalloc.config import TopologyConfig
from fragalloc.topology import DEFAULT_RTT_MS

#: Name, latitude, longitude. The first six are the measured set.
MASTER_REGIONS: tuple[tuple[str, float, float], ...] = (
    ("us-east-1", 37.5, -77.5),
    ("us-west-2", 45.8, -122.7),
    ("eu-west-1", 53.3, -6.3),
    ("eu-central-1", 50.1, 8.7),
    ("ap-southeast-1", 1.3, 103.8),
    ("ap-northeast-1", 35.7, 139.7),
    ("sa-east-1", -23.5, -46.6),
    ("af-south-1", -33.9, 18.4),
    ("ap-south-1", 19.1, 72.9),
    ("me-south-1", 26.1, 50.6),
)

#: The city each region stands for, for maps and figure labels. These are the
#: metropolitan areas the corresponding public-cloud regions are sited near,
#: not the coordinates of any particular facility.
REGION_CITY: dict[str, str] = {
    "us-east-1": "Ashburn, Virginia",
    "us-west-2": "Boardman, Oregon",
    "eu-west-1": "Dublin, Ireland",
    "eu-central-1": "Frankfurt, Germany",
    "ap-southeast-1": "Singapore",
    "ap-northeast-1": "Tokyo, Japan",
    "sa-east-1": "Sao Paulo, Brazil",
    "af-south-1": "Cape Town, South Africa",
    "ap-south-1": "Mumbai, India",
    "me-south-1": "Manama, Bahrain",
}


def region_meta(names) -> list[dict]:
    """Name, city, latitude and longitude for each named region."""
    lookup = {n: (lat, lon) for n, lat, lon in MASTER_REGIONS}
    out = []
    for name in names:
        lat, lon = lookup.get(name, (0.0, 0.0))
        out.append({"name": name, "city": REGION_CITY.get(name, name),
                    "lat": lat, "lon": lon})
    return out

MEASURED = 6
MAX_REGIONS = len(MASTER_REGIONS)

#: Coefficients of the fitted distance model, in milliseconds and kilometres.
MODEL_INTERCEPT_MS = 10.4
MODEL_MS_PER_KM = 0.01430
EARTH_RADIUS_KM = 6371.0


def great_circle_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Haversine distance between two (latitude, longitude) pairs."""
    lat1, lon1 = np.radians(a)
    lat2, lon2 = np.radians(b)
    h = (np.sin((lat2 - lat1) / 2) ** 2
         + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2)
    return float(2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(h)))


def modelled_rtt_ms(a: tuple[float, float], b: tuple[float, float]) -> float:
    return MODEL_INTERCEPT_MS + MODEL_MS_PER_KM * great_circle_km(a, b)


def rtt_matrix(n_regions: int, intra_region_rtt_ms: float = 1.0) -> np.ndarray:
    """``(n, n)`` latency matrix: measured where available, modelled beyond."""
    if not 2 <= n_regions <= MAX_REGIONS:
        raise ValueError(f"n_regions must lie in [2, {MAX_REGIONS}]")

    matrix = np.zeros((n_regions, n_regions), dtype=np.float64)
    for i in range(n_regions):
        for j in range(i + 1, n_regions):
            if i < MEASURED and j < MEASURED:
                value = DEFAULT_RTT_MS[i][j]
            else:
                _, lat_i, lon_i = MASTER_REGIONS[i]
                _, lat_j, lon_j = MASTER_REGIONS[j]
                value = modelled_rtt_ms((lat_i, lon_i), (lat_j, lon_j))
            matrix[i, j] = matrix[j, i] = round(value, 1)
    np.fill_diagonal(matrix, intra_region_rtt_ms)
    return matrix


def topology_for(n_regions: int) -> TopologyConfig:
    """A :class:`TopologyConfig` using the first ``n_regions`` master regions."""
    chosen = MASTER_REGIONS[:n_regions]
    return TopologyConfig(
        region_names=tuple(name for name, _, _ in chosen),
        region_longitudes_deg=tuple(lon for _, _, lon in chosen),
        rtt_matrix_ms=tuple(tuple(row) for row in rtt_matrix(n_regions)),
    )


def is_modelled(n_regions: int) -> bool:
    """True when the topology relies on modelled rather than measured latencies."""
    return n_regions > MEASURED
