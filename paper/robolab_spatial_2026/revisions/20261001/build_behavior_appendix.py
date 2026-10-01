"""Read existing confirmed outcomes; write only this independent revision folder."""
from pathlib import Path
from collections import defaultdict
import csv, json, importlib.util, hashlib
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[4]
HERE = ROOT / 'tmp/esmaeil_revision_rebuild/behavior'
HERE.mkdir(parents=True, exist_ok=True)
PAPER = ROOT / 'paper/robolab_spatial_2026'
ART = ROOT / 'artifacts/robolab_workshop_20260926'
spec = importlib.util.spec_from_file_location('original_figures', PAPER / 'generate_figures.py')
old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)
rows = list(csv.DictReader((PAPER / 'analysis/episode_outcomes_corrected.csv').open()))
for r in rows:
    for key in ('stable_ever', 'stable_at_final', 'initial_goal_true_registry'):
        r[key] = r[key] == 'True'
bound = [json.loads(s) for s in (ART/'release/bound_confirmation_episodes.jsonl').read_text().splitlines()]
matrix = json.loads((ROOT/'docs/robolab-workshop-20260926/prompt_matrix.json').read_text())
data = json.loads((PAPER/'analysis/paper_results.json').read_text())
scenes = ['S1','S3','S4','S5']
models = ['N3','E3','F3']
names = {'N3':'Nano','E3':'Edge','F3':'FLUX','pooled':'All models'}
forms = ['D','S','I']
allgoals = [(s,g) for s in scenes for g in old.GOALS[s]]
scene_names = {'S1':'Cube and bowl','S3':'Butter and raisin box','S4':'Mustard and raisin box','S5':'Two bowls'}
labels = {(s['id'],g['id']):g['label'] for s in matrix['scenes'] for g in s['goals']}
assert len(rows) == len(bound) == 864
assert {r['episode_id'] for r in rows} == {r['episode_id'] for r in bound}
assert sum(r['stable_ever'] for r in rows)==383
assert sum(r['stable_at_final'] for r in rows)==191

def save_csv(name, rows):
    with (HERE/name).open('w',newline='') as f:
        w=csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator='\n');w.writeheader();w.writerows(rows)
def escape(s):
    return str(s).replace('&',r'\&').replace('_',r'\_').replace('%',r'\%')
def fmt(x): return f'{100*x:.1f}'

# The extra D-I comparison is exploratory and is not added to the original
# S-I/D-S multiple-testing family. The same cluster resampling is retained.
di=[]
for model in ['pooled']+models:
    for stratum in ['all','achievement']:
        subset=[r for r in rows if (model=='pooled' or r['model_id']==model) and
                (stratum=='all' or r['stratum_corrected']==stratum)]
        for endpoint in ['stable_ever','stable_at_final']:
            r=old.contrast(subset,'D','I',endpoint)
            r.pop('p_sign_flip')
            r.update(model=model,stratum=stratum,status='exploratory_added_20261001')
            di.append(r)
(HERE/'direct_reference_comparison.json').write_text(json.dumps(di,indent=2)+'\n')
save_csv('direct_reference_comparison.csv', [{**{k:v for k,v in d.items() if k!='ci95_state_bootstrap'},
          'ci_low':d['ci95_state_bootstrap'][0], 'ci_high':d['ci95_state_bootstrap'][1]} for d in di])

# Full counts in compact model-by-goal rows; no weighted denominators.
count_rows=[]
for model in models:
    for scene,goal in allgoals:
        subset=[r for r in rows if (r['model_id'],r['scene_id'],r['goal_id'])==(model,scene,goal)]
        d={'model':model,'scene':scene,'goal':goal,'label':labels[scene,goal],
           'initially_satisfied':all(r['initial_goal_true_registry'] for r in subset)}
        for form in forms:
            a=[r for r in subset if r['form']==form]
            assert len(a)==8
            d.update({form+'_n':len(a),form+'_anytime':sum(r['stable_ever'] for r in a),
                      form+'_end':sum(r['stable_at_final'] for r in a)})
        count_rows.append(d)
