"""Readable paper figures from the unchanged, verified forecast-media pixels.

Only writes the three *_paper PDF/PNG pairs in revision_assets. The original
media, figures, annotations, and provenance remain unchanged.
"""
from pathlib import Path
import importlib.util

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import numpy as np

HERE = Path(__file__).resolve().parent
OUT = HERE.parents[1] / 'revision_assets'
spec = importlib.util.spec_from_file_location('verified_media', HERE / 'build_forecast_example_figures.py')
source = importlib.util.module_from_spec(spec)
spec.loader.exec_module(source)
plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10.5,
                     'pdf.fonttype': 42, 'savefig.facecolor': 'white'})
INK, MUTED, PURPLE = '#20313d', '#54626d', '#7040a0'
WIDTH = 7.2


def text(fig, x, y, value, **kwargs):
    fig.text(x / WIDTH, y / fig.get_figheight(), value, color=INK,
             va='baseline', **kwargs)


def panel(fig, pixels, x, y, width, border=None):
    """Embed the original RGB array without filtering, cropping, or retouching."""
    height = width * pixels.shape[0] / pixels.shape[1]
    ax = fig.add_axes([x / WIDTH, y / fig.get_figheight(),
                       width / WIDTH, height / fig.get_figheight()])
    ax.imshow(pixels, interpolation='none', aspect='equal')
    ax.set_axis_off()
    if border:
        pad = .007
        fig.add_artist(Rectangle(((x-pad)/WIDTH, (y-pad)/fig.get_figheight()),
                                 (width+2*pad)/WIDTH,
                                 (height+2*pad)/fig.get_figheight(),
                                 transform=fig.transFigure, facecolor='none',
                                 edgecolor=border, linewidth=.65))


def save(fig, name):
    # Keep PDF image objects at their source pixel dimensions.
    fig.savefig(OUT / f'{name}.pdf', metadata={'Title': name.replace('_', ' ')})
    fig.savefig(OUT / f'{name}.png', dpi=250)
    plt.close(fig)
    print(OUT / f'{name}.pdf')


def example(entry, data):
    fig = plt.figure(figsize=(WIDTH, 4.40))
    text(fig, .10, 4.20, entry['model_name'], fontsize=14, weight='bold')
    text(fig, .10, 4.015, 'Request observation', fontsize=10.5)
    panel(fig, data['raw'], .10, 2.70, 2.20)
    text(fig, 2.55, 3.84, 'Requested placement', fontsize=10.5)
    text(fig, 2.55, 3.57, 'Cube behind the bowl', fontsize=13, weight='bold')
    text(fig, 2.55, 3.25, 'Target: cube     Reference: bowl', fontsize=11)
    text(fig, 2.55, 2.96, 'Same camera and 32-action chunk', fontsize=10.5)
    for i, col in enumerate(data['cols']):
        left = .10 + i * 1.42
        text(fig, left + .675, 2.51,
             f"k = {col['k']}  |  +{col['dt']:.2f} s", fontsize=10, ha='center')
        panel(fig, col['pred'], left, 1.51, 1.35, PURPLE)
        panel(fig, col['exec'], left, .49, 1.35, INK)
    text(fig, .10, 2.35, 'Predicted', fontsize=11, weight='bold')
    text(fig, .10, 1.33, 'Executed', fontsize=11, weight='bold')
    text(fig, .10, .29,
         'Predicted k = 0 is reconstructed. Executed k = 0 is the request observation.',
         fontsize=9.8)
    text(fig, .10, .09,
         'Nominal frame times do not establish the pace of generated motion.', fontsize=9.8)
    save(fig, f"rev_forecast_{source.SLUG[entry['model']]}_paper")


def packets(data):
    if not np.array_equal(data['E3']['legend'], data['F3']['legend']):
        raise ValueError('The two original legends differ.')
    fig = plt.figure(figsize=(WIDTH, 9.60))
    text(fig, .10, 9.40, 'Original annotation materials', fontsize=14, weight='bold')
    text(fig, .40, 9.13, 'Shared scene legend shown to the VLMs', fontsize=11)
    panel(fig, data['E3']['legend'], .40, 7.22, 6.40)
    text(fig, .40, 7.00, 'Cosmos3 Edge forecast', fontsize=12, weight='bold')
    panel(fig, data['E3']['sheet'], 1.15, 3.75, 4.90)
    text(fig, .40, 3.54, 'FLUX 3 Action forecast', fontsize=12, weight='bold')
    panel(fig, data['F3']['sheet'], 1.15, .29, 4.90)
    text(fig, .10, .08,
         'Human-review summaries shown here. VLMs received eight sampled video frames.',
         fontsize=10)
    save(fig, 'rev_forecast_packets_paper')


def main():
    if not source.V['all_checks_pass'] or source.V['failed_checks']:
        raise ValueError('The source verification contains failures.')
    OUT.mkdir(exist_ok=True)
    data = {}
    for entry in source.V['examples']:
        data[entry['model']] = source.load(entry)
        example(entry, data[entry['model']])
    packets(data)


if __name__ == '__main__':
    main()
