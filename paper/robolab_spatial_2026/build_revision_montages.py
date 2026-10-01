"""Compose revision figures from preserved simulation frames; source pixels unchanged."""
from pathlib import Path
import importlib.util
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from PIL import Image
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('original',HERE/'generate_execution_examples.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
out=HERE/'revision_assets';out.mkdir(exist_ok=True)
for i,name in enumerate(('mustard','cube')):
    row=dict(m.ROWS[i]);row['top']=2.34
    row['title']=row['title'][4:]
    row['headings']=tuple(x.replace('Mover-first','Target-first') for x in row['headings'])
    m.ROWS=(row,);m.HEIGHT=2.4
    # Reload the immutable original definitions before the next row.
    m.render(HERE/'figures/execution_frames',out)
    (out/'execution_examples.pdf').replace(out/f'rev_execution_{name}.pdf')
    (out/'execution_examples.png').replace(out/f'rev_execution_{name}.png')
    spec.loader.exec_module(m)
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'pdf.fonttype':42})
fig,axs=plt.subplots(3,2,figsize=(7.2,6.5))
for i,(key,title) in enumerate((('a','Edge: mustard right of the box'),('b','Nano: cube behind the bowl'))):
 for j,(suffix,heading) in enumerate((('start','Initial scene'),('s','Target-first (S)'),('i','Reference-first (I)'))):
  ax=axs[j,i]
  ax.imshow(Image.open(HERE/f'figures/execution_frames/{key}_{suffix}.png'))
  ax.axis('off');ax.set_title(heading,fontsize=10,pad=5)
 axs[0,i].text(.5,1.30,title,transform=axs[0,i].transAxes,ha='center',fontsize=10,weight='bold')
fig.subplots_adjust(left=.01,right=.99,bottom=.01,top=.93,hspace=.15,wspace=.035)
fig.savefig(out/'rev_full_execution_views.pdf',bbox_inches='tight',dpi=200)
fig.savefig(out/'rev_full_execution_views.png',bbox_inches='tight',dpi=160)
plt.close(fig)