save_csv('per_goal_counts.csv', count_rows)

prompts=[]
for scene,goal in allgoals:
    for form in forms:
        actual={r['prompt'] for r in bound if (r['scene_id'],r['goal_id'],r['form'])==(scene,goal,form)}
        assert len(actual)==1
        prompts.append({'scene':scene,'goal':goal,'label':labels[scene,goal],'form':form,'prompt':actual.pop()})
(HERE/'exact_tested_prompts.json').write_text(json.dumps(prompts,indent=2)+'\n')

plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'axes.spines.top':False,
                     'axes.spines.right':False,'pdf.fonttype':42})
fig,axs=plt.subplots(1,2,figsize=(10,3.5),sharey=True)
for ax,stratum,title in zip(axs,['all','achievement'],['All evaluated episodes','Goals not satisfied initially']):
    x=np.arange(4)
    for offset,endpoint,label,color in [(-.18,'stable_ever','At any time','#147D92'),(.18,'stable_at_final','At episode end','#C46635')]:
        vals=[data['outcomes'][m][stratum]['all'][endpoint]['scene_goal_weighted_rate']*100 for m in ['pooled']+models]
        bars=ax.bar(x+offset, vals,.34,label=label,color=color)
        ax.bar_label(bars,labels=[f'{v:.1f}' for v in vals],fontsize=8,padding=3)
    ax.set_xticks(x,[names[m] for m in ['pooled']+models]);ax.set_title(title,fontweight='bold',fontsize=10)
    ax.set_ylim(0,72);ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True)
axs[0].set_ylabel('Stable-placement rate (%)')
axs[0].legend(frameon=False,loc='upper left',fontsize=8)
fig.tight_layout()
fig.savefig(HERE/'anytime_end.pdf',bbox_inches='tight');fig.savefig(HERE/'anytime_end.png',dpi=180,bbox_inches='tight');plt.close(fig)

relation=[]
for scene,goal in allgoals:
    subset=[r for r in rows if (r['scene_id'],r['goal_id'])==(scene,goal)]
    result=old.contrast(subset,'S','I','stable_ever')
    relation.append({'scene':scene,'goal':goal,'label':labels[scene,goal],
                    'initially_satisfied':all(r['initial_goal_true_registry'] for r in subset),
                    **{k:v for k,v in result.items() if k!='p_sign_flip'}})
(HERE/'per_relation_effects.json').write_text(json.dumps(relation,indent=2)+'\n')
fig,ax=plt.subplots(figsize=(9.3,5.2))
colors={'S1':'#147D92','S3':'#7951A1','S4':'#C46635','S5':'#497542'}
for i,r in enumerate(relation):
    y=len(relation)-1-i;x=100*r['difference'];lo,hi=np.array(r['ci95_state_bootstrap'])*100
    col=colors[r['scene']]
    ax.errorbar(x,y,xerr=[[x-lo],[hi-x]],fmt='o',color=col,capsize=3,markersize=5)
    if r['initially_satisfied']:ax.text(3,y,'satisfied initially',color='#666666',va='center',fontsize=7)
ax.set_yticks(range(len(relation)),[r['label'] for r in reversed(relation)])
ax.axvline(0,color='#777777',lw=.8);ax.set_xlim(-65,110)
ax.set_xlabel('Target-first minus reference-first (percentage points)')
ax.set_title('Effects differ substantially across relations',fontweight='bold')
ax.grid(axis='x',alpha=.18);fig.tight_layout()
fig.savefig(HERE/'per_relation_effects.pdf',bbox_inches='tight');fig.savefig(HERE/'per_relation_effects.png',dpi=180,bbox_inches='tight');plt.close(fig)

