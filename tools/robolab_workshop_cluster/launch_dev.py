import json, subprocess, sys
D='/Users/SZ5VJY/.copilot/session-state/5a07b8a7-a666-4758-8de5-62ca44621e3d/files/wams/docs/robolab-workshop-20260926'
R='/data/users/ali/rws-20260926'
rows=[json.loads(l) for l in open(f'{D}/planned_episodes.jsonl')]
dev=[r for r in rows if r['phase']=='development']
done={'RWS-N3-S1-D00-L-S'}
n3=[]
for s in ['S1','S2','S3','S4','S5']:
    e=[r for r in dev if r['model_id']=='N3' and r['scene_id']==s and r['episode_id'] not in done]
    e.sort(key=lambda r:r['order_in_block'])
    k=(len(e)+2)//3
    for i in range(k): n3.append((s,'N3',f"N3-{s}-D00",[r['episode_id'] for r in e[i::k]]))
srv=[(f'10.244.103.124:{p}','N3-ali-'+str(p) if p!=8600 else 'N3-ali') for p in range(8600,8604)]+\
    [(f'10.244.103.67:{p}',f'N3-aligroot-{p}') for p in range(8600,8604)]+\
    [(f'10.244.70.101:{p}',f'N3-alicollect-{p}') for p in range(8600,8604)]+\
    [(f'10.244.124.157:{p}',f'N3-alieval-{p}') for p in range(8600,8604)]
lanes=[(l,)+srv[i] for i,l in enumerate(n3)]
other=[(('S1','E3','E3-S1-D00',['RWS-E3-S1-D00-L-S']),'10.244.148.34:8600','E3-alia100e-0'),
       (('S5','E3','E3-S5-D00',['RWS-E3-S5-D00-LR-I']),'10.244.148.34:8601','E3-alia100e-1-8601'),
       (('S1','F3','F3-S1-D00',['RWS-F3-S1-D00-L-S']),'10.244.255.145:8600','F3-alia100f-0-cap1'),
       (('S5','F3','F3-S5-D00',['RWS-F3-S5-D00-LR-I']),'10.244.255.145:8602','F3-alia100f-2-cap1-8602')]
lanes+=other
gpus=[('alia40a-a40-2gpu',0),('alia40a-a40-2gpu',1)]+[(f'alia40{x}-a40-2gpu',g) for x in 'def' for g in (0,1)]+[(f'alia40{x}-a40-1gpu',0) for x in 'ghijklmnopqrstuv']
plan=[]
for i,((scene,model,block,eps),url,sname) in enumerate(lanes):
    pod,g=gpus[i]; lane=f"dev-{model}-{scene}-{i:02d}"
    plan.append(dict(lane=lane,pod='211247-'+pod,gpu=g,url=url,server=sname,model=model,scene=scene,block=block,episodes=eps))
json.dump(plan,open('/Users/SZ5VJY/.copilot/session-state/5a07b8a7-a666-4758-8de5-62ca44621e3d/files/dev_lanes.json','w'),indent=1)
if '--go' in sys.argv:
  for p in plan:
    cmd=(f"cd {R}; until grep -q READY dev/servers/{p['server']}/server.log; do sleep 5; done; "
         f"bash code/experiments/robolab_workshop/simrun.sh {p['gpu']} {R}/runs/_logs/{p['lane']}.log experiments.robolab_workshop.worker "
         f"--model {p['model']} --scene {p['scene']} --url http://{p['url']} --lane-id {p['lane']} --blocks {p['block']} "
         f"--episodes {','.join(p['episodes'])} --state-root {R}/states --out {R}/runs --robolab-root {R}/external/RoboLab-0aef241")
    full=f"setsid nohup bash -c '{cmd}' > /tmp/{p['lane']}.launch 2>&1 < /dev/null & echo {p['lane']} ok"
    print(subprocess.run(['kubectl','exec','-n','211247-prod',p['pod'],'-c',p['pod'],'--','bash','-c',full],capture_output=True,text=True).stdout.strip())
else:
  for p in plan: print(p['lane'],p['pod'],p['gpu'],p['server'],len(p['episodes']))
