"""Render four scene views with separate bands for titles, images, and goals."""
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from PIL import Image

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / 'paper/robolab_spatial_2026/revision_assets'
OUT.mkdir(parents=True, exist_ok=True)
plt.rcParams.update({'font.family': 'DejaVu Sans', 'pdf.fonttype': 42})
fig = plt.figure(figsize=(7.2, 4.0), facecolor='white')
scenes = [
    ('S1', 'Cube and bowl', 'Cube left, right, in front of,\nor behind the bowl'),
    ('S3', 'Butter and raisin box', 'Butter left, right, or on top\nof the raisin box'),
    ('S4', 'Mustard and raisin box', 'Mustard left, right, or on top\nof the raisin box'),
    ('S5', 'Two bowls', 'Stack either bowl\non the other'),
]
for i, (scene, title, goal) in enumerate(scenes):
    col, row = i % 2, i // 2
    left = .02 + col * .50
    center = left + .23
    title_y = .965 - row * .49
    image_bottom = .635 - row * .49
    label_y = .605 - row * .49
    ax = fig.add_axes([left, image_bottom, .46, .265])
    ax.imshow(Image.open(ROOT / f'docs/robolab-workshop-20260926/scene_images/{scene}.jpg'))
    ax.axis('off')
    fig.text(center, title_y, title, ha='center', va='top', fontsize=12, weight='bold')
    fig.text(center, label_y, goal, ha='center', va='top', fontsize=10.5, linespacing=1.25)
fig.savefig(OUT / 'rev_scene_overview.pdf', dpi=200)
fig.savefig(OUT / 'rev_scene_overview.png', dpi=180)
plt.close(fig)
