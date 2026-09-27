# Paper analysis

Run `python paper/robolab_spatial_2026/generate_figures.py` from the repository root (Python 3.10+, NumPy and Matplotlib). The script reads only committed source evidence and writes this directory plus `../figures/`. It records source SHA-256 hashes in `paper_results.json`.

The accepted-state registry supplies initial-goal status consistently across paired forms and models. The original per-episode stratum remains in `episode_outcomes_corrected.csv`; source artifacts are unchanged. Both outcome fields remain the frozen values. `stable_ever` means the full goal held for one continuous second at any time; `stable_at_final` requires the final continuous second. Neither is a new rescoring.

All-episode stable-ever S-I and D-S are the original confirmatory contrasts, with Holm correction across the two pooled tests. Corrected-stratum subgroup results, per-model contrasts and final-state results must be identified as descriptive or sensitivity analyses. Confidence intervals resample physical starts within scene, keeping all model/goal/form observations together. Scenes and goals receive equal weight.

`outcome_counts.csv` includes raw numerators/denominators and equally weighted rates; they need not agree because scenes have different numbers of goals. The heatmap has no achievement observations for S1-R, S3-R or S4-L; these are hatched, never displayed as zero success.

The first two columns of `goal_response_by_form.pdf` show overall stable-ever and final-state rates for every model and instruction form, including initially satisfied goals. These rates give equal weight to scenes, averaging goals within each scene; each model/form has 96 episodes. The remaining columns show the original eight-start per-goal stable-ever rates. No outcomes or paired effects are changed.

`paired_state_effects.csv` contains the 32 physical-state paired mean differences for each model and contrast, plus pooled state means (256 rows). The violin figure shows these observed discrete bounded means, vertical-only deterministic jitter, and an illustrative Gaussian KDE restricted to each group's observed extrema. It does not treat individual Bernoulli outcomes as continuous observations. Diamonds and intervals retain the unchanged paired means and state-bootstrap 95% intervals. The original forest display is retained as `wording_effect_forest.pdf`.
