# When the study can claim equivalent performance

Recorded prospectively on 24 September 2026, before any learned-policy
episodes in this clean study. This note clarifies the analysis handoff; it
does not change the frozen protocol file, prompts, queue, sample size,
physical scoring or equivalence margins.

The primary question is whether equivalent descriptions change performance.
Estimating that change does not require demonstrating equivalence. If an
effect is small or uncertain, report it as such.

With 24 confirmation layouts per model/family, a bootstrap interval can
collapse to zero when all observed paired differences are zero. That does
not show that the population difference is inside the success margin of
±0.10. For example, a population with layout contrasts +1 with probability
0.10 and zero otherwise is exactly on that margin. It still produces 24
zeros with probability `0.9^24 = 0.07977`. Calling those samples equivalent
would exceed the relevant one-sided 5% error rate on that event alone.

The analysis agent must therefore:

- Keep the planned layout-cluster bootstrap for descriptive uncertainty.
- Report all-zero or other zero-variance layout contrasts as **equivalence
  inconclusive**, not equivalent, regardless of a collapsed interval.
- Make no positive equivalence claim until a procedure with valid
  finite-sample coverage for independent layouts is specified before
  confirmation outcomes. It must respect the side strata and account for
  missingness/censoring.
- Apply that requirement to both the success margin of ±0.10 and the
  requested-position margin of ±0.02 m. A method valid for the discrete
  success endpoint does not automatically cover continuous position.
- Require both endpoints to establish their respective margins for the
  combined equivalence claim. Otherwise report inconclusive.

Do not treat 48 goal trials as independent layouts, use a nonsignificant
sign-flip result as evidence of equivalence, or replace a degenerate
bootstrap with a degenerate t or BCa interval. No additional episodes are
authorized or needed to enforce this safeguard. The existing study can
still estimate wording effects and prediction–execution disagreement.
