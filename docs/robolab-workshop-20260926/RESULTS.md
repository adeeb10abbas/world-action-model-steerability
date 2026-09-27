# RWS-20260926 confirmation results (RoboLab, four scenes, three models)

These results come from the frozen confirmation release (`release.json`, sha256 `cd0d4783…`). There are 864 of 864
valid episodes, and S2 is omitted (A1). Everything below is RoboLab only; nothing is pooled with DROID or RoboTwin.
Machine-readable sources are in `artifacts/robolab_workshop_20260926/results/` (`results.json` and CSVs). Amendments
are listed in `EXECUTION_RECORD.md`.

## Coverage

| Model | Planned | Valid | Invalid | Event-scorable | Primary-window fallback |
|---|---|---|---|---|---|
| N3 Cosmos3 Nano | 288 | 288 | 0 | 288 | 2 |
| E3 Cosmos3 Edge | 288 | 288 | 0 | 288 | 0 |
| F3 FLUX 3 Action | 288 | 288 | 0 | 288 | 0 |

## Standardized stable success

| Model | All | S1 | S3 | S4 | S5 | Achievement stratum |
|---|---|---|---|---|---|---|
| N3 | 142/288 (49.3%) | 47/96 | 38/72 | 54/72 | 3/48 | 80/226 (35.4%) |
| E3 | 93/288 (32.3%) | 31/96 | 27/72 | 32/72 | 3/48 | 41/236 (17.4%) |
| F3 | 148/288 (51.4%) | 32/96 | 26/72 | 60/72 | 30/48 | 90/230 (39.1%) |

- *Maintenance* episodes are those whose goal relation already held at the start: S1-R, S3-R, S4-L and a few
  others (172 of 864 episodes). They succeeded in 172 of 172 cases, so the "All" column is inflated by these
  episodes. The achievement stratum is the informative measure.
- Achievement-stratum success by wording form, D / S / I:
  - N3: 42.1% / 39.7% / 24.7%
  - E3: 26.3% / 17.9% / 7.7%
  - F3: 49.4% / 38.7% / 29.5%

## Confirmatory wording tests (paired at fixed start and goal; state-cluster sign-flip test, Holm-corrected)

| Contrast | Pairs | Mean Δ stable success | 95% CI (state bootstrap) | Discordant (first form only / second form only) | p (Holm) |
|---|---|---|---|---|---|
| E2: S − I (equivalent inverted-reference wording) | 288 | +0.122 | [+0.086, +0.154] | 45 / 14 | 0.00012 |
| E3: D − S (ordinary rephrasing) | 288 | +0.041 | [−0.002, +0.084] | 25 / 13 | 0.089 |

- An inverted-reference wording that is logically equivalent ("so that the bowl is to the right of the cube")
  reduces stable success by 12 points compared with the explicit form. The direction is the same for all three models
  (unpaired achievement-stratum rates, S − I: N3 +15, E3 +10, F3 +9 points).
- Ordinary rephrasing (native direct wording versus the explicit form) is not significant after Holm correction.
- Maintenance pairs contribute Δ = 0 by construction.

## Goal response (E4, descriptive)

`goal_response.csv` and `fig_goal_response.pdf` break results down by goal:
- Achievement goals that need motion toward the robot or across the table are rarely satisfied: S1-F, S1-B and
  S3-L are at or near 0–29% for all models.
- S5 bowl-in-bowl stacking separates the models: F3 reaches 58–67%, while N3 and E3 are at 0–13%.

## Failure stages and executed events

- Failure stages over all 864 episodes: stable 383, lift but no goal 287, contact but no lift 94, no mover contact
  69, goal reached but unstable 31.
- Executed next-chunk semantic events: 47 positive (wrong object or contradictory release), 293 neutral or no
  decision, 455 goal-consistent interaction, 11 physical failure. None were unscorable.
- A1 (native first-hit vs standardized stable success): every stable success was also a native first hit. The
  native checker additionally counts 6 (E3), 13 (F3) and 19 (N3) transient hits that did not remain stable.

## Forecast diagnostic utility (E1, primary): automated VLM labels (A11)

