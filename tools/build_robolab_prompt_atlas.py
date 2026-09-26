#!/usr/bin/env python3
"""Render the reviewed prompt catalog as a portable illustrated PDF."""
import json
from pathlib import Path
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle, PageBreak, KeepTogether

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'docs/robolab-workshop-20260926'
OUT=ROOT/'output/pdf/ROBOLAB_SCENES_AND_PROMPTS.pdf'
OUT.parent.mkdir(parents=True,exist_ok=True)
data=json.loads((SOURCE/'prompt_matrix.json').read_text())
styles=getSampleStyleSheet()
styles.add(ParagraphStyle(name='BodySmall',fontName='Helvetica',fontSize=9.5,leading=12.8,spaceAfter=6,textColor=colors.HexColor('#25334A')))
styles.add(ParagraphStyle(name='CellText',fontName='Helvetica',fontSize=9.2,leading=12.1))
styles.add(ParagraphStyle(name='CaptionSmall',fontName='Helvetica',fontSize=8,leading=10.3,textColor=colors.HexColor('#5B6778'),spaceAfter=7))
styles['Title'].fontName='Helvetica-Bold';styles['Title'].fontSize=26;styles['Title'].leading=30;styles['Title'].textColor=colors.HexColor('#142B4A')
styles['Heading1'].fontSize=20;styles['Heading1'].leading=24;styles['Heading1'].textColor=colors.HexColor('#142B4A')
styles['Heading2'].fontSize=12;styles['Heading2'].leading=15;styles['Heading2'].spaceBefore=9;styles['Heading2'].spaceAfter=5
W=A4[0]-84
story=[]
def p(text,style='BodySmall'):return Paragraph(text,styles[style])
def add(text,style='BodySmall'):story.append(p(text,style))
def table(rows,widths):
 t=Table([[p(str(c),'CellText') for c in row] for row in rows],colWidths=widths,repeatRows=1,hAlign='LEFT')
 t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#E9EFF6')),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6),('LINEBELOW',(0,0),(-1,0),.5,colors.HexColor('#B3C2D5')),('LINEBELOW',(0,1),(-1,-1),.3,colors.HexColor('#DCE3EC'))]));return t
add('RoboLab scenes<br/>and exact prompts','Title')
add('WORLD-ACTION MODEL WORKSHOP STUDY | 26 SEPTEMBER 2026','CaptionSmall')
story.append(Spacer(1,17))
add(escape(data['research_question']),'Heading1')
add('A robot can fail because it acts toward the wrong goal, or because it cannot complete the intended movement. We test whether the future a world-action model generates helps distinguish those observable cases. A plausible video or a low success rate alone cannot answer this.')
add('Read the pictures first, then compare the prompts','Heading2')
add('<b>Different goals:</b> the requested relation, destination or object changes. Prediction and action should respond to that change.')
add('<b>Same goal, different wording:</b> D is direct, S puts the moved object first in the relation clause, and I puts the reference first using a converse relation. The desired physical result stays the same.')
add('<b>Nominal means exact RoboLab text.</b> New instructions on an old scene are explicitly marked study-added goals. We do not call them native benchmark tasks.')
story.append(table([['Proposal','Scope'],['Primary','5 scenes / 14 physical goals / 42 exact prompts'],['Held scene','Mug: 9 prompts; reset validity must be resolved'],['Optional','5 additional object, distance or destination prompts'],['Current evidence','15 Nano pilot episodes; no new experiment started']], [115,W-115]))
story.append(Spacer(1,12))
add('<b>Workshop fit:</b> primary Motion 6 (what success-only benchmarks miss), secondary Motion 4 (whether model predictions can support evaluation). This study does not establish that world models are necessary or better than policies without exposed predictions.')
add('Reference frame: robot frame. Images show actual initial shoulder-camera inputs; the wrist input is also used by the policy. Native scene backgrounds are retained. Proposed prompt interventions are not yet qualified or run.','CaptionSmall')
for s in data['scenes']:
 story.append(PageBreak());add(f'{s["id"]}. {escape(s["title"])}','Heading1')
 add(escape(s['asset'])+' | '+escape(s['status']),'CaptionSmall')
 story.append(Image(str(SOURCE/s['image']),width=W,height=W*390/1280))
 add('First raw policy observation, before the first action. Two original shoulder views; not a generated scene illustration.','CaptionSmall')
 add('RoboLab nominal prompt'+('s' if len(s['nominals'])>1 else ''),'Heading2')
 for n in s['nominals']:add('“'+escape(n['prompt'].rstrip())+'”')
 if s['id']=='S4':add('Native text has one trailing space after the period; preserved in the JSON.','CaptionSmall')
 add('<b>What we test:</b> '+escape(s['question']))
 add('<b>Keep in mind:</b> '+escape(s['note']))
 if s['id']=='S1':
  add('Four goals on this fixed scene: left, right, in front, behind. The next page gives all twelve exact instructions.','Heading2')
  story.append(PageBreak());add('S1. Four goals, three descriptions each','Heading1')
 for g in s['goals']:
  title=p(escape(g['label'])+' <font color="#62718A">('+escape(g['origin'])+')</font>','Heading2')
  rows=[['ID / form','Exact instruction']]+[[escape(x['id']),escape(x['text'])] for x in g['prompts']]
  story.append(KeepTogether([title,table(rows,[78,W-78])]))
story.append(PageBreak());add('Optional tests and interpretation rules','Heading1')
for s in data['scenes']:
 for e in s['extras']:
  story.append(KeepTogether([p(escape(e['id']),'Heading2'),p('“'+escape(e['text'])+'”'),p(escape(e['test']),'CaptionSmall')]))
add('Do not collapse these distinctions','Heading2')
for text in ['“Not left” does not uniquely mean right. We exclude negation from the primary matrix.','“Farther from the robot base” is radial distance; “behind” is a directional relation. These are separate tests.','“On top” requires support; “above” can permit hovering. RGB predictions cannot prove contact or stable support.','Bowl role reversal changes which object moves. It is a different goal, not a paraphrase.','A goal already true at reset is a maintenance case. Report it separately from achieving a new goal.','A generated future can be ambiguous, occluded or too short to show the decision. Mark it unknown; do not count it as correct or wrong.']:
 add('• '+escape(text))
add('Sources and exact machine-readable strings','Heading2')
add('Native source: NVlabs/RoboLab commit 0aef241fb088ca21bb4ebd24448940ed56620d17. Scene images: September 26 workstation pilot, request 000 raw observations. All 29 spatial task definitions are preserved in native_spatial_inventory.json.','CaptionSmall')
add('Editable source: docs/robolab-workshop-20260926/SCENES_AND_PROMPTS.md<br/>Exact prompts and hashes: docs/robolab-workshop-20260926/prompt_matrix.json<br/>Workshop: https://do-robots-need-world-models.github.io/','CaptionSmall')
def footer(canvas,doc):
 canvas.setStrokeColor(colors.HexColor('#DCE3EC'));canvas.line(42,36,A4[0]-42,36)
 canvas.setFont('Helvetica',8);canvas.setFillColor(colors.HexColor('#62718A'));canvas.drawString(42,23,'ROBOLAB PROMPT CATALOG | DRAFT FOR REVIEW');canvas.drawRightString(A4[0]-42,23,str(doc.page))
SimpleDocTemplate(str(OUT),pagesize=A4,rightMargin=42,leftMargin=42,topMargin=38,bottomMargin=48,title='RoboLab Scenes and Exact Prompts',author='World Action Model Steerability').build(story,onFirstPage=footer,onLaterPages=footer)
print(OUT)
