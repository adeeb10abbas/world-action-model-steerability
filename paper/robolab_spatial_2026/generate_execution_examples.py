#!/usr/bin/env python3
"""Render two observed execution pairs; never synthesize or annotate image pixels.

Run from any directory with Python, Pillow and Matplotlib:
    python paper/robolab_spatial_2026/generate_execution_examples.py

Inputs are the six full-resolution canonical frames in figures/execution_frames.
Their video identities, extraction timestamps and hashes are recorded separately
in analysis/execution_examples_receipt.json. The same crop and 90-degree CCW
rotation are applied to every displayed frame. The full input frames are kept
unchanged alongside the resulting figure. All text and outlines are outside the
image rectangles. Outcome labels refer to the recorded episode predicates, not
independent judgments of instruction compliance from a single photograph.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from PIL import Image

HERE = Path(__file__).resolve().parent
CROP = (380, 100, 920, 635)  # left, upper, right, lower in original 1280 x 720 image
WIDTH, HEIGHT = 6.0, 4.8
TEAL, ORANGE, INK, GRAY = "#147D92", "#C46635", "#20252B", "#7B848A"

ROWS = (
    {
        "title": "A   Edge · mustard right of the raisin box",
        "top": 4.74,
        "files": ("a_start.png", "a_s.png", "a_i.png"),
        "headings": ("Shared start · 0 s", "Mover-first (S) · 40 s", "Reference-first (I) · 40 s"),
        "clauses": ("Object to move: mustard", "Mustard right of raisin box", "Raisin box left of mustard"),
        "outcomes": ("Goal initially unmet", "Arrangement reached", "Arrangement not reached"),
    },
    {
        "title": "B   Nano · cube behind the bowl",
        "top": 2.34,
        "files": ("b_start.png", "b_s.png", "b_i.png"),
        "headings": ("Shared start · 0 s", "Mover-first (S) · 25.4 s", "Reference-first (I) · 25.4 s"),
        "clauses": ("Object to move: cube", "Cube behind bowl", "Bowl in front of cube"),
        "outcomes": ("Goal initially unmet", "Arrangement not reached", "Relation reached; bowl moved"),
    },
)


def render(input_dir: Path, output_dir: Path) -> None:
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9,
                         "pdf.fonttype": 42, "ps.fonttype": 42, "savefig.facecolor": "white"})
    fig = plt.figure(figsize=(WIDTH, HEIGHT), facecolor="white")
    image_height = 1.64
    # Rotation makes the crop 535 pixels wide and 540 pixels tall.
    image_width = image_height * (CROP[3] - CROP[1]) / (CROP[2] - CROP[0])
    centres = (1.0, 3.0, 5.0)
    colors = (GRAY, TEAL, ORANGE)
    for row in ROWS:
        top = row["top"]
        fig.text(.18 / WIDTH, top / HEIGHT, row["title"], ha="left", va="top",
                 fontsize=10.1, weight="bold", color=INK)
        image_top = top - .32
        image_bottom = image_top - image_height
        for col, (cx, color, filename) in enumerate(zip(centres, colors, row["files"])):
            path = input_dir / filename
            with Image.open(path) as original:
                if original.size != (1280, 720):
                    raise ValueError(f"Expected unmodified 1280x720 frame: {path}: {original.size}")
                displayed = original.convert("RGB").crop(CROP).transpose(Image.Transpose.ROTATE_90)
            left = cx - image_width / 2
            ax = fig.add_axes([left / WIDTH, image_bottom / HEIGHT, image_width / WIDTH, image_height / HEIGHT])
            ax.imshow(displayed, interpolation="none", aspect="equal")
            ax.set_axis_off()
            # Outline is outside the image; no arrow, marker or text obscures evidence.
            pad = .009
            border = Rectangle(((left-pad) / WIDTH, (image_bottom-pad) / HEIGHT),
                               (image_width+2*pad) / WIDTH, (image_height+2*pad) / HEIGHT,
                               transform=fig.transFigure, facecolor="none", edgecolor=color,
                               linewidth=.85, clip_on=False)
            fig.add_artist(border)
            fig.text(cx / WIDTH, (top-.18) / HEIGHT, row["headings"][col], ha="center", va="top",
                     fontsize=9, weight="medium", color=color)
            fig.text(cx / WIDTH, (image_bottom-.055) / HEIGHT, row["clauses"][col],
                     ha="center", va="top", fontsize=8.8, color=INK)
            fig.text(cx / WIDTH, (image_bottom-.205) / HEIGHT, row["outcomes"][col],
                     ha="center", va="top", fontsize=8.8,
                     weight="medium" if col else "normal", color=color)
    output_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_dir / "execution_examples.pdf", dpi=330,
                metadata={"Title": "Observed paired executions under alternative spatial descriptions",
                          "Subject": "Real simulation frames; common crop and rotation; annotations outside image pixels"})
    fig.savefig(output_dir / "execution_examples.png", dpi=300)
    plt.close(fig)
    print(f"Saved {output_dir / 'execution_examples.pdf'}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=HERE / "figures/execution_frames")
    parser.add_argument("--output-dir", type=Path, default=HERE / "figures")
    args = parser.parse_args()
    render(args.input_dir, args.output_dir)


if __name__ == "__main__":
    main()
