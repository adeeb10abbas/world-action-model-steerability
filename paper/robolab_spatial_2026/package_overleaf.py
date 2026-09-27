"""Package the paper for the existing Overleaf project without replacing its old main.tex."""
from pathlib import Path
from shutil import copy2
from zipfile import ZipFile, ZIP_DEFLATED

paper = Path(__file__).resolve().parent
repo = paper.parents[1]
bundle = repo / "tmp" / "overleaf_rws_20260927"
bundle.mkdir(parents=True, exist_ok=True)
source = (paper / "main.tex").read_text()
source = source.replace(r"\graphicspath{{figures/}}", "")
source = source.replace("scene_mustard.jpg", "rws_scene_mustard.jpg")
source = source.replace("wording_effect.pdf", "rws_wording_effect.pdf")
source = source.replace("goal_response_by_form.pdf", "rws_goal_response.pdf")
source = source.replace(r"\bibliography{references}", r"\bibliography{rws_references}")
(bundle / "rws_main.tex").write_text(source)
files = {
    "references.bib": "rws_references.bib",
    "corl_2026.sty": "corl_2026.sty",
    "corlabbrvnat.bst": "corlabbrvnat.bst",
    "scene_mustard.jpg": "rws_scene_mustard.jpg",
    "figures/wording_effect.pdf": "rws_wording_effect.pdf",
    "figures/goal_response_by_form.pdf": "rws_goal_response.pdf",
}
for source_name, output_name in files.items():
    copy2(paper / source_name, bundle / output_name)
output = repo / "output" / "pdf"
output.mkdir(parents=True, exist_ok=True)
copy2(paper / "main.pdf", output / "same_goal_different_words.pdf")
with ZipFile(output / "same_goal_different_words_overleaf.zip", "w", ZIP_DEFLATED) as z:
    for name in ["rws_main.tex", *files.values()]:
        z.write(bundle / name, name)
print(bundle)
