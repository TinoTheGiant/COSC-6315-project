"""The cluster's geography must be the simulator's geography.

ADR-0009 makes weight transfer depend on the two halves of the pipeline agreeing
on the problem's shape, and geography is part of that shape. ADR-0011 makes the
agreement structural by generating the Compose file from `DEFAULT_RTT_MS`. These
tests are what stops someone hand-editing the generated file and quietly
decoupling the two.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from shardmind.config import ShardMindConfig
from shardmind.topology import DEFAULT_RTT_MS

yaml = pytest.importorskip("yaml")
REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def compose(tmp_path_factory) -> dict:
    out = tmp_path_factory.mktemp("gen") / "compose.yml"
    subprocess.run(
        [sys.executable, str(REPO / "scripts" / "gen_cluster.py"), "-o", str(out)],
        cwd=REPO, check=True,
        env={"PYTHONPATH": str(REPO / "src"), "PATH": "/usr/bin:/bin"},
    )
    return yaml.safe_load(out.read_text())


def _delays(service: dict) -> dict[str, float]:
    raw = service["environment"]["NETEM_RULES"]
    return {p.split("=")[0]: float(p.split("=")[1]) for p in raw.split(";") if p}


def test_one_node_per_region(compose) -> None:
    names = ShardMindConfig().topology.region_names
    assert len(compose["services"]) == len(names)


def test_each_node_declares_its_region_as_locality(compose) -> None:
    names = list(ShardMindConfig().topology.region_names)
    for i, name in enumerate(names):
        assert f"--locality=region={name}" in compose["services"][f"node{i}"]["command"]


def test_netem_delays_reconstruct_the_simulator_matrix(compose) -> None:
    """netem shapes egress only, so each side carries half the round trip. Two
    halves must add back up to the matrix the simulator uses, or every latency
    number the cluster produces describes a different world from the one the
    agent was pre-trained in."""
    n = len(compose["services"])
    for i in range(n):
        di = _delays(compose["services"][f"node{i}"])
        for j in range(n):
            if i == j:
                continue
            ip_j = f"172.28.0.{11 + j}"
            dj = _delays(compose["services"][f"node{j}"])
            ip_i = f"172.28.0.{11 + i}"
            round_trip = di[ip_j] + dj[ip_i]
            assert round_trip == pytest.approx(DEFAULT_RTT_MS[i][j], abs=0.01), (
                f"{i}->{j}: cluster would deliver {round_trip} ms, "
                f"simulator assumes {DEFAULT_RTT_MS[i][j]} ms"
            )


def test_a_node_does_not_shape_traffic_to_itself(compose) -> None:
    for i in range(len(compose["services"])):
        assert f"172.28.0.{11 + i}" not in _delays(compose["services"][f"node{i}"])


def test_every_node_can_shape_its_own_egress(compose) -> None:
    """Without NET_ADMIN the tc calls fail silently inside the entrypoint and the
    cluster runs with no latency at all, which looks like a spectacular result."""
    for svc in compose["services"].values():
        assert "NET_ADMIN" in svc["cap_add"]


def test_nodes_have_fixed_addresses(compose) -> None:
    """The netem filters match on destination IP, so the addresses cannot be
    left to Docker to assign."""
    for i, svc in enumerate(compose["services"].values()):
        assert svc["networks"]["crdb"]["ipv4_address"] == f"172.28.0.{11 + i}"


def test_memory_settings_fit_a_laptop(compose) -> None:
    """ADR-0010 budgets about 2.3 GB across the cluster so the machine stays
    usable for other work."""
    for svc in compose["services"].values():
        assert "--cache=128MiB" in svc["command"]
        assert "--max-sql-memory=256MiB" in svc["command"]


def test_all_nodes_join_the_same_cluster(compose) -> None:
    joins = {
        next(tok for tok in svc["command"].split() if tok.startswith("--join="))
        for svc in compose["services"].values()
    }
    assert len(joins) == 1
