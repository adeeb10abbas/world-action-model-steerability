#!/usr/bin/env python3
"""Build the appendix figures and provenance for the two preselected forecast examples.

Input is forecast_media/: the compact subset of the cluster extraction made by extract_forecast_examples.py.
Before drawing, every committed file and every displayed pixel window is re-hashed against
forecast_media/verification.json, and the build stops unless all extraction checks passed. Nothing is run on the
simulator, the policies, or the VLM labelers.

Outputs (paths relative to paper/robolab_spatial_2026/):
  revision_assets/rev_forecast_example_{edge,flux}.{pdf,png}  generated future vs. execution of the same request
  revision_assets/rev_forecast_packet_{edge,flux}.{pdf,png}   original annotation packet (prediction only)
  revisions/20261001/forecast_media_provenance.json           sources, identities, mappings, commands

    python paper/robolab_spatial_2026/revisions/20261001/build_forecast_example_figures.py
"""
from pathlib import Path
import hashlib
import json
import platform

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.patches import Circle, Rectangle
import numpy as np
import PIL
from PIL import Image

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
MEDIA = HERE / 'forecast_media'
OUT = HERE.parents[1] / 'revision_assets'
PROVENANCE = HERE / 'forecast_media_provenance.json'
V = json.loads((MEDIA / 'verification.json').read_text())

NS, POD = '211247-prod', '211247-aliv100-v100-1gpu'
ENV_PY = '/data/users/ali/vla_wam/envs/robolab-v2-isaac50/bin/python'
SLUG = {'E3': 'edge', 'F3': 'flux'}
LABEL_KEYS = ('a', 'b', 'adjudicated')
VLM_NAMES = {'qwen3-vl-235b': 'Qwen3-VL-235B-A22B-Instruct-FP8', 'glm-4.5v': 'GLM-4.5V-FP8'}
VLM_SHORT = {'qwen3-vl-235b': 'Qwen3-VL', 'glm-4.5v': 'GLM-4.5V'}
FIELDS = (('Moving\nobject', 'moving_object', 'fc_moving_object_role'), ('Direction', 'direction', 'fc_direction'),
          ('Final\nrelation', 'visible_final_relation', 'fc_visible_final_relation'),
          ('Relation\nobject', 'relation_object', None))
FLAGS = ('possible_release', 'missing_object', 'hallucinated_object')
NAME = {'banana': 'banana', 'bowl': 'bowl', 'rubiks_cube': "Rubik's cube"}
SHORT = {'banana': 'banana', 'bowl': 'bowl', 'rubiks_cube': 'cube'}
PRED, EXEC, MUTED, RULE = '#6a3d9a', '#1f2a33', '#4a5966', '#c9ced3'
ROLE = {'mover': '#147D92', 'reference': '#C46635', 'other': '#5f6b76'}
FIG_W, PNG_DPI, CONTEXT_REDUCE = 7.2, 250, 2
INSET = 4  # PNG pixels under each panel's 1.4 pt border, excluded from the exact-enlargement check
DISPLAY = {}
SHARED_START = any(c['check'] == 'examples_share_initial_state' and c['pass'] for c in V['checks'])
plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10, 'pdf.fonttype': 42})


def sha256(p) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def arr_sha(a) -> str:
    """experiments/robolab_workshop/worker.py arr_sha: hash of dtype, shape and C-order bytes."""
    a = np.ascontiguousarray(a)
    return hashlib.sha256(f"{a.dtype.str}{a.shape}".encode() + a.tobytes()).hexdigest()


def rel(p) -> str:
    return Path(p).resolve().relative_to(REPO).as_posix()


def local(entry: dict) -> Path:
    return MEDIA / Path(entry['path']).relative_to(V['out'])


def verified(entry: dict):
    """Committed copy of one cluster output, after re-checking its file hash and, for frames, its pixel hash."""
    p = local(entry)
    if sha256(p) != entry['file_sha256']:
        raise SystemExit(f'file hash differs from verification.json: {rel(p)}')
    if 'pixels_sha256' not in entry:
        return p, None
    a = np.asarray(Image.open(p))
    if list(a.shape) != entry['shape'] or arr_sha(a) != entry['pixels_sha256']:
        raise SystemExit(f'pixel hash differs from verification.json: {rel(p)}')
    return p, a


def load(e: dict) -> dict:
    fc, c, pre = e['files']['compact'], e['crop'], e['request']['pre_tick']
    if [m['k'] for m in e['frame_mapping']] != V['selected_k']:
        raise SystemExit(f"{e['model']}: frame mapping does not list the selected frames")
    win = (slice(c['y0'], c['y0'] + c['h']), slice(c['x0'], c['x0'] + c['w']))
    cols = []
    for m in e['frame_mapping']:
        k, tick = m['k'], m['tick']
        if (m['generated_frame_index'], m['exec_frame_index'], tick) != (k, pre + k, pre + k) \
                or abs(m['t_s'] - tick / V['fps']) > 1e-9 or abs(m['t_after_request_s'] - k / V['fps']) > 1e-9:
            raise SystemExit(f"{e['model']}: inconsistent frame mapping at k={k}")
        pred = verified(fc[f'pred_cell_k{k:02d}'])[1][win]
        exe = verified(fc[f'exec_cell_tick{tick:03d}'])[1][win]
        ref = e['crop_pixels'][str(k)]
        if (arr_sha(pred), arr_sha(exe)) != (ref['pred_crop_pixels_sha256'], ref['exec_crop_pixels_sha256']):
            raise SystemExit(f"{e['model']}: displayed window differs from the extraction record at k={k}")
        cols.append({'k': k, 'tick': tick, 't': m['t_s'], 'dt': m['t_after_request_s'], 'pred': pred, 'exec': exe})
    raw = verified(fc['raw_camera_request_tick'])[1]
    files = {n: verified(fc[f'packet_{n}'])[0] for n in ('packet.json', 'legend.png', 'contact_sheet.png')}
    for n, p in files.items():
        if sha256(p) != e['packet']['sha256'][n]:
            raise SystemExit(f"{e['model']}: {n} is not the packet file recorded for {e['annotation_id']}")
    if json.loads(files['packet.json'].read_text()) != e['packet']['packet_json']:
        raise SystemExit(f"{e['model']}: packet.json differs from the extraction record")
    return {'cols': cols, 'raw': raw, 'legend': np.asarray(Image.open(files['legend.png']).convert('RGB')),
            'sheet': np.asarray(Image.open(files['contact_sheet.png']).convert('RGB'))}


def snap(v: float) -> float:
    """Round inches to whole PNG pixels so image panels are exact integer enlargements."""
    return round(v * PNG_DPI) / PNG_DPI


