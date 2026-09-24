# Clean WAM workshop cohort

This repository prepares clean LAT, HEIGHT and DIST scenes for the WAM
steerability workshop paper. It contains clean construction/qualification
records and the scientific source, asset and calibration dependencies needed
to reproduce them. Prior experimental cohorts are excluded from this package
and from its analysis denominators.

LAT and DIST use a flat tabletop. HEIGHT alone uses raised supports because
its goals require different final heights. For each layout, the primary
comparison changes wording while keeping the initial physical state fixed.
Removing the DIST pedestals simplifies that task; it is not a measured support
ablation. Differences between families cannot isolate a spatial-axis effect
because their objects and necessary geometry also differ.

## Scene completion

The target is 29 distinct layouts per family: one pilot, four development,
and 24 confirmation layouts. Development uses two layouts per counterbalance
side; confirmation uses twelve per side. The pilot side is declared separately.
Sides mean robot approach side for LAT, upper-support side for HEIGHT, and bowl
side for DIST. Goal sign keeps its physical meaning under either arrangement.

Every selected layout needs six complete scripted trials: both goals across
three resets each. A valid failed trial disqualifies that candidate from the
selected set and remains in the clean rejection inventory. These trials show
physical feasibility and provide no learned-policy success rate. Source geometry
and controller calibration may be reused; new candidate placements still need
their own physical qualification.

## The planned learned-policy cohort

The frozen 1,044-cell registry provides the condition and ordering template
for the separately named clean release proposed as
`SGW-CLEAN-STUDY-20260924`. It retains the original cell IDs inside the new
release namespace; the full identity is `(release_id, cell_id)`. Final
registration must bind selected clean fixtures, exact code/runtime identities,
output storage and completion pointers. No release is created here.

The clean study budget is 36 pilot + 144 development + 864 confirmation
episodes across two models and three families. Use the same selected layouts
for both models. Prior-cohort outcomes and completion pointers do not populate
this clean queue; no additional episodes are hidden in a completed release.
The original source repositories and their evidence remain untouched.

## Cluster transfer

Transfer authored design inputs, selected-layout mappings, measured poses,
calibration, asset/camera identities and compact qualification receipts.
Regenerate USD overlays against the cluster's pinned RoboLab installation;
workstation absolute paths are not portable. Record actual model-input cameras
and preprocessing during any later learned-policy run.

Follow the frozen six-cell order within each matched block and keep each
prompt static throughout an episode. Preserve valid model failures and
technical missingness separately. Compare generated futures with execution
only where a verified physical time map and matching view exist; otherwise
that forecast score is unavailable.

**Prepare the scene package and handoff only. The 1,044 learned-policy episodes
are cluster-only and are not authorized to start.**