fig,ax=plt.subplots(figsize=(7.5,3.2))
for j,model in enumerate(['pooled']+models):
    for offset,endpoint,col,label in [(.13,'stable_ever','#147D92','At any time'),(-.13,'stable_at_final','#C46635','At episode end')]:
        r=next(x for x in di if x['model']==model and x['stratum']=='all' and x['endpoint']==endpoint)
        x=r['difference']*100;lo,hi=np.array(r['ci95_state_bootstrap'])*100
        ax.errorbar(x,3-j+offset,xerr=[[x-lo],[hi-x]],fmt='o',capsize=3,color=col,label=label if j==0 else None)
ax.set_yticks(range(4),[names[m] for m in reversed(['pooled']+models)])
ax.axvline(0,color='#777777',lw=.8);ax.set_xlabel('Direct minus reference-first (percentage points)')
ax.set_title('Direct instructions versus reference-first descriptions',fontweight='bold',fontsize=10)
ax.legend(frameon=False,fontsize=8);ax.grid(axis='x',alpha=.18);fig.tight_layout()
fig.savefig(HERE/'direct_reference_effects.pdf',bbox_inches='tight');fig.savefig(HERE/'direct_reference_effects.png',dpi=180,bbox_inches='tight');plt.close(fig)

# Runtime values are taken from actual receipts, not only the pre-run requested settings.
receipt_paths={'N3':'N3-ali','E3':'E3-alia100e-0','F3':'F3-alia100f-0-cap1'}
runtime={m:json.loads((ART/f'dev/servers/{p}/server_receipt.json').read_text()) for m,p in receipt_paths.items()}
(HERE/'runtime_settings.json').write_text(json.dumps({m:{'source_receipt':str((ART/f'dev/servers/{receipt_paths[m]}/server_receipt.json').relative_to(ROOT)),
    'source_commit':r['source_head'],'checkpoint_revision':r['revision'],'settings':r['config'],'request_seed':r['seed']} for m,r in runtime.items()},indent=2)+'\n')

out=[r'''% Insert after references, with \appendix already issued by the parent document.
% Requires graphicx, booktabs, longtable, array. Figure paths can be adjusted when copied.
\section{Evaluation details and full instructions}
\label{app:behavior}
The comparison changes the instruction while fixing the requested placement and the object the robot should move. For each physical starting state, the same model is run separately under the direct (D), target-first (S), and reference-first (I) instructions. ``Target-first'' describes the order of objects in the relational clause after ``so that''; every instruction still names the same target object as the object to move. The control sequence is not fixed: each policy generates a new sequence from its instruction, so later observations may differ.

\subsection{Scenes and starting states}
The study includes eight starting states in each of four native RoboLab scenes. Small changes to object positions and orientations produce different starts, and a scripted controller checks the requested placements before learned-policy evaluation. The cube scene has four goals, each box scene has three, and the two-bowl scene has two, giving twelve goals and 36 instructions. With three models and eight starts for every goal, this yields 864 episodes. The planned two-bin scene did not produce a qualifying start with the scripted controller and was excluded before the learned-policy outcomes were collected; it contributes no observations to these results.

\begin{table}[!ht]
\centering\small
\caption{Scenes, goals, and episode duration. All goals in a scene share its eight starting states. The already-satisfied column describes all eight starts in that scene.}
\label{tab:appendix-scenes}
\begin{tabular}{@{}p{.25\linewidth}p{.36\linewidth}p{.20\linewidth}r@{}}
\toprule Scene & Requested placements & Already satisfied & Duration\\
\midrule
Cube and bowl & Cube left, right, in front, behind bowl & Cube right & 30\,s\\
Butter and raisin box & Butter left, right, on top of box & Butter right & 40\,s\\
Mustard and raisin box & Mustard left, right, on top of box & Mustard left & 40\,s\\
Two bowls & Left bowl on right; right bowl on left & None & 20\,s\\
\bottomrule
\end{tabular}
\end{table}

Directions are defined in the robot's coordinate frame. The left and right bowl identities are assigned from their positions at reset and remain fixed for the episode. Seven goals are supplied by RoboLab; five add left/right placements using these same scenes and objects. In particular, the cube-right instruction is tested in the simple cube/bowl/banana scene used for the other cube goals, rather than in RoboLab's separate cube-right scene with additional objects.

\subsection{Exact instructions}
Tables below reproduce all tested instructions. D retains the benchmark task's original wording where that goal exists on the scene; it is a baseline instruction, not evidence that wording came from a diverse human annotation process. S describes the relation starting with the target object, whereas I starts with the reference object and reverses the relation. The source file preserves a trailing space in the native mustard-on-box instruction; that whitespace is omitted from this typeset table.
''']
for scene in scenes:
    out.append(r'\subsubsection{'+escape(scene_names[scene])+r'}'+'\n')
    out.append(r'\begin{longtable}{@{}p{.08\linewidth}p{.87\linewidth}@{}}'+'\n'+r'\toprule Form & Instruction\\\midrule\endhead'+'\n')
    for s,g in allgoals:
        if s!=scene:continue
        out.append(r'\multicolumn{2}{@{}l}{\textbf{'+escape(labels[s,g])+r'}}\\'+'\n')
        for p in prompts:
            if (p['scene'],p['goal'])==(s,g):out.append(p['form']+' & '+escape(p['prompt'].strip())+r'\\[3pt]'+'\n')
        out.append(r'\addlinespace'+'\n')
    out.append(r'\bottomrule\end{longtable}'+'\n')