_PROBE = Figure(figsize=(FIG_W, 2))
_PROBE_RENDERER = FigureCanvasAgg(_PROBE).get_renderer()
SEP = '  ·  '


def text_size(s: str, **kw) -> tuple[float, float]:
    """Rendered width and height of a block of text, in inches."""
    t = _PROBE.text(0, 0.5, s, **kw)
    bb = t.get_window_extent(_PROBE_RENDERER)
    t.remove()
    return bb.width / _PROBE.dpi, bb.height / _PROBE.dpi


def fit(lines, width: float, size: float, floor: float, **kw) -> float:
    """Largest font size, at most size, at which every line fits in width."""
    while max(text_size(s, fontsize=size, **kw)[0] for s in lines) > width:
        size = round(size - 0.1, 1)
        if size < floor:
            raise SystemExit(f'text does not fit in {width:.2f} in: {lines}')
    return size


def wrap(s: str, width: float, sep: str = ' ', **kw) -> str:
    """Break s at sep so that every line fits in width."""
    lines = []
    for piece in s.split(sep):
        if lines and text_size(lines[-1] + sep + piece, **kw)[0] <= width:
            lines[-1] += sep + piece
        elif text_size(piece, **kw)[0] > width:
            raise SystemExit(f'unbreakable text wider than {width:.2f} in: {piece}')
        else:
            lines.append(piece)
    return '\n'.join(lines)


def run_lines(parts, width: float, **kw) -> list:
    """Split coloured pieces of text into lines no wider than width; blank spacer pieces never start a line."""
    lines, w = [[]], 0.0
    for s, color in parts:
        sw = text_size(s, **kw)[0]
        if s.strip() and lines[-1] and w + sw > width:
            while not lines[-1][-1][0].strip():
                lines[-1].pop()
            lines.append([])
            w = 0.0
        if lines[-1] or s.strip():
            lines[-1].append((s, color))
            w += sw
    return lines


def stack(items, top: float = 0.07) -> tuple[dict, float]:
    """Top coordinate of each (key, height, gap below) block, stacked downwards from top."""
    y = {}
    for key, h, gap in items:
        y[key], top = top, top + h + gap
    return y, top


class Canvas:
    """A figure laid out in inches from its top-left corner."""

    def __init__(self, height: float):
        self.h = snap(height)
        self.fig = plt.figure(figsize=(FIG_W, self.h))
        self.smooth, self.exact, self.images, self.tags = [], [], {}, []

    def ax(self, x, top, w, h):
        x, top, w, h = map(snap, (x, top, w, h))
        a = self.fig.add_axes((x / FIG_W, 1 - (top + h) / self.h, w / FIG_W, h / self.h))
        a.set_xticks([]), a.set_yticks([])
        return a

    def image(self, ax, img, exact: bool, name: str, **kw):
        """The PDF embeds every image at its own resolution. In the PNG, exact panels are integer pixel
        enlargements (checked in save) and other images are antialiased."""
        im = ax.imshow(img, interpolation='none', **kw)
        pos = ax.get_position()
        x0, y0 = round(pos.x0 * FIG_W * PNG_DPI), round((1 - pos.y1) * self.h * PNG_DPI)
        w, h = round(pos.width * FIG_W * PNG_DPI), round(pos.height * self.h * PNG_DPI)
        if exact:
            f = w // img.shape[1]
            if f < 1 or (w, h) != (f * img.shape[1], f * img.shape[0]):
                raise SystemExit(f'{name}: panel of {w}x{h} PNG pixels is not an integer enlargement')
            self.exact.append((x0, y0, f, img))
        else:
            self.smooth.append(im)
        rec = self.images.setdefault(name, {'image': name, 'source_px': [img.shape[1], img.shape[0]],
                                            'png_px': [w, h], 'count': 0, 'pdf': 'embedded at source resolution',
                                            'png': f'exact {w // img.shape[1]}x pixel replication' if exact
                                            else 'antialiased resampling'})
        rec['count'] += 1
        return im

    def tag(self, ax, s, color):
        """A label drawn over an exact panel; the enlargement check skips the pixels under it."""
        self.tags.append(ax.text(.035, .06, s, transform=ax.transAxes, fontsize=7.2, color='white', va='bottom',
                                 bbox=dict(boxstyle='round,pad=0.2', fc=color, ec='none', alpha=.85)))

    def text(self, x, top, s, **kw):
        kw.setdefault('va', 'top')
        return self.fig.text(x / FIG_W, 1 - top / self.h, s, **kw)

    def run(self, x, top, parts, **kw):
        """Pieces of text in different colours on one line."""
        for s, color in parts:
            self.text(x, top, s, color=color, **kw)
            x += text_size(s, **kw)[0]
        return x

    def rule(self, x0, x1, top):
        self.fig.add_artist(Line2D([x0 / FIG_W, x1 / FIG_W], [1 - top / self.h] * 2, color=RULE, lw=.7))

    def draw(self, ops) -> None:
        for kind, args, kw in ops:
            getattr(self, kind)(*args, **kw)

    def save(self, stem: Path) -> list[Path]:
        self.fig.savefig(stem.with_suffix('.pdf'), metadata={'CreationDate': None})
        for im in self.smooth:
            im.set_interpolation('antialiased')
        self.fig.savefig(stem.with_suffix('.png'), dpi=PNG_DPI)
        self.fig.set_dpi(PNG_DPI)
        self.fig.canvas.draw()
        png = np.asarray(Image.open(stem.with_suffix('.png')).convert('RGB'))
        covered = np.zeros(png.shape[:2], bool)
        for t in self.tags:
            bb = t.get_bbox_patch().get_window_extent()
            covered[png.shape[0] - int(np.ceil(bb.y1)) - 2:png.shape[0] - int(bb.y0) + 2,
                    int(bb.x0) - 2:int(np.ceil(bb.x1)) + 2] = True
        plt.close(self.fig)
        for x0, y0, f, img in self.exact:
            big = np.kron(img, np.ones((f, f, 1), dtype=img.dtype))
            h, w = big.shape[:2]
            win = (slice(y0 + INSET, y0 + h - INSET), slice(x0 + INSET, x0 + w - INSET))
            keep = ~covered[win]
            if keep.mean() < 0.8 or not np.array_equal(png[win][keep], big[INSET:-INSET, INSET:-INSET][keep]):
                raise SystemExit(f'{stem.name}: a panel at ({x0}, {y0}) is not an exact {f}x enlargement of its source')
        DISPLAY[stem.name] = list(self.images.values())
        return [stem.with_suffix('.pdf'), stem.with_suffix('.png')]


def role_of(geo: dict) -> dict:
    r = geo['roles']
    return {o: 'mover' if o == r['mover'] else 'reference' if o == r['reference'] else 'other'
            for o in geo['legend_numbers']}


