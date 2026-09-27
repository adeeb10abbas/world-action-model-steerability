"""Launch one scripted-check process per next candidate (all its goals, fail-fast, charged to the 140 cap).

usage: launch_campaign.py [--go] [--skip S1-P03,...]
"""
import subprocess, sys
R = '/data/users/ali/rws-20260926'
NS = '211247-prod'
PY = '/data/users/ali/vla_wam/envs/robolab-v2-isaac50/bin/python'


def kx(pod, cmd):
    return subprocess.run(['kubectl', 'exec', '-n', NS, pod, '-c', pod, '--', 'bash', '-c', cmd],
                          capture_output=True, text=True)


out = kx('211247-alia40b-a40-2gpu', f'cd {R}/code; {PY} -m experiments.robolab_workshop.registry next --state-root {R}/states').stdout
skip = set(sys.argv[sys.argv.index('--skip') + 1].split(',')) if '--skip' in sys.argv else set()
jobs = []
for line in out.splitlines():
    parts = line.split()
    if parts and parts[0] in ('S1', 'S2', 'S3', 'S4', 'S5'):
        jobs += [(parts[0], pid) for pid in parts[1:] if pid not in skip]
gpus = [(f'211247-alia40{x}-a40-2gpu', g) for x in 'abcdef' for g in (0, 1)] + \
       [(f'211247-alia40{x}-a40-1gpu', 0) for x in 'ghijklmnopqrstuv']
slots = [(p, g, 'a') for p, g in gpus] + [(p, g, 'b') for p, g in gpus]
print(len(jobs), 'candidates:', jobs)
if '--go' in sys.argv:
    for (scene, pid), (pod, g, tag) in zip(jobs, slots):
        cmd = (f"RWS_CACHE_TAG={tag} bash {R}/code/experiments/robolab_workshop/simrun.sh {g} {R}/states/_logs/cand-{pid}.log "
               f"experiments.robolab_workshop.states scripted --scene {scene} --slot _candidates/{scene}/{pid} --charge "
               f"{'--goals R,L ' if scene == 'S2' else ''}"
               f"--state-root {R}/states --robolab-root {R}/external/RoboLab-0aef241")
        r = kx(pod, cmd)
        print(pid, pod, g, tag, r.returncode)
