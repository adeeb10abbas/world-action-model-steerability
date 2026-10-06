"""Render current prompt labels from saved results without rerunning analysis.

Historical D/S/I data keys and the original manuscript figures stay unchanged.
Only the two figures used by the coauthor revision are exported here.
"""
from pathlib import Path
import importlib.util
import json
import re

from matplotlib.figure import Figure
from matplotlib.text import Text

HERE = Path(__file__).resolve().parent
LABELS = {"D": "DIR", "S": "TF", "I": "RF"}
OUTPUTS = {
    "wording_effect": "rev_wording_effect",
    "goal_response_by_form": "rev_goal_response_by_form",
}


def main():
    spec = importlib.util.spec_from_file_location("original_figures", HERE / "generate_figures.py")
    original = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(original)
    results = json.loads((HERE / "analysis/paper_results.json").read_text())
    savefig = Figure.savefig

    def save_revision(figure, filename, *args, **kwargs):
        source = Path(filename)
        if source.stem not in OUTPUTS:
            return
        if source.stem == "goal_response_by_form":
            for axis in figure.axes[:3]:
                axis.set_yticks((0, 1, 2), ("DIR", "TF", "RF"), fontsize=8)
        for label in figure.findobj(Text):
            label.set_text(re.sub(r"\b[DSI]\b", lambda m: LABELS[m.group()], label.get_text()))
        if source.stem == "wording_effect":
            for axis in figure.axes:
                axis.title.set_fontsize(8.0)
        destination = HERE / "revision_assets" / (OUTPUTS[source.stem] + source.suffix)
        savefig(figure, destination, *args, **kwargs)
        print(destination)

    Figure.savefig = save_revision
    try:
        original.figures(results)
    finally:
        Figure.savefig = savefig


if __name__ == "__main__":
    main()
