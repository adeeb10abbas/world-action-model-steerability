"""Compact original violin plot using the saved results and plotting routine.

Only figure layout and reader-facing labels change; all observations, offsets,
means, confidence intervals, and density settings are inherited unchanged.
"""
from pathlib import Path
import importlib.util
import json
import re
from matplotlib.figure import Figure
from matplotlib.text import Text

HERE = Path(__file__).resolve().parents[2]
LABELS = {'D':'DIR','S':'TF','I':'RF'}
spec = importlib.util.spec_from_file_location('original_figures', HERE/'generate_figures.py')
original = importlib.util.module_from_spec(spec)
spec.loader.exec_module(original)
results = json.loads((HERE/'analysis/paper_results.json').read_text())
savefig = Figure.savefig

def compact_save(figure, filename, *args, **kwargs):
    source = Path(filename)
    if source.stem != 'wording_effect':
        return
    for label in list(figure.texts):
        if label.get_text().startswith(('Requested arrangement', '32 matched starts')):
            label.remove()
    for label in figure.findobj(Text):
        label.set_text(re.sub(r'\b[DSI]\b', lambda m: LABELS[m.group()], label.get_text()))
    for ax in figure.axes:
        ax.title.set_fontsize(8)
        ax.set_xlabel('Placement-rate difference\n(percentage points)', fontsize=7.4)
    figure.set_size_inches(5.5, 2.40)
    figure.subplots_adjust(left=.115, right=.985, top=.90, bottom=.27, wspace=.24)
    destination = HERE/'revision_assets'/('rev_wording_effect'+source.suffix)
    if source.suffix == '.pdf':
        kwargs['metadata']={'Title':'Wording effects across matched physical starts','Author':'Anonymous Authors'}
    savefig(figure, destination, *args, **kwargs)
    print(destination)

Figure.savefig = compact_save
try:
    original.figures(results)
finally:
    Figure.savefig = savefig
