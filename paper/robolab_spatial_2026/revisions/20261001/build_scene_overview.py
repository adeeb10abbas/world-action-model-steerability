from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from PIL import Image
ROOT=Path(__file__).resolve().parents[4]
r=ROOT/'tmp/esmaeil_revision_rebuild/scenes'
r.mkdir(parents=True,exist_ok=True)
plt.rcParams.update({'font.family':'DejaVu Sans','pdf.fonttype':42})
fig,axs=plt.subplots(2,2,figsize=(7.2,4.8))
for ax,scene,title,goal in zip(axs.flat,['S1','S3','S4','S5'],['Cube and bowl','Butter and raisin box','Mustard and raisin box','Two bowls'],['Left / right / front / behind','Left / right / supported on top','Left / right / supported on top','Either bowl stacked on the other']):
 ax.imshow(Image.open(ROOT/f'docs/robolab-workshop-20260926/scene_images/{scene}.jpg'));ax.axis('off');ax.set_title(title,fontsize=11,weight='bold');ax.text(.5,-.06,goal,transform=ax.transAxes,ha='center',fontsize=9)
fig.subplots_adjust(left=.02,right=.98,top=.92,bottom=.05,wspace=.05,hspace=.30)
fig.savefig(r/'rev_scene_overview.pdf',bbox_inches='tight',dpi=200)
fig.savefig(r/'rev_scene_overview.png',bbox_inches='tight',dpi=160)