def legend_key(geo: dict) -> list[tuple[str, str]]:
    numbers, role = geo['legend_numbers'], role_of(geo)
    parts = []
    for o in sorted(numbers, key=numbers.get):
        parts += [(f"{numbers[o]} = {NAME[o]}" + (f" ({role[o]})" if role[o] != 'other' else ''), ROLE[role[o]]),
                  ('   ', MUTED)]
    return parts[:-1]


def label_value(v, numbers: dict) -> str:
    v = str(v)
    inv = {n: o for o, n in numbers.items()}
    return f"{v} ({SHORT[inv[int(v)]]})" if v.isdigit() and int(v) in inv else v.replace('_', ' ')


def labeler_names(lab: dict) -> dict:
    expect = {'a': 'A', 'b': 'B', 'adjudicated': 'adjudicator'}
    for k, who in expect.items():
        if lab[k]['raw']['labeler'] != who:
            raise SystemExit(f"unexpected labeler {lab[k]['raw']['labeler']!r} for {k}")
    return {'a': f"A ({VLM_SHORT[lab['a']['raw']['model']]})", 'b': f"B ({VLM_SHORT[lab['b']['raw']['model']]})",
            'adjudicated': 'Adjudicated'}


def label_table(e: dict, x: float, top: float, width: float) -> tuple[list, float]:
    """Drawing operations for the label table, and the y of its bottom edge."""
    lab, numbers = e['labels'], e['geometry']['legend_numbers']
    disputed = set(lab['adjudicated']['raw'].get('disputed') or [])
    names, ops = labeler_names(lab), []
    heads = [h + ('†' if f in disputed else '') for h, f, _ in FIELDS]
    rows = [(names[k], [label_value(lab[k]['row'][f], numbers) for _, f, _ in FIELDS]) for k in LABEL_KEYS]
    derived = [lab['derived']['row'][f].replace('_', ' ') if f else '–' for _, _, f in FIELDS]
    columns = [[r[0] for r in rows] + ['Derived']] + [heads[j].split('\n') + [r[1][j] for r in rows] + [derived[j]]
                                                      for j in range(len(FIELDS))]
    for FS in np.arange(8.8, 7.55, -0.1).round(1):
        widths = [max(text_size(s, fontsize=FS, weight='bold')[0] for s in c) for c in columns]
        gap = (width - sum(widths)) / len(FIELDS)
        if gap >= 0.12:
            break
    else:
        raise SystemExit(f"{e['model']}: label table does not fit in {width:.2f} in")
    for line in run_lines(legend_key(e['geometry']), width, fontsize=FS, weight='bold'):
        ops.append(('run', (x, top, line), dict(fontsize=FS, weight='bold')))
        top += 0.20
    top += 0.10
    cx = [x]
    for w in widths[:-1]:
        cx.append(cx[-1] + w + gap)
    for j, h in enumerate(heads):
        ops.append(('text', (cx[j + 1], top, h), dict(fontsize=FS - 0.4, color=MUTED, linespacing=1.05)))
    top += 0.40
    ops.append(('rule', (x, x + width, top - 0.06), {}))
    for name, vals in rows:
        ops.append(('text', (cx[0], top, name), dict(fontsize=FS, weight='bold', color=EXEC)))
        for j, (v, (_, f, _)) in enumerate(zip(vals, FIELDS)):
            ops.append(('text', (cx[j + 1], top, v), dict(fontsize=FS, color=EXEC,
                                                          weight='bold' if f in disputed else 'normal')))
        top += 0.215
    ops.append(('rule', (x, x + width, top - 0.045), {}))
    ops.append(('text', (cx[0], top, 'Derived'), dict(fontsize=FS, style='italic', color=MUTED)))
    for j, v in enumerate(derived):
        ops.append(('text', (cx[j + 1], top, v), dict(fontsize=FS, style='italic', color=MUTED)))
    top += 0.215
    if disputed:
        note = wrap(f"† A and B disagreed on this field; the adjudicator "
                    f"({VLM_SHORT[lab['adjudicated']['raw']['model']]}) chose the value shown.", width, fontsize=8.2)
        ops.append(('text', (x, top + 0.06, note), dict(fontsize=8.2, color=MUTED)))
        top += 0.06 + text_size(note, fontsize=8.2)[1]
    return ops, top