Forecast labels are automated. The two labelers are open-weight VLMs, blind to the key, and the adjudicator is
labeler A (A11 and the A11 results note in `EXECUTION_RECORD.md`). Sources:
- `artifacts/robolab_workshop_20260926/results_vlm/`
- `annotation/labels_vlm_*.jsonl`
- `annotation/vlm_agreement.json`
- `analysis/forecast_labels_vlm.jsonl`

| Comparison (leave-one-state-cluster-out, 8 folds) | n | Events | Brier without forecast | Brier with forecast | Δ (without − with) | 95% CI |
|---|---|---|---|---|---|---|
| **E1 pooled** | 864 | 47 | 0.04012 | 0.04085 | **−0.0007** | [−0.0018, +0.0002] |
| E1 N3 | 288 | 15 | 0.04012 | 0.04151 | −0.0014 | |
| E1 E3 | 288 | 8 | 0.02491 | 0.02530 | −0.0004 | |
| E1 F3 | 288 | 24 | 0.06210 | 0.06104 | +0.0011 | |
| Missingness-only control | 864 | 47 | 0.04012 | 0.04011 | +0.00001 | |
| A3 persistence control | 864 | 47 | 0.04012 | 0.04011 | +0.00001 | |
| A4 permuted forecast labels (2 seeds) | 864 | 47 | | | −0.0005 | [−0.0018, +0.0005] |

**The primary claim is not supported.** With these labels, adding forecast-derived features to the
state/action baseline does not improve held-out prediction of next-chunk wrong-object or contradictory-release
events. The point estimate is slightly worse, and it cannot be told apart from permuted labels (A4). Coverage is
complete: all 864 primary forecasts decoded, 862 of the 864 used the declared request, and the other 2 used the
declared fallback. The null result is therefore not a coverage failure.

**Predicted versus executed events (A2, pooled over models).** Rows are the forecast's visible final relation;
columns are the executed next-chunk outcome.

| Forecast | Goal-consistent interaction | Neutral / no decision | Other, no event | Wrong-goal event | Total |
|---|---|---|---|---|---|
| goal | 19 | 16 | 4 | 0 | 39 |
| alternative goal | 62 | 29 | 5 | 3 | 99 |
| not goal | 309 | 207 | 54 | 38 | 608 |
| unknown | 65 | 41 | 6 | 6 | 118 |

**What the forecasts show.**
- Forecast labels: 673 of 864 are `up_only`, and 608 are `not_goal`, so most forecast windows cover only the
  grasp-and-lift phase. They seldom show a destination relation.
- Exploratory, not prespecified: forecasts in which the labelers saw the *reference* object move (247 of 864) were
  followed by an executed wrong-goal event in 23 cases (9.3%). Forecasts showing the mover were followed by one in
  19 of 540 cases (3.5%).
- In the achievement stratum, stable success was 46 of 203 (23%) after a reference-moving forecast, versus 150 of
  425 (35%) after a mover forecast.
- This univariate signal does not survive the prespecified held-out comparison against the state/action baseline.

**Label reliability (primary windows, n = 864).** Agreement between labeler A (Qwen3-VL-235B) and labeler B
(GLM-4.5V) is low:

| Field | Raw agreement | Cohen's κ |
|---|---|---|
| moving object | 0.59 | 0.40 |
| direction | 0.49 | 0.11 |
| visible final relation | 0.20 | 0.08 |
| relation object | 0.33 | 0.11 |
| possible release | 0.93 | 0.03 |
| missing object | 0.98 | 0.00 |
| hallucinated object | 0.99 | 0.23 |
| all fields | 0.06 | |

- The labelers differ systematically. Labeler A usually reports no visible relation (571 of 864); labeler B names
  one. Labeler B reports release far more often (52 versus 4).
- The adjudicator (labeler A) chose each labeler's value as follows:
  - visible final relation: A 438, B 213, `unknown` 39
  - direction: A 173, B 267
  - moving object: A 180, B 172
- Request-0 windows agree even less: κ ≤ 0.11 on every field.

With κ at 0.1–0.4, the E1 null result fits two readings, which these data cannot separate: the forecast carries
no additional information, or the automated labels are too noisy to extract it. The null result should be
reported with that caveat, not as proof that the forecasts are uninformative.
