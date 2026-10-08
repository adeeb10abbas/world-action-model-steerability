"""Author-review preview only; preserve the current manuscript and figures."""
from pathlib import Path
import csv
import hashlib
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

PAPER = Path(__file__).resolve().parents[2]
ROOT = PAPER.parents[1]
SOURCE = PAPER / 'analysis/wording_contrasts.csv'
OUT = ROOT / 'output/figures/wording_effect_simple_preview'
PDF = ROOT / 'output/pdf/wording_effect_simple_preview.pdf'
rows = {(r['model'], r['contrast']): r for r in csv.DictReader(SOURCE.open())
        if r['stratum'] == 'all' and r['endpoint'] == 'stable_ever'}
models = [('N3', 'Nano', '#087F8C'), ('E3', 'Edge', '#D97926'),
          ('F3', 'FLUX', '#7856A5'), ('pooled', 'Pooled', '#20252B')]
plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 9.5,
                     'pdf.fonttype': 42, 'ps.fonttype': 42,
                     'axes.unicode_minus': True, 'savefig.facecolor': 'white'})
fig = plt.figure(figsize=(7.8, 3.35), facecolor='white')
axes = [fig.add_axes([.105, .255, .32, .47]),
        fig.add_axes([.60, .255, .32, .47])]
fig.text(.5, .965, 'How much does wording change the placement rate?',
         ha='center', va='top', fontsize=12, fontweight='bold', color='#17232B')
fig.text(.5, .865, 'Point = average effect     Bar = 95% confidence interval',
         ha='center', va='center', fontsize=9, color='#48525A')
plotted = []
for ax, key, title, neg, pos in zip(axes, ['S-I', 'D-S'],
      ['Target-first vs. reference-first (TF − RF)', 'Direct vs. target-first (DIR − TF)'],
      ['RF higher', 'TF higher'], ['TF higher', 'DIR higher']):
    ax.set_title(title, fontsize=9.2, pad=13, color='#17232B')
    ax.set_xlim(-12, 25)
    ax.set_ylim(3.55, -.50)
    ax.set_xticks([-10, 0, 10, 20], ['−10', '0', '+10', '+20'])
    ax.set_yticks(range(4), [m[1] for m in models])
    ax.tick_params(axis='y', length=0, pad=8, labelsize=10)
    ax.tick_params(axis='x', length=3, labelsize=9, colors='#48525A')
    for side in ['top', 'right', 'left']:
        ax.spines[side].set_visible(False)
    ax.spines['bottom'].set_color('#9CA6AC')
    ax.axvline(0, color='#7A858C', linestyle=(0, (3, 3)), lw=1, zorder=1)
    ax.axhline(2.5, color='#DDE2E5', lw=.8, zorder=1)
    ax.grid(axis='x', color='#EDF0F2', lw=.65)
    for y, (model, name, color) in enumerate(models):
        r = rows[(model, key)]
        value, lo, hi = [100 * float(r[k]) for k in ['difference', 'ci_low', 'ci_high']]
        assert lo <= value <= hi
        ax.errorbar(value, y, xerr=[[value-lo], [hi-value]],
                    fmt='D' if model == 'pooled' else 'o', color=color,
                    markersize=6.2, elinewidth=1.7, capsize=3.4,
                    markeredgecolor='white', markeredgewidth=.6, zorder=3)
        ax.text(1.025, y, f'{value:+.1f}', transform=ax.get_yaxis_transform(),
                ha='left', va='center', fontsize=10, color=color,
                fontweight='bold' if model == 'pooled' else 'normal')
        plotted.append({'model': name, 'comparison': {'S-I':'TF-RF','D-S':'DIR-TF'}[key],
                        'mean_pp': value, 'ci95_low_pp': lo, 'ci95_high_pp': hi})
    ax.text(0, -.25, '← '+neg, transform=ax.transAxes,
            ha='left', va='center', color='#53616B', fontsize=8.8)
    ax.text(1, -.25, pos+' →', transform=ax.transAxes,
            ha='right', va='center', color='#53616B', fontsize=8.8)
fig.text(.5, .062, 'Difference in stable-placement rate (percentage points)',
         ha='center', va='center', fontsize=10)
fig.savefig(OUT.with_suffix('.png'), dpi=250)
fig.savefig(PDF, metadata={'Title':'Simpler wording-effect figure preview', 'Author':'Anonymous Authors'})
plt.close(fig)
(Path(__file__).parent/'validation.json').write_text(json.dumps({
    'source':str(SOURCE.relative_to(ROOT)),
    'source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
    'endpoint':'all episodes, stable placement at any time',
    'plotted_values':plotted,
    'uncertainty':'Existing 95% intervals from resampling physical starts within scenes',
    'manuscript_replaced':False,
    'plot_png':str(OUT.with_suffix('.png').relative_to(ROOT)),
    'plot_pdf':str(PDF.relative_to(ROOT))},indent=2)+'\n')
print(OUT.with_suffix('.png'))
print(PDF)