def example_figure(e: dict, d: dict) -> list[Path]:
    req, geo, crop, lab = e['request'], e['geometry'], e['crop'], e['labels']
    pre, n, ri = req['pre_tick'], req['n_executed'], req['request_index']
    cam, cols, raw = geo['chosen_camera'], d['cols'], d['raw']
    cell, cells = e['camera_cell'][cam], e['camera_cell'].values()
    cell_w, cell_h = cell['cols'][1] - cell['cols'][0] + 1, cell['rows'][1] - cell['rows'][0] + 1
    comp_w, comp_h = max(c['cols'][1] for c in cells) + 1, max(c['rows'][1] for c in cells) + 1
    M, CW, PW, GAP = 0.08, 3.20, 1.28, 0.06
    TW, CH, PH = FIG_W - 2 * M, CW * raw.shape[0] / raw.shape[1], PW * crop['h'] / crop['w']
    RX = M + CW + 0.20
    RW = FIG_W - M - RX
    GX = (FIG_W - len(cols) * PW - (len(cols) - 1) * GAP) / 2
    names = labeler_names(lab)
    sub = dict(fontsize=9.2, color=MUTED)

    title = f"{e['model_name']}: forecast and execution of the same {n}-action chunk"
    tsize = fit([title], TW, 12.5, 11, weight='bold')
    ids = [wrap(SEP.join([f"Episode {e['episode_id']}", f"annotation packet {e['annotation_id']}",
                          f"request {ri} (chunk {ri + 1})", f"seed {req['seed']}"]), TW, SEP, fontsize=9.2),
           wrap(f"Instruction: “{e['instruction']}”", TW, fontsize=9.2),
           wrap(SEP.join([f"Request input: tick {pre}, t = {req['t_start']:.3f} s",
                          f"{n} actions executed at ticks {pre}–{pre + n - 1}",
                          f"after the last: tick {pre + n}, t = {req['t_end']:.3f} s"]), TW, SEP, fontsize=9.2),
           wrap(f"Exterior camera {cam} = rows {cell['rows'][0]}–{cell['rows'][1]}, columns {cell['cols'][0]}–"
                f"{cell['cols'][1]} of the {comp_w}×{comp_h} policy input", TW, fontsize=9.2)]
    ctx_title, tab_title = f"Initial observation: request-{ri} input, tick {pre}", 'Original VLM labels of this forecast'
    hsize = min(fit([ctx_title], CW, 10, 8.6, weight='bold'), fit([tab_title], RW, 10, 8.6, weight='bold'))
    h1 = [f"k = {c['k']}  ·  +{c['dt']:.2f} s" for c in cols]
    h2 = [f"tick {c['tick']}  ·  t = {c['t']:.3f} s" for c in cols]
    s1, s2 = fit(h1, PW - 0.05, 9.4, 7.5, weight='bold'), fit(h2, PW - 0.05, 8.6, 7.2)
    bands = ([('PREDICTED', PRED), (f"   generated frame k of the request-{ri} forecast", MUTED)],
             [('EXECUTED', EXEC), (f"   simulator frame at tick {pre} + k, after k of the {n} executed actions", MUTED)])
    bsize = fit([''.join(s for s, _ in b) for b in bands], FIG_W - GX - M, 9.4, 8, weight='bold')

    flags = {k: ' / '.join(lab[k]['row'][f] for f in FLAGS) for k in LABEL_KEYS}
    flags = (f"A, B and the adjudication all answer {flags['a']} for possible release / missing object / "
             f"hallucinated object" if len(set(flags.values())) == 1
             else 'possible release / missing object / hallucinated object: '
             + '; '.join(f"{names[k]} {flags[k]}" for k in LABEL_KEYS))
    vlm = {k: VLM_NAMES[lab[k]['raw']['model']] for k in LABEL_KEYS}
    foot = [f"All ten panels show the same {crop['w']}×{crop['h']}-pixel window (dashed box) of the {cell_w}×{cell_h} "
            f"exterior view in the composite given to the policy; source pixels are not resampled. Column k pairs "
            f"generated frame k with the executed frame after k actions (tick {pre} + k), the nominal 15 Hz mapping "
            f"defined by the model and export code. Generated frame 0 is the model's reconstruction of its input. The "
            f"mapping does not show that the predicted motion keeps the executed pace.",
            f"Labelers A ({vlm['a']}) and B ({vlm['b']}) saw only legend.png and generated frames k = "
            f"{', '.join(map(str, e['packet']['vlm_frames_shown']))}, never the instruction or the execution; "
            f"disagreements went to an adjudicator ({vlm['adjudicated']}) with the same images. {flags}. Derived: the "
            f"labels mapped to scene roles after unblinding.",
            f"Example chosen by the manifest rule “{e['selection_rule']}” and kept regardless of what it shows."]
    if e['frame0']['composite_rows_present'] < comp_h:
        foot.append(f"{e['model_name']} decodes rows 0–{e['frame0']['composite_rows_present'] - 1} of the {comp_h}-row "
                    f"composite; the missing rows lie outside this window.")
    foot = [wrap(p, TW, fontsize=8.2) for p in foot]

    ops, tab_bottom = label_table(e, RX, 0.0, RW)
    y, height = stack([('title', text_size(title, fontsize=tsize, weight='bold')[1], 0.07)]
                      + [(f'id{i}', text_size(s, **sub)[1], 0.03 if i < len(ids) - 1 else 0.14) for i, s in enumerate(ids)]
                      + [('ctxtitle', text_size(ctx_title, fontsize=hsize, weight='bold')[1], 0.12),
                         ('ctx', max(CH, tab_bottom + 0.03), 0.20),
                         ('colhdr1', text_size(h1[0], fontsize=s1, weight='bold')[1], 0.035),
                         ('colhdr2', text_size(h2[0], fontsize=s2)[1], 0.11),
                         ('band1', text_size('Ag', fontsize=bsize, weight='bold')[1], 0.05), ('row1', PH, 0.10),
                         ('band2', text_size('Ag', fontsize=bsize, weight='bold')[1], 0.05), ('row2', PH, 0.16)]
                      + [(f'foot{i}', text_size(p, fontsize=8.2, linespacing=1.3)[1], 0.10) for i, p in enumerate(foot)],
                      top=0.08)
    y['ids'] = [y[f'id{i}'] for i in range(len(ids))]
    S = Canvas(height)

    S.text(M, y['title'], title, fontsize=tsize, weight='bold')
    for top, s in zip(y['ids'], ids):
        S.text(M, top, s, **sub)
    S.text(M, y['ctxtitle'], ctx_title, fontsize=hsize, weight='bold')
    S.text(RX, y['ctxtitle'], tab_title, fontsize=hsize, weight='bold')

    ax = S.ax(M, y['ctx'], CW, CH)
    r = CONTEXT_REDUCE
    shown = raw.reshape(raw.shape[0] // r, r, raw.shape[1] // r, r, 3).mean((1, 3)).round().astype(np.uint8)
    S.image(ax, shown, exact=False, name=f"{rel(local(e['files']['compact']['raw_camera_request_tick']))} "
                                          f"({raw.shape[1]}x{raw.shape[0]}) as {r}x{r} means",
            extent=(-0.5, raw.shape[1] - 0.5, raw.shape[0] - 0.5, -0.5))
    x0, y0, x1, y1 = crop['raw_camera_box_px']
    for ec, lw, ls in (('black', 2.4, '-'), ('white', 1.2, (0, (4, 2)))):
        ax.add_patch(Rectangle((x0 - .5, y0 - .5), x1 - x0, y1 - y0, fill=False, ec=ec, lw=lw, ls=ls,
                               alpha=.45 if ec == 'black' else 1))
    centres = geo['camera_rule'][cam]['centres_raw_px']
    mid, role = np.mean(list(centres.values()), 0), role_of(geo)
    for obj, (u, v) in centres.items():
        ax.add_patch(Circle((u, v), 34, fill=False, ec=ROLE[role[obj]], lw=1.5))
        dv = (np.array([u, v]) - mid) / (np.linalg.norm(np.array([u, v]) - mid) or 1)
        ax.text(u + 68 * dv[0], v + 68 * dv[1], str(geo['legend_numbers'][obj]), ha='center', va='center', fontsize=8,
                weight='bold', color='white', bbox=dict(boxstyle='circle,pad=0.2', fc=ROLE[role[obj]], ec='white', lw=.6))
    note = f"render {raw.shape[1]}×{raw.shape[0]}, shown at 1/{r}; the policy receives {cell_w}×{cell_h}"
    ax.text(.012, .025, note, transform=ax.transAxes, fontsize=fit([note], CW - 0.12, 7.2, 6.4), color='white',
            va='bottom', bbox=dict(boxstyle='round,pad=0.25', fc='black', ec='none', alpha=.6))
    S.draw([(kind, (a[0], a[1] + y['ctx'] + 0.03) + a[2:], kw) if kind != 'rule' else (kind, (a[0], a[1], a[2] + y['ctx'] + 0.03), kw)
            for kind, a, kw in ops])

    for key, parts in zip(('band1', 'band2'), bands):
        S.run(GX, y[key], parts, fontsize=bsize, weight='bold')
    for j, c in enumerate(cols):
        x = GX + j * (PW + GAP)
        S.text(x + PW / 2, y['colhdr1'], h1[j], ha='center', fontsize=s1, weight='bold')
        S.text(x + PW / 2, y['colhdr2'], h2[j], ha='center', fontsize=s2, color=MUTED)
        for row, img, color, tag in (('row1', c['pred'], PRED, 'decoded input'), ('row2', c['exec'], EXEC, 'model input')):
            a = S.ax(x, y[row], PW, PH)
            S.image(a, img, exact=True, name=f"{crop['w']}x{crop['h']} display window of the predicted and executed "
                                             f"exterior cells (rows {crop['y0']}-{crop['y0'] + crop['h'] - 1}, "
                                             f"cols {crop['x0']}-{crop['x0'] + crop['w'] - 1})")
            for s in a.spines.values():
                s.set_edgecolor(color), s.set_linewidth(1.4)
            if c['k'] == 0:
                S.tag(a, tag, color)
    for i, p in enumerate(foot):
        S.text(M, y[f'foot{i}'], p, fontsize=8.2, color=MUTED, linespacing=1.3)
    return S.save(OUT / f"rev_forecast_example_{SLUG[e['model']]}")


def packet_figure(e: dict, d: dict) -> list[Path]:
    req, pk, geo = e['request'], e['packet'], e['geometry']
    pre, ri, n = req['pre_tick'], req['request_index'], pk['packet_json']['frames']
    legend, sheet, sheet_k = d['legend'], d['sheet'], pk['contact_sheet_frames']
    rows_n, cols_n = -(-len(sheet_k) // 4), 4
    th, tw = sheet.shape[0] // rows_n, sheet.shape[1] // cols_n
    if (th * rows_n, tw * cols_n) != sheet.shape[:2] or sheet_k != list(range(0, n, 4)):
        raise SystemExit(f"{e['model']}: unexpected contact-sheet layout")
    lay = pk['canonical_layout']
    frame_h, frame_w = lay['exterior_rows'][1] + 1, 2 * tw
    M, SW = 0.08, 4.40
    TW = FIG_W - 2 * M
    LH, SH = TW * legend.shape[0] / legend.shape[1], SW * sheet.shape[0] / sheet.shape[1]
    NX = M + SW + 0.18
    NW = FIG_W - M - NX
    sub = dict(fontsize=9.2, color=MUTED)
    nb = geo['legend_numbers']

    title = f"{e['model_name']}: original annotation packet {e['annotation_id']}"
    tsize = fit([title], TW, 12.5, 11, weight='bold')
    ids = [wrap(SEP.join([f"Episode {e['episode_id']}", f"request {ri}, input at tick {pre} (t = {req['t_start']:.3f} s)",
                          f"{n} generated frames, nominally 15 Hz", 'prediction only']), TW, SEP, fontsize=9.2),
           wrap(f"Instruction (hidden from the labelers): “{e['instruction']}”", TW, fontsize=9.2)]
    leg_title = f"legend.png, as given to the VLM labelers (shown at 1/2 resolution)"
    sheet_title = 'contact_sheet.png, the original human-review summary (not shown to the labelers)'
    hsize = fit([leg_title, sheet_title], TW, 10, 8.6, weight='bold')
    key = run_lines([("Episode's first observation (tick 0, before any action).", MUTED), ('   ', MUTED)]
                    + legend_key(geo), TW, fontsize=8.6)
    same = len({x['packet']['sha256']['legend.png'] for x in V['examples']}) == 1
    legnote = wrap(f"Yellow circles and numbers mark the objects; each number is drawn above and to the right of its "
                   f"circle, and the direction arrows are drawn over the numbers. In the left view the arrow labels "
                   f"cover {nb['banana']} and {nb['rubiks_cube']}, and the bowl's {nb['bowl']} falls beside the "
                   f"banana; in the right view the cube's {nb['rubiks_cube']} falls on the banana's circle."
                   + (' Both examples have byte-identical legends'
                      + (' (same restored initial state)' if SHARED_START else '') + '.' if same else ''),
                   TW, fontsize=8.6)
    notes = [f"Tiles: generated frames k = 0, 4, …, {n - 1} of the request-{ri} forecast, every second pixel; in "
             f"each, the wrist view is above the left | right exterior views.",
             f"+s is the nominal time after the request input: t = {req['t_start']:.3f} s + k/15.",
             f"The labelers instead saw legend.png and frames k = {', '.join(map(str, pk['vlm_frames_shown']))} of "
             f"forecast.mkv at {frame_w}×{frame_h}.",
             f"Prediction only: nothing here is paired with the execution. Frames "
             f"{', '.join(map(str, V['selected_k'][:-1]))} and {V['selected_k'][-1]} appear with the matching "
             f"executed frames in the companion figure, cut from the original future array."]
    if lay['exterior_resampled']:
        notes.append(f"The packet layout stretches this model's {lay['exterior_source_rows']} decoded exterior rows to "
                     f"{lay['exterior_rows'][1] - lay['exterior_rows'][0] + 1} (one layout for all models).")
    notes = [wrap(s, NW, fontsize=8.2) for s in notes]
    notes_h = sum(text_size(s, fontsize=8.2, linespacing=1.25)[1] + 0.11 for s in notes) - 0.11

    key_h = text_size('Ag', fontsize=8.6)[1]
    y, _ = stack([('title', text_size(title, fontsize=tsize, weight='bold')[1], 0.07)]
                 + [(f'id{i}', text_size(s, **sub)[1], 0.03 if i < len(ids) - 1 else 0.14) for i, s in enumerate(ids)]
                 + [('legtitle', text_size(leg_title, fontsize=hsize, weight='bold')[1], 0.12), ('leg', LH, 0.04),
                    ('legcams', key_h, 0.08)]
                 + [(f'key{i}', key_h, 0.04) for i in range(len(key))]
                 + [('legnote', text_size(legnote, fontsize=8.6)[1], 0.16),
                    ('sheettitle', text_size(sheet_title, fontsize=hsize, weight='bold')[1], 0.12),
                    ('sheet', max(SH, notes_h), 0.08)], top=0.08)
    S = Canvas(y['sheet'] + max(SH, notes_h) + 0.08)
    S.text(M, y['title'], title, fontsize=tsize, weight='bold')
    for i, s in enumerate(ids):
        S.text(M, y[f'id{i}'], s, **sub)

    S.text(M, y['legtitle'], leg_title, fontsize=hsize, weight='bold')
    ax = S.ax(M, y['leg'], TW, LH)
    S.image(ax, legend.reshape(legend.shape[0] // 2, 2, legend.shape[1] // 2, 2, 3).mean((1, 3)).round()
            .astype(np.uint8), exact=False, name=f"legend.png ({legend.shape[1]}x{legend.shape[0]}) as 2x2 means")
    for xx, s in ((M + TW / 4, 'left exterior camera'), (M + 3 * TW / 4, 'right exterior camera')):
        S.text(xx, y['legcams'], s, ha='center', fontsize=8.6, color=MUTED)
    for i, line in enumerate(key):
        S.run(M, y[f'key{i}'], line, fontsize=8.6)
    S.text(M, y['legnote'], legnote, fontsize=8.6, color=MUTED)

    S.text(M, y['sheettitle'], sheet_title, fontsize=hsize, weight='bold')
    ax = S.ax(M, y['sheet'], SW, SH)
    S.image(ax, sheet, exact=False, name=f"contact_sheet.png ({sheet.shape[1]}x{sheet.shape[0]})")
    for i in range(rows_n * cols_n):
        r, c = divmod(i, cols_n)
        if i < len(sheet_k):
            ax.text(c * tw + 8, r * th + 8, f"k = {sheet_k[i]}  ·  +{sheet_k[i] / 15:.2f} s", fontsize=6.8,
                    color='white', va='top', bbox=dict(boxstyle='round,pad=0.18', fc=PRED, ec='none', alpha=.88))
        else:
            ax.text(c * tw + tw / 2, r * th + th / 2, 'empty\npadding tile', ha='center', va='center', fontsize=7.4,
                    color='#9aa3ab')
    for r in range(1, rows_n):
        ax.axhline(r * th - .5, color='white', lw=.6)
    for c in range(1, cols_n):
        ax.axvline(c * tw - .5, color='white', lw=.6)
    ny = y['sheet']
    for s in notes:
        S.text(NX, ny, s, fontsize=8.2, color=MUTED, linespacing=1.25)
        ny += text_size(s, fontsize=8.2, linespacing=1.25)[1] + 0.11
    return S.save(OUT / f"rev_forecast_packet_{SLUG[e['model']]}")


def citations(model: str) -> list[dict]:
    keep = ('path', 'line', 'claim', 'line_text', 'file_sha256', 'tree_head', 'unmodified_at_head')
    return [{k: c[k] for k in keep} for c in V['source_citations'] if c['model'] == model]


def commands() -> dict:
    out, script = V['out'], V['argv'][0]
    media = rel(MEDIA)
    stage = ' '.join(['experiments/__init__.py', 'experiments/robolab_workshop', script,
                      rel(HERE / 'forecast_packet_retrieval_manifest.json')])
    return {
        'note': ('The figures were built from the committed forecast_media/ copy. Stage, extract, and copy reproduce '
                 'that copy from the commit that adds these files (the original run staged the same files with an '
                 'equivalent tar pipe; staged code was identical to the repository, see verification.json). '
                 'extract_on_pod is the recorded run and overwrites its output directory; reverify_on_pod instead '
                 'extracts into a scratch directory without the sync videos and checks every compact file against '
                 'the recorded output by SHA-256. Its verification.json then differs from the committed one only in argv, run times, '
                 'output paths and the absent sync-video entries; every check, hash and value is identical (re-run '
                 '2026-10-01 from the commit that adds these files).'),
        'stage_code_on_pod': (f"git archive --format=tar HEAD {stage} | kubectl exec -i -n {NS} {POD} -- sh -c "
                              f"'rm -rf /tmp/fm_run && mkdir -p /tmp/fm_run/repo && tar -C /tmp/fm_run/repo -xf -'"),
        'extract_on_pod': (f"kubectl exec -n {NS} {POD} -- sh -c 'cd /tmp/fm_run/repo && {ENV_PY} "
                           f"{' '.join(V['argv'])}'"),
        'reverify_on_pod': (f"kubectl exec -n {NS} {POD} -- sh -c 'cd /tmp/fm_run/repo && {ENV_PY} {script} "
                            f"--out /tmp/fm_run/reverify && cd /tmp/fm_run/reverify && sha256sum E3/*.png E3/packet/* "
                            f"F3/*.png F3/packet/* | (cd {out} && sha256sum -c --quiet -) && echo COMPACT_FILES_IDENTICAL'"),
        'copy_compact_subset': (f"kubectl exec -n {NS} {POD} -- sh -c 'cd {out} && tar -cf - verification.json "
                                f"E3/*.png E3/packet F3/*.png F3/packet' | tar -C {media} -xf -"),
        'build_figures_and_provenance': f"python {rel(Path(__file__))}",
        'cleanup_pod': f"kubectl exec -n {NS} {POD} -- rm -rf /tmp/fm_run",
        'extraction_run': {k: V[k] for k in ('argv', 'started_utc', 'finished_utc', 'host', 'python', 'numpy', 'pillow',
                                             'torch', 'ffmpeg', 'ffmpeg_path')} | {'cwd': '/tmp/fm_run/repo',
                                                                                   'interpreter': ENV_PY},
    }


def example_record(e: dict, figures: list[Path]) -> dict:
    req, art, geo, fc, pk = e['request'], e['artifacts'], e['geometry'], e['files']['compact'], e['packet']
    cam, cell = geo['chosen_camera'], e['camera_cell'][geo['chosen_camera']]
    hv = e['frame0']['composite_rows_present']
    attempt = {k: e[k] for k in ('attempt_id', 'attempt_dir', 'complete_json', 'result_sha256', 'scene_id',
                                 'state_slot', 'goal_id', 'prompt_id', 'form', 'lane', 'prompt_sha256')}
    mapping = []
    for m in e['frame_mapping']:
        k, tick, cp = m['k'], m['tick'], e['crop_pixels'][str(m['k'])]
        mapping.append(m | {
            'predicted_source': f"{req['future']['uri']} frame {k}, rows {cell['rows'][0]}-{hv - 1}, "
                                f"cols {cell['cols'][0]}-{cell['cols'][1]}",
            'executed_source': f"{art['exec_composite.mkv']['path']} decoded frame {tick}, rows "
                               f"{cell['rows'][0]}-{cell['rows'][1]}, cols {cell['cols'][0]}-{cell['cols'][1]}",
            'predicted_png': rel(local(fc[f'pred_cell_k{k:02d}'])), 'executed_png': rel(local(fc[f'exec_cell_tick{tick:03d}'])),
            'window_pixels_sha256': {'predicted': cp['pred_crop_pixels_sha256'], 'executed': cp['exec_crop_pixels_sha256']},
            'window_psnr_db_predicted_vs_executed': cp['psnr_db_pred_vs_exec']})
    lag = e['lag_diagnostic']
    return {
        'model': e['model'], 'model_name': e['model_name'], 'episode_id': e['episode_id'],
        'annotation_id': e['annotation_id'], 'instruction': e['instruction'], 'selection_rule': e['selection_rule'],
        'attempt': attempt, 'initial_state': e['initial_state'],
        'request': {k: v for k, v in req.items() if k != 'effective_prompt'} | {'neighbours': e['neighbour_requests']},
        'effective_prompt': req.get('effective_prompt'),
        'server': {'call': e['server_call'], 'receipt': e['server_receipt']},
        'sources': {
            'execution_recording': art['exec_composite.mkv'] | {
                'frame_index': 'decoded frame i is the composite observed at simulator tick i (15 Hz); every decoded '
                               'frame matches stream_frame_hashes.json'},
            'request_metadata': art['requests.jsonl'], 'request_input': art['requests/r01_input.npz'],
            'next_request_input': art['requests/r02_input.npz'], 'generated_future': req['future'],
            'actions': art['actions.npz'], 'stream_frame_hashes': art['stream_frame_hashes.json'],
            'states': art['states.jsonl.gz'], 'first_observation': art['first_observation.npz'],
            'other_attempt_artifacts': {k: art[k] for k in ('intent.json', 'initial_state.json', 'exec_head_camera.mkv',
                                                            'exec_viewport.mkv')},
            'packet': {nm: {'path': pk['paths'][nm], 'sha256': pk['sha256'][nm], 'bytes': pk['bytes'][nm]}
                       for nm in pk['paths']},
            'annotation_key': {'path': pk['key_path'], 'row': pk['key']},
        },
        'packet_layout': {k: pk[k] for k in ('canonical_layout', 'contact_sheet_frames', 'vlm_frames_shown',
                                             'legend_source')},
        'camera': {
            'chosen': cam,
            'rule': ('exterior camera in which the mover and reference both project inside the frame at the request '
                     'tick (simulator object boxes), preferring the larger mover-reference separation in pixels'),
            'per_camera': geo['camera_rule'], 'composite_cells': e['camera_cell'], 'legend_numbers': geo['legend_numbers'],
            'roles': geo['roles'], 'object_positions_m': geo['object_positions_m'],
            'objects_union_box_raw_px': geo['objects_union_box_raw_px'],
            'objects_union_box_cell_px': geo['objects_union_box_cell_px'], 'display_window': e['crop']},
        'frame_mapping': mapping,
        'frame0_reconstruction': e['frame0'],
        'lag_diagnostic': {'note': lag['note']} | {
            c: {'mean_abs_best_minus_k': lag[c]['mean_abs_best_minus_k'],
                'best_exec_offset_per_k': lag[c]['best_exec_offset_per_k']} for c in ('left', 'wrist')},
        'labels': {t: {'row': v['row'], 'file': v['file']} | (
            {'raw_file': v['raw_file'], 'labeler_model': VLM_NAMES[v['raw']['model']], 'disputed': v['raw']['disputed'],
             'observations': v['raw']['observations']} if 'raw' in v else {}) for t, v in e['labels'].items()},
        'committed_media': {k: {'path': rel(local(v)), 'sha256': v['file_sha256']} | (
            {'pixels_sha256': v['pixels_sha256'], 'shape': v['shape']} if 'pixels_sha256' in v else {})
            for k, v in fc.items()},
        'cluster_only_media': e['files']['cluster_only'],
        'model_source_citations': citations(e['model']),
        'checks': {'n': sum(c['example'] == e['model'] for c in V['checks']),
                   'all_pass': all(c['pass'] for c in V['checks'] if c['example'] == e['model']),
                   'names': [c['check'] for c in V['checks'] if c['example'] == e['model']]},
        'figures': [{'path': rel(p), 'sha256': sha256(p), 'bytes': p.stat().st_size} for p in figures],
    }


def lag_summary() -> str:
    """Wording for the supporting lag diagnostic, read from verification.json."""
    parts, late = [], None
    for e in V['examples']:
        lag, m = e['lag_diagnostic'], e['model_name']
        left, wrist = lag['left']['best_exec_offset_per_k'], lag['wrist']['best_exec_offset_per_k']
        n = len(left) - 1
        late = range(20, n + 1)
        # The qualitative sentence below must stay true of the data.
        if not (left[14] >= 10 and max(left[k] for k in late) - min(left[k] for k in late) <= 5):
            raise SystemExit(f'{m}: left-camera lag no longer rises then plateaus; revise lag_summary')
        rng = lambda xs: f'{min(xs[k] for k in late)}-{max(xs[k] for k in late)}'
        parts.append(f"{m}: for k = {late[0]}-{n} the best offset is {rng(left)} (left) and {rng(wrist)} (wrist); "
                     f"at k = {n} it is {left[n]} (left) and {wrist[n]} (wrist); mean |best - k| is "
                     f"{lag['left']['mean_abs_best_minus_k']:.1f} (left) and {lag['wrist']['mean_abs_best_minus_k']:.1f} "
                     f"(wrist)")
    return ('Whether the generated content proceeds at the nominal 15 Hz pace is not established. A supporting '
            'diagnostic finds, for each generated frame k, the executed frame of the chunk (offset 0-32) with the '
            'lowest mean squared error in the same camera cell. For the left exterior camera the best offset rises '
            'with k for roughly the first 15 frames and then plateaus; the wrist-camera offsets are noisier. '
            + '. '.join(parts) + '. A left-camera plateau fits a forecast that slows or stops relative to the '
            'execution, and equally a forecast whose later content matches no executed frame well; prediction '
            'errors confound the diagnostic, so it is inconclusive and not a timing measurement.')


def alignment() -> dict:
    req_ev, cam_ev, time_ev, rows_ev = [], [], [], []
    for e in V['examples']:
        f0, sc, q, m = e['frame0'], e['server_call'], e['request'], e['model_name']
        pre, n, ri = q['pre_tick'], q['n_executed'], q['request_index']
        cell = e['camera_cell'][e['geometry']['chosen_camera']]
        req_ev += [f"{m}: packet key row {e['annotation_id']} names episode {e['episode_id']}, request {ri}, and the "
                   f"future file hash {q['future']['sha256'][:12]}…; requests.jsonl request {ri} has pre_tick {pre}, "
                   f"{n} executed actions, seed {q['seed']}, future {q['future_status']}.",
                   f"{m}: calls log {sc['calls_log']} line {sc['line']} (served index {sc['served_index']}) records "
                   f"the same input hash, returned-action hash, seed {sc['effective_seed']} and future file.",
                   f"{m}: executed commands for ticks {pre}-{pre + n - 1} equal the first {n} actions of the returned "
                   f"chunk; the executed frame at tick {pre} equals the request-{ri} input composite and the frame "
                   f"at tick {pre + n} equals the request-{ri + 1} input (pixel equality).",
                   f"{m}: forecast.mkv frames and contact_sheet.png re-derived from the same future array."]
        cam_ev.append(f"{m}: generated frame 0 vs. request input, PSNR same cell (wrist/left/right) "
                      f"{f0['psnr_db_vs_input']['wrist']:.1f}/{f0['psnr_db_vs_input']['left']:.1f}/"
                      f"{f0['psnr_db_vs_input']['right']:.1f} dB vs. swapped exterior cells "
                      f"{f0['psnr_db_swapped_cells']['pred_left_vs_input_right']:.1f}/"
                      f"{f0['psnr_db_swapped_cells']['pred_right_vs_input_left']:.1f} dB; best left-cell shift "
                      f"({f0['left_cell_shift']['best_dy']}, {f0['left_cell_shift']['best_dx']}) px; displayed cell "
                      f"rows {cell['rows'][0]}-{cell['rows'][1]}, cols {cell['cols'][0]}-{cell['cols'][1]}.")
        time_ev.append(f"{m}: states.jsonl.gz ticks are consecutive with t = index/15; window t = "
                       f"{q['t_start']:.4f}-{q['t_end']:.4f} s read from ticks {pre} and {pre + n}.")
        if f0['composite_rows_present'] < 540:
            rows_ev.append(f"{m} decodes {f0['composite_rows_present']} of the 540 composite rows (exterior-cell rows "
                           f"0-{f0['exterior_cell_rows_present'] - 1} of 180); the displayed window (cell rows "
                           f"{e['crop']['y0']}-{e['crop']['y0'] + e['crop']['h'] - 1}) lies inside the decoded region.")
    claims = {e['model_name']: '; '.join(c['claim'] for c in citations(e['model'])) for e in V['examples']}
    return {
        'request_and_chunk': {'status': 'verified for both examples', 'evidence': req_ev},
        'camera_view': {
            'status': 'verified: predicted and executed rows show the same exterior camera cell',
            'evidence': ['request composite rebuilt from the raw camera renders: wrist above [left | right]; '
                         'swapping the exterior cells does not reproduce it'] + cam_ev},
        'time': {
            'status': ('nominal mapping verified in model source and records: generated frame k <-> executed frame at '
                       'tick pre_tick + k (t = tick/15 s); generated frame 0 reconstructs the request input. The '
                       "worker's recorded future_frame_times agree but were not used as evidence."),
            'evidence': time_ev + [f"{m} source (file and line per example): {s}" for m, s in claims.items()]},
        'unresolved': [
            lag_summary(),
            'Generated frame 0 is a decoded reconstruction of the input, not the input itself.',
            ('FLUX 3 Action decodes with a non-causal video decoder, so each decoded frame, including frame 0, depends '
             'on the predicted latents.'),
            ('Executed frames show what the simulator rendered after the controller tracked the commanded actions; '
             'they are not a target the forecast was trained to reproduce pixel for pixel.')] + rows_ev + [
            'Only these two preselected packets were verified; nothing here establishes alignment for other packets.'],
        'observations': [
            ('legend.png is drawn on ' + ' / '.join(sorted({e['packet']['legend_source'] for e in V['examples']}))
             + (' and is byte-identical for both packets'
                + (' (both episodes start from the same restored state: equal state and first-observation hashes)'
                   if SHARED_START else '')
                if len({e['packet']['sha256']['legend.png'] for e in V['examples']}) == 1 else '')
             + '. experiments/robolab_workshop/annotation.py draw_legend writes each number above and to the right '
               'of its circle (u+34, v-60) and draws the direction arrows afterwards, over the numbers. In the left '
               'pane the "farther" marker and the "robot-left" label cover numbers 1 (banana) and 3 (cube), and the '
               'bowl\'s 2 falls just below the banana circle, nearer the banana than the bowl; in the right pane the '
               'cube\'s 3 falls on the banana\'s circle.'),
            ('VLM free-text observations misnumber objects in two of six labels (structured fields unaffected; all '
             'moving_object fields are 3, the cube): Cosmos3 Edge labeler A writes "1: red bowl, 2: banana", and the '
             'FLUX 3 Action adjudicator calls the cube "object 1" and the banana "object 3". Legend: 1 banana, 2 bowl, '
             '3 cube.'),
            ('Disputed fields: Cosmos3 Edge visible_final_relation (A none, B on_top_of; adjudicated none). FLUX 3 Action '
             'relation_object (A none, B 3 = the cube itself; adjudicated none).')],
    }


def write_provenance(built: dict) -> None:
    doc = {
        'generated_by': rel(Path(__file__)),
        'purpose': ('Provenance for the appendix figures pairing each preselected forecast with the execution of the '
                    'same request. Built only from existing recordings; no episode, policy inference, or VLM call.'),
        'build_environment': {'python': platform.python_version(), 'numpy': np.__version__,
                              'matplotlib': matplotlib.__version__, 'pillow': PIL.__version__},
        'extraction': {'script': V['generated_by'], 'script_sha256': sha256(REPO / V['generated_by']),
                       'verification_json': rel(MEDIA / 'verification.json'),
                       'verification_json_sha256': sha256(MEDIA / 'verification.json'),
                       'manifest': rel(HERE / 'forecast_packet_retrieval_manifest.json'),
                       'manifest_sha256_at_run': V['manifest']['sha256'], 'data_root': V['data_root'],
                       'cluster_output_dir': V['out'], 'n_checks': V['n_checks'],
                       'all_checks_pass': V['all_checks_pass'], 'failed_checks': V['failed_checks'],
                       'informational_checks': V['informational_checks']},
        'commands': commands(),
        'display': {'note': (f'PDF: every image is embedded at the listed source resolution without resampling. '
                             f'PNG ({PNG_DPI} dpi): the predicted and executed windows are exact integer pixel '
                             f'enlargements, checked at every build by comparing each panel with np.kron of its '
                             f'source, excluding a {INSET}-pixel inset under the panel border and the pixels under '
                             f'the k = 0 text tags; context images are antialiased.'),
                    'figures': DISPLAY},
        'alignment': alignment(),
        'examples': [example_record(e, built[e['model']]) for e in V['examples']],
    }
    PROVENANCE.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + '\n')


def main() -> None:
    hard = [c for c in V['checks'] if not c['informational']]
    if not V['all_checks_pass'] or V['failed_checks'] or len(hard) != V['n_checks'] or not all(c['pass'] for c in hard):
        raise SystemExit('verification.json reports failed or missing checks; refusing to build')
    OUT.mkdir(parents=True, exist_ok=True)
    built = {}
    for e in V['examples']:
        d = load(e)
        built[e['model']] = example_figure(e, d) + packet_figure(e, d)
    write_provenance(built)
    for figs in built.values():
        for p in figs:
            print(rel(p), p.stat().st_size, sha256(p)[:12])
    print(rel(PROVENANCE))


if __name__ == '__main__':
    main()
