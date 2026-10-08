"""Publication diagram using unmodified, verified evaluation images."""
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor, white
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Paragraph
from reportlab.lib.styles import ParagraphStyle

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'revision_assets/rev_vqa_protocol.pdf'
W, H = 600, 174
c = canvas.Canvas(str(OUT), pagesize=(W, H))
c.setTitle('Instruction interpretation: inputs, question, and scoring')
c.setAuthor('Anonymous Authors')
ink = HexColor('#17232B')
muted = HexColor('#53616B')
line = HexColor('#CBD3D8')
teal = HexColor('#147D92')
orange = HexColor('#C46635')

def text(x, y, value, font='Helvetica', size=12, color=ink):
    c.setFillColor(color)
    c.setFont(font, size)
    c.drawString(x, y, value)

def paragraph(x, top, width, value, size=13, leading=15):
    style = ParagraphStyle('p', fontName='Helvetica', fontSize=size,
                           leading=leading, textColor=ink)
    p = Paragraph(value, style)
    _, height = p.wrap(width, H)
    p.drawOn(c, x, top-height)
    return height

def arrow(x1,y1,x2,y2):
    c.setStrokeColor(muted); c.setFillColor(muted); c.setLineWidth(1.2)
    c.line(x1,y1,x2,y2)
    p=c.beginPath()
    if y1==y2:
        p.moveTo(x2,y2);p.lineTo(x2-6,y2+3);p.lineTo(x2-6,y2-3)
    else:
        p.moveTo(x2,y2);p.lineTo(x2-3,y2+6);p.lineTo(x2+3,y2+6)
    p.close();c.drawPath(p,fill=1,stroke=0)

# Exact camera pixels are embedded without cropping or synthetic annotations.
c.setStrokeColor(line);c.setFillColor(white);c.setLineWidth(.7)
c.roundRect(0,1,365,172,5,stroke=1,fill=1)
for x,name,label in [(9,'wrist','Wrist'),(129,'left','Left exterior'),(249,'right','Right exterior')]:
    text(x,161,label,size=11,color=muted)
    c.drawImage(ImageReader(str(ROOT/f'revision_assets/rev_vqa_mustard_{name}.png')),
                x,94,width=107,height=60.1875,mask='auto')
h=paragraph(9,86,345,'<font color="#C46635"><b>RF:</b></font> Move the mustard bottle on the table so that the raisin box is '
          '<b>to the left of</b> the mustard bottle.',size=13,leading=14)
assert h <= 42
h=paragraph(9,40,345,'<font color="#147D92"><b>Question:</b></font> Interpret the requested outcome, not the current arrangement. '
          'Return one JSON object:',size=13,leading=14)
assert h <= 28
arrow(371,143,414,143)
c.setFillColor(HexColor('#EDF5F6'));c.setStrokeColor(teal)
c.roundRect(421,121,178,43,5,fill=1,stroke=1)
text(434,147,'Language / VL model',font='Helvetica-Bold',size=14,color=teal)
text(434,131,'Tested without robot actions',size=11,color=muted)
arrow(510,115,510,104)
c.setFillColor(HexColor('#F6F8F9'));c.setStrokeColor(line)
c.roundRect(421,1,178,97,5,fill=1,stroke=1)
text(433,83,'SCORE AGAINST',font='Helvetica-Bold',size=10,color=muted)
text(433,66,'Target',size=10,color=muted)
text(484,66,'mustard_bottle',font='Courier',size=12)
text(433,48,'Reference',size=10,color=muted)
text(491,48,'raisin_box',font='Courier',size=12)
text(433,30,'Relation',size=10,color=muted)
text(484,30,'right_of',font='Courier-Bold',size=13,color=teal)
text(433,11,'All three fields must match.',size=11,color=muted)
c.showPage();c.save()
print(OUT)
