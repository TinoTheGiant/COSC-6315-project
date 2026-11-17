"""The anonymiser's scan must catch what its rewrites miss."""

from __future__ import annotations

import importlib.util
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "anonymise", Path(__file__).resolve().parents[1] / "scripts" / "anonymise.py")
anonymise = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(anonymise)


def test_rewrites_remove_every_known_identifier():
    text = ("Tinotenda Kaseke, UTPB, COSC 6315, TinoTheGiant/COSC-6315-project, "
            "kaseke_t87479@utpb.edu, C:\\Users\\tinok\\x, Tino's laptop")
    assert not anonymise.FORBIDDEN.search(anonymise.rewrite(text).encode())


def test_scan_finds_an_identifier_in_text_and_binary(tmp_path):
    (tmp_path / "clean.md").write_text("nothing here")
    assert anonymise.scan(tmp_path) == []
    (tmp_path / "leak.bin").write_bytes(b"\x00\x01Author: Kaseke\x00")
    (tmp_path / "leak.md").write_text("Repository: TinoTheGiant/x")
    hits = anonymise.scan(tmp_path)
    assert len(hits) == 2


def test_palatino_is_not_a_false_positive(tmp_path):
    (tmp_path / "IEEEtran.cls").write_text("% use Palatino as the main text font")
    assert anonymise.scan(tmp_path) == []


def test_scan_looks_inside_zip_files(tmp_path):
    import zipfile
    with zipfile.ZipFile(tmp_path / "model.zip", "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("system_info.txt", "user: tinok on Im-Alien " * 20)
    assert len(anonymise.scan(tmp_path)) == 1
