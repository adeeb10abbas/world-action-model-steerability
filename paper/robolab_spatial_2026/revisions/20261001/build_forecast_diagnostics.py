"""Visualize released forecast measurements; no experiments or classifier refitting."""
from pathlib import Path
from collections import Counter
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[4]
ART = ROOT / 'artifacts/robolab_workshop_20260926'
OUT = ROOT / 'paper/robolab_spatial_2026/revision_assets'
OUT.mkdir(parents=True, exist_ok=True)
labels = [json.loads(l) for l in (ART/'analysis/forecast_labels_vlm.jsonl').read_text().splitlines()]
results = json.loads((ART/'results_vlm/results.json').read_text())
agreement = json.loads((ART/'results_vlm/vlm_agreement.json').read_text())['primary']
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11,'axes.spines.top':False,'axes.spines.right':False,'axes.titleweight':'bold','pdf.fonttype':42})
fig = plt.figure(figsize=(7.2,5.4), layout='constrained')
grid = fig.add_gridspec(2,2,height_ratios=[1.05,1])
axs = [fig.add_subplot(grid[0,0]),fig.add_subplot(grid[0,1]),fig.add_subplot(grid[1,:])]
fig.get_layout_engine().set(rect=(0,.14,1,.98),h_pad=.12,w_pad=.12)
# Counts are assignments, not independently verified observations.
cats=['goal','alternative_goal','not_goal','unknown']
names=['Requested relation','Other relation','Neither relation','Unknown']
counts=Counter(x['fc_visible_final_relation'] for x in labels)
y=np.arange(4)
axs[0].barh(y,[counts[k]/len(labels)*100 for k in cats],color=['#237b91','#bc672c','#66788a','#b1b7bf'])
for i,k in enumerate(cats): axs[0].text(counts[k]/len(labels)*100+1.5,i,str(counts[k]),va='center',fontsize=10.5)
axs[0].set_yticks(y,names); axs[0].invert_yaxis(); axs[0].set_xlim(0,86); axs[0].set_xlabel('VLM labels (%)'); axs[0].set_title('(a) Assigned relation',loc='left',pad=14)
keys=['moving_object','direction','visible_final_relation']; names=['Moving object','Direction','Final relation']
y=np.arange(3)
axs[1].barh(y,[agreement[k]['kappa'] for k in keys],color='#237b91')
for i,k in enumerate(keys): axs[1].text(agreement[k]['kappa']+.02,i,f"{agreement[k]['kappa']:.2f}",va='center',fontsize=10.5)
axs[1].set_yticks(y,names); axs[1].invert_yaxis(); axs[1].set_xlim(0,1); axs[1].set_xlabel("Cohen's κ"); axs[1].set_title('(b) VLM agreement',loc='left',pad=14)
rs=[results['E1']]+[results['E1_by_model'][k] for k in ['N3','E3','F3']]
y=np.arange(4); vals=np.array([r['delta'] for r in rs])*1000
axs[2].axvline(0,color='#9da3aa',lw=.8)
axs[2].scatter(vals,y,s=[34,22,22,22],color=['#1d3446','#697f90','#697f90','#697f90'],zorder=3)
ci=np.array(results['E1']['ci95_conditional_bootstrap'])*1000
axs[2].errorbar(vals[0],0,xerr=[[vals[0]-ci[0]],[ci[1]-vals[0]]],fmt='none',color='#1d3446',capsize=3)
axs[2].set_yticks(y,['Pooled','Nano','Edge','FLUX']); axs[2].invert_yaxis(); axs[2].set_xlim(-2,1.7); axs[2].set_xticks([-2,-1,0,1]); axs[2].set_xlabel('Brier improvement (×10⁻³)'); axs[2].set_title('(c) Added diagnostic value',loc='left',pad=14)
for ax in axs: ax.tick_params(labelsize=10.5); ax.grid(axis='x',color='#e8eaec',lw=.5); ax.set_axisbelow(True)
fig.text(.025,.085,'Automated labels. Agreement does not establish accuracy.',fontsize=10.5,color='#435463')
fig.text(.025,.042,'Positive values favor forecasts. The 95% interval is for the pooled estimate.',fontsize=10.5,color='#435463')
fig.savefig(OUT/'rev_forecast_diagnostics.pdf',bbox_inches='tight')
fig.savefig(OUT/'rev_forecast_diagnostics.png',dpi=180,bbox_inches='tight')
