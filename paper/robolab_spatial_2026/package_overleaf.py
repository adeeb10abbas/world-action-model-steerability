#!/usr/bin/env python3
"""Create the minimal coauthor Overleaf project, preserving manuscript bytes.

Run from any directory: python paper/robolab_spatial_2026/package_overleaf.py
The archive contains exactly nine files; no old staging files, build artifacts,
analysis tables, source videos or alternative manuscripts are included.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from zipfile import ZIP_DEFLATED, ZipFile

PAPER = Path(__file__).resolve().parent
REPO = PAPER.parents[1]
FILES = {
    "main.tex": "main.tex",
    "references.bib": "references.bib",
    "corl_2026.sty": "corl_2026.sty",
    "corlabbrvnat.bst": "corlabbrvnat.bst",
    "OVERLEAF_README.md": "README.md",
    "scene_mustard.jpg": "figures/scene_mustard.jpg",
    "figures/wording_effect.pdf": "figures/wording_effect.pdf",
    "figures/goal_response_by_form.pdf": "figures/goal_response_by_form.pdf",
    "figures/execution_examples.pdf": "figures/execution_examples.pdf",
}


def package(destination: Path) -> None:
    missing = [str(PAPER / source) for source in FILES if not (PAPER / source).is_file()]
    if missing:
        raise FileNotFoundError("Missing Overleaf inputs: " + ", ".join(missing))
    source = (PAPER / "main.tex").read_bytes()
    if rb"\graphicspath{{figures/}}" not in source:
        raise ValueError("The manuscript must resolve graphics from figures/.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(prefix=destination.stem + "-", suffix=".zip", dir=destination.parent, delete=False) as f:
        temporary = Path(f.name)
    try:
        with ZipFile(temporary, "w", ZIP_DEFLATED) as archive:
            for source_name, archive_name in FILES.items():
                archive.write(PAPER / source_name, archive_name)
        with ZipFile(temporary) as archive:
            assert len(archive.namelist()) == 9
            assert set(archive.namelist()) == set(FILES.values())
            assert archive.read("main.tex") == source
            for source_name, archive_name in FILES.items():
                assert archive.read(archive_name) == (PAPER / source_name).read_bytes()
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    print(json.dumps({"archive": str(destination), "file_count": len(FILES), "main_document": "main.tex",
                      "main_tex_sha256": hashlib.sha256(source).hexdigest()}, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=REPO / "output/pdf/same_goal_different_words_overleaf.zip")
    package(parser.parse_args().output)


if __name__ == "__main__":
    main()
