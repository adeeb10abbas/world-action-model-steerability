"""Launch the confirmation lanes: one serialized policy server + one simulator worker chain per lane.

Blocks per model are partitioned once (LPT on expected block wall time); a lane runs its blocks in supplied
block order, chaining one worker invocation per consecutive same-scene run. Usage: launch_confirm.py [--go]
"""
import json, subprocess, sys, collections
D = '/Users/SZ5VJY/.copilot/session-state/5a07b8a7-a666-4758-8de5-62ca44621e3d/files'
R = '/data/users/ali/rws-20260926'
NS = '211247-prod'
EXPECT = {'S1': 245, 'S2': 240, 'S3': 320, 'S4': 315, 'S5': 150}


def kx(pod, cmd):
    return subprocess.run(['kubectl', 'exec', '-n', NS, pod, '-c', pod, '--', 'bash', '-c', cmd],
                          capture_output=True, text=True)


rows = [json.loads(l) for l in kx('211247-alia40b-a40-2gpu', f'cat {R}/release/bound_confirmation_episodes.jsonl').stdout.splitlines() if l.strip()]
order = {b['block_id']: i for i, b in enumerate(json.load(open(f'{D}/wams/docs/robolab-workshop-20260926/planned_blocks.json'))['blocks'])}
blocks = collections.OrderedDict()
for r in rows:
    b = blocks.setdefault(r['block_id'], {'block': r['block_id'], 'model': r['model_id'], 'scene': r['scene_id'], 'n': 0})
    b['n'] += 1
IP = {'ali': '10.244.103.124', 'aligroot': '10.244.103.67', 'alicollect': '10.244.70.101', 'alieval': '10.244.124.157',
      'alia100e': '10.244.148.34', 'alia100f': '10.244.255.145', 'alia100g': '10.244.227.174',
      'alia100p1': '10.244.143.130', 'alia100p2': '10.244.32.186', 'alia100p3': '10.244.212.193'}
servers = {'N3': [], 'E3': [], 'F3': []}
for h in ('ali', 'aligroot', 'alicollect', 'alieval'):
    for p in range(8600, 8604):
        name = ('N3-ali' if p == 8600 else f'N3-ali-{p}') if h == 'ali' else f'N3-{h}-{p}'
        servers['N3'].append((name, f'{IP[h]}:{p}'))
servers['E3'] += [('E3-alia100e-0', f"{IP['alia100e']}:8600"), ('E3-alia100e-1-8601', f"{IP['alia100e']}:8601"),
                  ('E3-alia100e-0-8602', f"{IP['alia100e']}:8602"), ('E3-alia100e-1-8603', f"{IP['alia100e']}:8603")]
servers['E3'] += [(f'E3-alia100e-{2 + (p - 8604) // 2}-{p}', f"{IP['alia100e']}:{p}") for p in range(8604, 8608)]
servers['E3'] += [(f'E3-alia100p2-1-{p}', f"{IP['alia100p2']}:{p}") for p in range(8602, 8607)]
servers['F3'] += [('F3-alia100f-0-cap1', f"{IP['alia100f']}:8600"), ('F3-alia100f-1-cap1-8601', f"{IP['alia100f']}:8601"),
                  ('F3-alia100f-2-cap1-8602', f"{IP['alia100f']}:8602"), ('F3-alia100f-3-cap1-8603', f"{IP['alia100f']}:8603")]
servers['F3'] += [(f'F3-alia100g-{g}-cap1-860{g}', f"{IP['alia100g']}:860{g}") for g in range(4)]
for h in ('alia100p1', 'alia100p2', 'alia100p3'):
    servers['F3'] += [(f'F3-{h}-0-cap1-{p}', f'{IP[h]}:{p}') for p in (8600, 8601)]

lanes = []
for m, srv in servers.items():
    bl = sorted((b for b in blocks.values() if b['model'] == m), key=lambda b: -EXPECT[b['scene']] * b['n'])
    load = [[0.0, []] for _ in srv]
    for b in bl:
        i = min(range(len(load)), key=lambda k: load[k][0])
        load[i][0] += EXPECT[b['scene']] * b['n']
        load[i][1].append(b)
    for (name, url), (t, bs) in zip(srv, load):
        if bs:
            lanes.append({'model': m, 'server': name, 'url': url, 'expect_s': t,
                          'blocks': sorted(bs, key=lambda b: order[b['block']])})
gpus = [(f'211247-alia40{x}-a40-2gpu', g) for x in 'abcdef' for g in (0, 1)] + \
       [(f'211247-alia40{x}-a40-1gpu', 0) for x in 'ghijklmnopqrstuv']
slots = gpus + gpus
lanes.sort(key=lambda l: -l['expect_s'])
plan = []
for i, l in enumerate(lanes):
    pod, g = slots[i]
    lane = f"conf-{l['server']}"
    runs, cur = [], None
    for b in l['blocks']:
        if cur and cur[0] == b['scene']:
            cur[1].append(b['block'])
        else:
            cur = (b['scene'], [b['block']])
            runs.append(cur)
    plan.append({**l, 'lane': lane, 'pod': pod, 'gpu': g, 'runs': runs,
                 'blocks': [b['block'] for b in l['blocks']]})
json.dump(plan, open(f'{D}/confirm_lanes.json', 'w'), indent=1)
if '--go' in sys.argv:
    for p in plan:
        steps = [f"until grep -q READY dev/servers/{p['server']}/server.log; do sleep 5; done"]
        for scene, bs in p['runs']:
            steps.append(f"RWS_CACHE_TAG={p['lane']} bash code/experiments/robolab_workshop/simrun.sh {p['gpu']} - "
                         f"experiments.robolab_workshop.worker --model {p['model']} --scene {scene} --url http://{p['url']} "
                         f"--lane-id {p['lane']} --blocks {','.join(bs)} --rows {R}/release/bound_confirmation_episodes.jsonl "
                         f"--state-root {R}/states --out {R}/runs --robolab-root {R}/external/RoboLab-0aef241 "
                         f"> {R}/runs/_logs/{p['lane']}-{scene}.log 2>&1")
        cmd = f"cd {R}; " + "; ".join(steps)
        full = f"setsid nohup bash -c '{cmd}' > {R}/runs/_logs/{p['lane']}.chain 2>&1 < /dev/null & echo {p['lane']} ok"
        print(kx(p['pod'], full).stdout.strip())
else:
    for p in plan:
        print(p['lane'], p['pod'], p['gpu'], round(p['expect_s'] / 3600, 2), 'h', p['blocks'])
    print(len(plan), 'lanes; max expected h', round(max(p['expect_s'] for p in plan) / 3600, 2))
