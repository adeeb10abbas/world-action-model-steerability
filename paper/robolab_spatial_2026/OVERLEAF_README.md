# Same Goal, Different Words

Spatial Instruction Sensitivity in World–Action Models

## Editing

- `main.tex` contains the manuscript.
- `references.bib` contains the bibliography.
- `figures/` contains the scene illustration, wording-effect violins, goal breakdown, and paired execution examples.

The current draft has four pages of main text and one reference page. Authors: Ali-Adeeb Abbas, Esmaeil Seraj, Behrad Toghi, and Taskin Padir. Affiliations and author order follow the supplied author list.

## Build

In Overleaf, select `main.tex` as the main document and **pdfLaTeX** as the compiler. TeX Live 2024 matches the verified local build.

For a local build:

```sh
latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
```

Keep `corl_2026.sty` and `corlabbrvnat.bst` alongside the manuscript.