out.append(r'''
The bowl task deserves separate interpretation. Its D instruction requests stacking, and its S instruction specifies that one bowl is on top of and supported by the other. I describes the lower bowl as underneath and supporting the target bowl. That wording does not explicitly require the nesting checked by the benchmark predicate. The bowl results are therefore reported separately and the pooled wording contrast is also examined without them.

\subsection{Policy and simulator settings}
The policies receive the native wrist view, two exterior views, and robot state. Each request returns 32 actions; all 32 are executed at 15\,Hz before the next observation and request. The same request seed (6100) is used for the paired instructions. Episodes run for the complete duration in Table~\ref{tab:appendix-scenes}, even after a placement first passes the check. There are no automatic request retries. The policy implementation and camera preprocessing remain specific to each released checkpoint.

\begin{table}[!ht]
\centering\small
\caption{Recorded inference settings. Values come from the policy server receipts used in the study.}
\label{tab:appendix-settings}
\begin{tabular}{@{}lccc@{}}
\toprule Setting & Cosmos3 Nano & Cosmos3 Edge & FLUX 3 Action\\
\midrule
Arithmetic & bfloat16 & bfloat16 & bfloat16\\
Sampling steps & 4 & 4 & 4\\
Sampler & UniPC & UniPC & Cosmos UniPC\\
Noise shift & 5.0 & 5.0 & 5.0\\
Visual guidance & 3.0 & 3.0 & 4.0\\
Action guidance & --- & --- & 1.0\\
Observation history & 1 & 1 & 1\\
Actions per request & 32 & 32 & 32\\
Control frequency & 15\,Hz & 15\,Hz & 15\,Hz\\
Prompt JSON formatting & No & Yes & No\\
Input/canvas setting & $540\!\times\!640$ & $540\!\times\!640$ & $544\!\times\!736$\\
\bottomrule
\end{tabular}
\end{table}

The Cosmos models use joint-position actions and a \texttt{480} resolution setting. Edge records a guidance interval of [960,1001]. FLUX uses its DROID camera layout and absolute action parameterization with the released action scale of 2.0. FLUX's immutable configuration retains an inference-seed value of 0, while each inference call explicitly supplies the study seed 6100; the latter is the effective request seed. Canvas dimensions are model-specific preprocessing settings, not different simulated camera placements. The source and checkpoint identities, together with complete recorded configurations, are included with the supplementary artifacts.

\subsection{Placement criteria and statistical comparison}
For left/right/front/behind, the spatial predicate uses the native 45-degree relation cone in the robot frame and requires the target to be supported by the table. For on-top placement, the native support predicate checks upward support and the target centroid within the reference footprint, with a 1\,cm tolerance. Bowl stacking combines the native open-top containment predicate with contact between the bowls. In every case the gripper must be detached from the target. A stable placement requires the full predicate and target speed below 2\,cm/s for one continuous second. Speed is computed by a backward difference of successive recorded positions at 15\,Hz, which avoids treating solver velocity jitter at an unchanged position as motion.

The any-time outcome asks whether this condition holds anywhere in the episode. The episode-end outcome requires it throughout the final second. Neither condition proves that the intended object was manipulated; for example, moving the reference can make the requested relative arrangement true while leaving the target untouched. They are placement outcomes rather than a complete instruction-following score.

The saved initial states determine whether a requested arrangement holds before any policy action. Cube-right, butter-right, and mustard-left are initially satisfied in all eight starts. Those three goals account for 216 episodes; the other nine account for 648 episodes. Every initially-satisfied episode passes the any-time criterion, so including these episodes increases absolute any-time rates without changing their S--I contribution, which is zero. Earlier per-episode labels disagreed with the saved-state classification for 44 episodes; the supplementary table uses the common saved-state labels consistently across forms and models. Original any-time and episode-end outcomes are unchanged.

For a wording comparison, the two binary placement outcomes are subtracted for the same model, starting state, and goal. Differences are averaged over goals within each scene, then equally over scenes and models. This prevents scenes with more goals from dominating the pooled result. Confidence intervals use 10,000 bootstrap draws of the eight physical starts within each scene; all associated goals, models, and instruction forms remain together. The original pooled S--I and D--S tests use paired sign flips and Holm correction across those two tests. Per-model, subgroup, per-relation, terminal-outcome, and newly added D--I summaries are descriptive; they do not expand that original test family.

\section{Additional behavioral results}
\label{app:behavior-results}
\subsection{Direct versus reference-first wording}
The direct baseline can also be compared with reference-first wording. This added comparison is useful for connecting the controlled S--I intervention to the short instruction normally supplied with a task, but D and I also differ in length and sentence construction. It therefore does not isolate reference reversal as closely as S versus I. Table~\ref{tab:appendix-di} and Figure~\ref{fig:appendix-di} report it descriptively.
\begin{table}[!ht]
\centering\small
\caption{Exploratory D--I gaps in percentage points, with 95\% intervals obtained by resampling paired physical starts. Positive values favor the direct instruction. No new multiplicity-adjusted significance claims are made.}
\label{tab:appendix-di}
\begin{tabular}{@{}lcc@{}}\toprule Model & At any time & At episode end\\\midrule
''')
for model in ['pooled']+models:
    vals=[]
    for endpoint in ['stable_ever','stable_at_final']:
        d=next(x for x in di if x['model']==model and x['stratum']=='all' and x['endpoint']==endpoint)
        lo,hi=d['ci95_state_bootstrap'];vals.append(f"{fmt(d['difference'])} [{fmt(lo)}, {fmt(hi)}]")
    out.append(names[model]+' & '+' & '.join(vals)+r'\\'+'\n')
