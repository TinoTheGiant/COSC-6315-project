#!/usr/bin/env python3
"""Build the anonymised copy of the repository for double-blind review.

    python scripts/anonymise.py OUTDIR

Copies the files git tracks into OUTDIR, minus material that identifies the
author or the course and is not needed to check the paper, rewrites
identifying strings in text files, and then scans every copied file, text and
binary, for the identifiers. It exits non-zero, and prints each hit, if any
survive. Run it on the commit that is submitted; the zip it writes is what
goes to anonymous.4open.science or the submission system.

The scan is the check. A rewrite rule that misses a spelling is caught by the
scan, not trusted.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: Not needed to check the paper, and identifying: the course midterm draft
#: and its slides, the CCGrid build's intermediate review notes, project
#: status notes that name people, and the midterm sections.
EXCLUDE_PREFIXES = (
    "deck/",
    "paper/main.",               # midterm draft: .tex, .pdf, .docx
    "paper/sections/0",          # midterm sections; the CCGrid paper uses sections/full/
    "paper/reviews/",
    "paper/README.md",
    "docs/publication-readiness.md",
    ".github/CODEOWNERS",
    "scripts/anonymise.py",      # holds the patterns it removes
)

#: Ordered rewrites, applied to every text file that is copied.
REWRITES: tuple[tuple[str, str], ...] = (
    (r"Course project, COSC 6315\. Tinotenda Kaseke, September to October 2026\.",
     "Anonymised for double-blind review."),
    (r"TinoTheGiant/COSC-6315-project", "anonymous/repository"),
    (r"COSC-6315-project", "repository"),
    (r"https?://github\.com/TinoTheGiant[^\s)\"']*", "https://anonymous.4open.science/"),
    (r"TinoTheGiant", "anonymous"),
    (r"Tinotenda Kaseke", "the author"),
    (r"Tino Kaseke", "the author"),
    (r"Tino's laptop", "a laptop"),
    (r"\bby Tino\b", "by the author"),
    (r"\bTino\b", "the author"),
    (r"Kaseke", "Author"),
    (r"[\w.]+@utpb\.edu", "anonymous@example.org"),
    (r"tinokaseke@gmail\.com", "anonymous@example.org"),
    (r"University of Texas Permian Basin", "the author's university"),
    (r"\bUTPB\b", "the university"),
    (r"COSC[ -]?6315", "the course"),
    (r"(?i)C:\\\\?Users\\\\?tinok", r"C:\\Users\\user"),
    (r"(?i)/c/Users/tinok", "/c/Users/user"),
    (r"\btinok\b", "user"),
    (r"(?i)Im-Alien", "host"),
)

#: What the scan refuses to find anywhere, text or binary.
FORBIDDEN = re.compile(
    rb"(?i)kaseke|tinothegiant|tinok\b|tinotenda|\btino\b|utpb|permian|cosc[ -]?6315|"
    rb"im-alien|odessa"
)

TEXT_SUFFIXES = {
    ".py", ".md", ".tex", ".bib", ".txt", ".csv", ".json", ".yml", ".yaml", ".toml",
    ".cfg", ".ini", ".sh", ".js", ".ts", ".html", ".css", ".sty", ".cls", ".bst", "",
}


def tracked_files() -> list[str]:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True)
    return [p for p in out.stdout.decode().split("\0") if p]


def excluded(path: str) -> bool:
    return any(path.startswith(p) for p in EXCLUDE_PREFIXES)


def rewrite(text: str) -> str:
    for pattern, repl in REWRITES:
        text = re.sub(pattern, repl, text)
    return text


def build(outdir: Path) -> list[str]:
    if outdir.exists():
        shutil.rmtree(outdir)
    copied = []
    for rel in tracked_files():
        if excluded(rel):
            continue
        src, dst = ROOT / rel, outdir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.suffix.lower() in TEXT_SUFFIXES:
            try:
                dst.write_text(rewrite(src.read_text(encoding="utf-8")), encoding="utf-8")
            except UnicodeDecodeError:
                shutil.copy2(src, dst)
        else:
            shutil.copy2(src, dst)
        copied.append(rel)
    return copied


def scan(outdir: Path) -> list[str]:
    hits = []
    for path in sorted(p for p in outdir.rglob("*") if p.is_file()):
        rel = str(path.relative_to(outdir))
        if FORBIDDEN.search(rel.encode()):
            hits.append(f"{rel}: identifying file name")
        blobs = [("", path.read_bytes())]
        # Compressed members hide their text from a byte scan: look inside.
        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as zf:
                blobs += [(f"!{n}", zf.read(n)) for n in zf.namelist()]
        for member, data in blobs:
            m = FORBIDDEN.search(data)
            if m:
                start = max(0, m.start() - 30)
                hits.append(f"{rel}{member}: ...{data[start:m.end() + 30]!r}...")
    return hits


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    outdir = Path(argv[1]).resolve()
    copied = build(outdir)
    hits = scan(outdir)
    print(f"copied {len(copied)} files to {outdir}")
    if hits:
        print(f"FAIL: {len(hits)} file(s) still identify the author:")
        for h in hits:
            print("  " + h)
        return 1
    archive = shutil.make_archive(str(outdir), "zip", outdir)
    print(f"PASS: no identifier found. Archive: {archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
