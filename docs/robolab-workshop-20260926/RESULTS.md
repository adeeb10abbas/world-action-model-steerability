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

## Forecast diagnostic utility (E1, primary)

E1, A2, A3 and A4 are **pending automated VLM labels** (A11). 1,726 blinded packets have been built, and every
forecast was decodable. The E1 baseline Brier score without forecast features is 0.0401 (47 positives out of 864).