out.append(r'''\bottomrule\end{tabular}\end{table}

\begin{figure}[!ht]\centering
\includegraphics[width=.90\linewidth]{direct_reference_effects.pdf}
\caption{The short direct instruction also outperforms reference-first descriptions on average. Intervals are descriptive paired-start bootstrap intervals; D--I was added after the original analyses.}
\label{fig:appendix-di}\end{figure}

\subsection{Relation-specific effects}
Figure~\ref{fig:appendix-relation} shows that the average wording effect does not represent a uniform drop across relations. Mustard-right exhibits the largest contrast: 20 of 24 target-first episodes reach the placement, compared with 2 of 24 reference-first episodes. These counts pool the three models over eight starts each. The corresponding target-first/reference-first counts are 8/0 for Nano, 4/0 for Edge, and 8/2 for FLUX. By contrast, cube-behind has a negative S--I gap, and the cube scene has no net S--I gap after averaging its four relations. This pattern motivates testing equivalent descriptions within each relation rather than expecting one prompt form to be uniformly preferable. Per-relation estimates involve only eight physical starts and should be read as descriptive localization of the observed effect.

\begin{figure}[!ht]\centering
\includegraphics[width=\linewidth]{per_relation_effects.pdf}
\caption{Per-relation S--I differences pooled over models, with descriptive 95\% intervals from the eight physical starts for that scene. Positive values favor target-first wording. Initially-satisfied goals contribute zero to this any-time contrast.}
\label{fig:appendix-relation}\end{figure}

\subsection{Reaching an arrangement and keeping it}
Across the 864 episodes, 383 reach a stable placement and 191 also satisfy the episode-end criterion. Thus 192 of the 383 any-time passes (50.1\%) do not retain the scored arrangement through the final second. Among the 648 episodes that must establish a new arrangement, 167 reach it and 94 retain it at the end; the remaining 73 account for 43.7\% of that group's any-time passes. For initially-satisfied goals, 97 of 216 episodes preserve a final stable outcome. These are raw counts. Figure~\ref{fig:appendix-end} uses the scene-balanced rates used in the main paper, so its percentages need not equal the raw fractions.

\begin{figure}[!ht]\centering
\includegraphics[width=\linewidth]{anytime_end.pdf}
\caption{Any-time and episode-end placement rates, averaging goals within each scene and weighting scenes equally. The right panel excludes goals already satisfied at reset. Reaching the scored arrangement and keeping it under continued control are distinct requirements.}
\label{fig:appendix-end}\end{figure}

\subsection{Complete per-goal counts}
Each table entry gives the number of any-time passes followed by the number of episode-end passes, both out of eight starts. A dagger marks a goal satisfied at all eight initial states. No missing observations are represented as zero. These tables report the original physical outcome predicates, not a newly corrected measure of instruction success.
''')
for model in models:
    out.append(r'\begin{table}[!ht]\centering\small'+'\n'+r'\caption{'+names[model]+r' placement counts. Entries are any-time/end, each out of eight.}'+'\n'+r'\begin{tabular}{@{}p{.48\linewidth}ccc@{}}\toprule Goal & Direct & Target-first & Reference-first\\\midrule'+'\n')
    for r in count_rows:
        if r['model']!=model:continue
        label=escape(r['label'])+(r'$^\dagger$' if r['initially_satisfied'] else '')
        out.append(label+' & '+' & '.join(f"{r[f+'_anytime']}/{r[f+'_end']}" for f in forms)+r'\\'+'\n')
    out.append(r'\bottomrule\end{tabular}\end{table}'+'\n')
(HERE/'behavior_appendix.tex').write_text('\n'.join(out))

summary={'source_episode_csv':str((PAPER/'analysis/episode_outcomes_corrected.csv').relative_to(ROOT)),
 'source_episode_sha256':hashlib.sha256((PAPER/'analysis/episode_outcomes_corrected.csv').read_bytes()).hexdigest(),
 'episodes':len(rows),'actual_prompts':len(prompts),'main_outcomes_changed':False,
 'new_analysis':'D-I descriptive bootstrap intervals, per-relation descriptive intervals; no new policy episodes',
 'pooled_DI': [d for d in di if d['model']=='pooled'],
 'figures':['anytime_end.pdf','per_relation_effects.pdf','direct_reference_effects.pdf'],
 'tex_requires':['longtable','array','booktabs','graphicx'],
 'request_seed_note':'FLUX config inference_seed remains0; wrapper service.infer(obs, seed=int(seed)) supplies6100',
 'target_first_internal_key':'S retained unchanged'}
(HERE/'BUILD_RECEIPT.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps({'outputs':str(HERE),'episodes':len(rows),'prompts':len(prompts),
                 'pooled_DI':[d for d in di if d['model']=='pooled']},indent=2))
