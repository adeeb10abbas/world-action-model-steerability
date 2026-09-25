# Current cluster continuation

The user separately authorized runtime integration, bounded checks, and the
committed study on 24 September 2026. This supersedes the preparation-only
permission recorded in the original delivery. **Genuine study execution is
running on five A40 policy/simulator pairs.** At 2026-09-25 05:09 UTC,
123 unique episodes were complete: N3 43/522, E3 34/522 and F3 46/522.
These comprise all 54 pilots and 69 development episodes, with 122 valid model
failures and one valid success; the five technical attempts remain separate.
The frozen pilot barrier released development at 03:01:35.850529 UTC.
See [the operational snapshot](progress-20260925-0510.json),
[the periodic timing/capacity report](report-20260925-0408.json) and
[first valid episode evidence for every model](first-valid-study-episodes.json).
The execution source is `a94696d3fa75c78a4f756536b988cead607e53b8`;
receipt-only commits do not change the running source or materialization.

Each model's first valid `LAT-P01-*-I-POS/attempt-002` retained 15 requests,
15 predictions and 450 actions. All three outcomes are **valid model failures**.
Every manifest artifact hash was independently verified. First-episode
intent-to-result times were N3 506.951 s, E3 426.463 s and F3 426.057 s.
These include reset, rollout, video encoding and native close, but the result
timestamp precedes manifest hashing and completion-pointer publication;
they are not the full end-to-end worker time. Videos remain under
`study-a40-v2/attempts/<cell>/attempt-002/videos/viewport.mp4` on the PVC.
Sampled policy anon+shmem peaks were 3.757-5.320 GiB across the five lanes,
with no OOM or OOM-kill events. The original technical attempts below are
preserved separately, never relabeled.

Current pairs are N3 i/m and l/n, E3 j/g, and F3 k/h and o/p (policy/simulator
aliases). Pod q remains unclaimed for GPU work. Other A40/A100 queues and the
protected B200 are untouched. Full 1,566-cell completion, final analysis and
final-only local H.264 delivery remain pending. No local video transfer has
started. Progress receipts are collected hourly; capacity can be reassigned
only at a verified quiescent boundary without losing an in-flight attempt.

**Current expansion decision, 05:38 UTC:** the
[isolation-only authorization](isolated-a40-expansion-authorization.json)
supersedes the six-pair proposal below. Target **eight isolated pairs**:
the existing five plus r/s, t/u and v/q. The parent will relay recreated
r/s/t/v Pod names using the g-q isolation template. Until then, do not poll,
recreate or bind them. Verify the new actual Pod identities, exactly one
visible idle GPU and a fresh PVC-only check, then use unchanged `a94696d`
admission and the selected policy's frozen binding at an intact partition
boundary. Choose the model with the most remaining claimable work.
q's CPU guardian and all existing lanes remain unchanged.

**Permanent stand-down on shared a-f:** no further diagnostics, retries or
study launches there. The parent reported that the user's replacement
evaluation workers are running again and explained the old zombie queue
roots as the user's restart; this is attributed parent evidence, not another
cluster check by this coordinator. Preserve the earlier failed diagnostics.
No admission-source amendment is authorized or required by this new plan.

**Historical initial A40 expansion proposal, 25 September:** the
[prospective expansion and placement record](shared-a40-expansion-20260925.json)
preserves the then-authorized six proposed pairs and their actual eligibility.
**No additional study lane or request was launched.** Existing pairs and
the independent CPU guardian on q were not restarted.

| Lane | Policy / simulator | Policy model | Actual expansion state |
| --- | --- | --- | --- |
| 1 | i / m | N3 | Existing, unchanged |
| 2 | l / n | N3 | Existing, unchanged |
| 3 | j / g | E3 | Existing, unchanged |
| 4 | k / h | F3 | Existing, unchanged |
| 5 | o / p | F3 | Existing, unchanged |
| 6 | r index 1 / s index 0 | Unassigned | Declared 1 / visible 2 GPU admission conflict |
| 7 | t index 0 / u isolated | Unassigned | Policy t has the same count conflict |
| 8 | v index 0 / q isolated | Unassigned | Policy v has the same count conflict |
| 9 | b index 1 / a index 0 | Unassigned | b had a live user evaluation queue targeting index 1 |
| 10 | e index 1 / c index 0 | Unassigned | c placement diagnostic did not qualify |
| 11 | f index 1 / d index 0 | Unassigned | d placement diagnostic did not qualify |

Exact UUIDs, Pod UIDs, observed RAM and timestamps are in the receipt.
r/s/t/v expose two GPUs despite a one-GPU Pod allocation. CPU reproduction
confirmed that `a94696d` requires one `pod_gpu_count` to equal both values:
declaring one fails visible-count admission; declaring two fails actual-Pod
admission. No truthful declaration or binding note alone can satisfy both.
Genuine isolation or a prospectively authorized source amendment is needed;
no guard, Pod receipt or running source was changed. u actually exposed only
one GPU in the read-only inventory. No Isaac process was started in r.

The e/f training queues were explicitly constrained to `GPUS=0`; b's
evaluation queue targeted its proposed study GPU despite near-zero GPU
memory. On c/d, one 180-second camera-enabled AppLauncher placement attempt
each was stopped with no owned descendants remaining, zero model requests,
zero scene resets and zero actions. **Neither qualified graphics placement.**
The diagnostic harness omitted the frozen simulator runtime environment and
inherited the Pods' different library path. Logs reported missing
`libGLU.so.1`, CUDA driver-entry-point errors and no suitable PhysX GPU.
These are preserved diagnostic-startup failures, not evidence that the
qualified production runtime or the physical GPUs are incompatible.
There was no automatic retry and no study attempt was consumed.

No cross-UUID client was observed, but no owned graphics client was observed
either, so absence of a spill is not a placement pass. Neighbor memory and
utilization varied during the attempts; unchanged-neighbor behavior cannot
be claimed. The old c/d user queue roots were zombies on follow-up, not
verified still running; this coordinator signaled only its own diagnostic
descendants, and the external cause of those queue exits is unknown.

The RAM envelope adds the existing measured policy peak of 6,306,213,888
bytes, simulator peak of 7,057,051,648 bytes and an 8 GiB margin:
20.446 GiB above existing user anon+shmem. At the actual check starts,
c/d user anon+shmem was 15.506/16.488 GiB against 64 GiB limits; both fit.
Minimum observed remaining anon headroom was 46.904/47.199 GiB, respectively.
This does not implement the required durable 4 GiB shared-Pod boundary hold.
Shared reservation/binding semantics and a launcher preserving foreign
processes also remain prerequisites; the original launcher refuses them.
At most nine whole partitions are claimable within a stage, so eleven
physical pairs would include standby capacity without changing the protocol.

**05:09 UTC progress:** 36 additional completions since 04:08 correspond to
35.25 episodes/hour, with 534 additional dispatched requests and 16,013
additional recorded actions. Five attempts were unfinished at the snapshot:
three executing actions, one at 450 actions awaiting final publication, and
one newly starting with no request yet. They are not five newly completed
episodes or five simultaneous inference calls. No new technical attempt or
fleet hold occurred. Finalized manifests account for 1,015.723 GiB across
128 attempts; unindexed native/in-flight bytes remain separately unmeasured.
The guardian subsequently reported 137.847 TiB and 73.964 million inodes free.

The local storage-notification connection failed with `tls: bad record MAC`;
the independent guardian retained its process identity and fresh heartbeat,
and study workers continued. The disconnected read-only observer remained
alive remotely. Its
[exact PID/start-bound retirement](notification-observer-retirement-20260925-0510.json)
stopped only that orphan observer, not the guardian, boundary observer or
model workers. The
[replacement notification observer](notification-observer-start-v3.json)
is running with a verified identity and an exclusive observer lock.
Current Bash handle: `storage-guard-events-v3`. This restores notifications;
it does not claim the underlying intermittent TLS fault was eliminated.

**04:08 UTC progress:** 33 additional completions since 03:02 correspond to
30.03 episodes/hour across the fleet, with 532 additional dispatched requests
and 15,919 additional recorded actions. All five pairs had real requests and
actions in flight; no lane was quiescent or loaned and no fleet hold existed.
The independently running guardian retained its verified process identity.
Its latest heartbeat reported 138.245 TiB and 74.221 million inodes available.
Finalized manifests accounted for 729.992 GiB across 92 attempts, including
the five technical attempts. Actual unindexed native and in-flight bytes
remain unmeasured, with separate engineering allowances in the receipt.

The 04:08 UTC conditional collection projection was **about 56 hours remaining,
around 27 September 12:02 UTC**, assuming approved whole-partition loans,
unchanged observed costs and no infrastructure failures. It includes model
startup, per-episode publication, scaled partition re-verification and the
global D-to-C barrier; it does not simply divide by inference latency.
Without loans the same calculation gives about 67 hours remaining.
Confirmation-scene timing and future storage contention are unmeasured:
a uniform 25% slowdown would increase the loaned estimate to about 70 hours.
Final artifact revalidation, analysis, encoding and final-only local transfer
are additional and currently unestimated, not included in that collection ETA.
Projected loans in the report are simulation assumptions, not actual changes
or instructions to claim a particular partition.

**Storage retention:** the
[metadata-only capacity sanity check](storage-capacity-sanity.json) reuses
three completed 450-action manifests; it reads no raw arrays/videos and runs
no new inference or recursive scan. The largest recorded attempt occupies
7.953 GiB of manifest-accounted raw masters. The conservative one-attempt plan
requires 36.833 TiB including native-output allowance, all later viewing
copies, margin and the original 100 GiB reserve; preserving the new 20 TiB
export floor requires 56.735 TiB available at that snapshot. The export
reported 139.184 TiB and 74.841 million inodes available. The planned inode
envelope is 18.223 million.

The PVC's 2 Ti declaration is not the export-wide enforcement boundary
(the observed export already holds more than 61 TiB). A per-UID/GID server
quota remains unverified; the current coordinator explicitly authorized
proceeding on the shared export, not a storage-owner quota attestation.
`tools/watch_study_storage.py` supplies an independent finite CPU guardian:
it samples every 60 seconds and publishes the existing fleet hold when free
space is **below 20 TiB** or free inodes are **below 5,000,000**. Active attempts
finish; no new claims start after the hold becomes visible. Stale/failed
watched owners also hold the fleet, including failures whose quota prevented
normal receipts. A preallocated hold inode supports EDQUOT/ENOSPC control
publication. Nothing is deleted, downsampled or downloaded early.

Four-hour footprint reports use finalized manifest-accounted logical bytes,
including technical attempts, and identify unindexed native/in-flight bytes
as unmeasured with a separate engineering allowance. They are not presented
as a full allocated-disk census. Before intentional lane retirement or
replacement, update the guardian's operational active-owner index so a
deliberately stopped owner is not mistaken for an infrastructure failure.
The guardian never changes the running model source or clears a hold.
Its [actual PID/start/heartbeat verification](storage-guardian-start.json)
records guardian source `502d720856c9f7a88dd37acb53255ae2388f5071`, PID 4121
on Pod q and a finite 14-day lifetime. The operational owner index is
`study-a40-v2/storage-guard/active-owners.json`. At 01:05 UTC, finalized
manifests accounted for 206.309 GiB across valid and preserved technical
attempts, with five attempts in flight; unindexed native bytes remain
separately unmeasured.

**Throughput diagnosis (receipts only):** the
[54-pilot timing analysis](throughput-20260925-pilot.json) attributes 44.85%
of five-pair time from 01:05 to 03:02 to the frozen global pilot barrier.
E3's single lane had three serial pilot partitions; other lanes waited
32.6-96.4 minutes after their last pilot partition. Active episode means,
including pointer publication, were N3 554.2 s, E3 465.7 s and F3 495.9 s.
Policy servers already stayed resident across each six-episode partition:
there were nine policy launches, not 54. Each episode did relaunch Isaac;
startup plus physical reset averaged 48-52 s, native close 5 s, video encoding
4-6 s and manifest hashing/publication 29-36 s. Inter-episode gaps were about
one second. Each partition also spent 187-337 s on final full re-verification
and cleanup. Existing receipts cannot isolate NFS write time from the
379-463 s combined inference/physics/transport/recording interval.

No throughput change has been deployed. The preferred proposal is a loan of
a quiescent lane to E3 at an intact partition boundary, preserving the stage
barriers, frozen bindings and every in-flight attempt. Replaying the existing
pilot timing with the idle F3 lane taking E3-DIST would have released the
barrier **32 min 34 s earlier**, conditional on unchanged recorded costs.
Resident-simulator work could save at most 53-57 s per episode before
subtracting still-required physical reset work; it is not a 2.4x remedy and
requires a prospective lifecycle change and remains unapproved.
The missed hourly receipt was not backfilled: the next actual snapshot was
captured at 03:02, and hourly monitoring is re-armed.

**General lane loans approved at 03:07 UTC:** the
[current authorization](lane-loan-authorization.json) allows an idle A40 pair
to restart for N3, E3 or F3, whichever has the most remaining claimable work,
at an intact partition boundary. Here "policy family" means N3/E3/F3, not the
LAT/HEIGHT/DIST scene family. Use unchanged execution source `a94696d` and
the destination policy's own frozen binding. First verify no in-flight attempt
or owned worker/native child, then retire the old controllers with exact
identities and preserve their terminal receipts. Prevent a new-claim race;
never infer quiescence from low GPU utilization or a stale lane status.
Update the guardian's owner index before intentional retirement, use new
immutable control/launch identities, and record the lane, from/to policy
family, completed boundary and selected claimable work. No loan has occurred
at the authorization snapshot; it does not change any running plan.
A [metadata-only boundary observer](lane-boundary-observer-start.json) on q
notifies this coordinator about possible eligibility. It is not another
launcher and cannot substitute for fresh quiescence or lock checks.

The remaining global execution barrier is **all 216 development episodes
(nine D partitions; 270 cumulative P+D cells) before any confirmation**.
There is no further global stage barrier within the 1,296 confirmation
episodes, but nine whole 144-cell partitions and their six-condition blocks
remain intact. Final analysis requires all 1,566 cells and the explicit 27
authoritative release identities with complete accounting; final local video
delivery remains gated on full study/output accounting, verified derivatives
and local capacity. Resource/ownership checks and the N=1/storage holds remain
continuous. Missing forecast camera/time alignment and semantic validation
block prediction claims, not genuine behavioral episodes. The next roughly
four-hour report will include these barriers, completed/522 for each policy
family, footprint, recorded loans and a timing-based conditional ETA.

**Preserved hold and repair:** the first five A40 attempts completed 15 genuine
requests and 450 physical actions each: 75 requests and 2,250 actions total.
All five native simulator children exited zero with their process groups
drained, and every viewport video is retained. The policy-side verifier
incorrectly reconstructed the simulator argv with the policy interpreter
instead of the attested RoboLab interpreter. Their
[technical-invalid manifests and clean native receipts](a40-attempt1-preservation.json)
remain unchanged; they are not scored model failures. All five lanes were held
after the in-flight attempts, without churning retries.

The authorized repair retains the `study-a40-v2/` cohort and its attempt
directories. Versioned replacement releases use the corrected common source;
affected cells resume at `attempt-002`, not a reset counter. Frozen
`spec/protocol.json` field `operations.max_attempts_per_cell` remains three.
No completed valid/censored cell may be replayed through a replacement release.
The new binding enables a durable fleet hold on the first technical-invalid
attempt (N=1), checked before model construction, new attempts and dispatch.
Only the coordinator clears the hold after verifying and deploying a fix.

The first `r3` recovery was
[blocked at resource admission before loading a model or creating an attempt](a40-r3-admission-hold.json):
its budget/allocation receipt retained the original release ID. The N=1 hold
stopped the fleet without consuming `attempt-002`. Release creation and all
operational receipts now share the revision-aware identifier; CPU coverage
checks allocation, budget, measured-runtime and storage identities for P/D/C.
Fresh `r4` releases preserve both the original technical attempts and the
zero-request `r3` release. The initiating blocked lane now also stops its own
idle simulator, rather than requiring a separate coordinator stop.

**All three actual pinned runtimes have now completed six fixed-input
requests each (18 total), with zero executed actions or study episodes.**
This is verified native inference, not merely a Running Pod. Physical forecast
mapping remains unavailable. These requests
are consumed; do not rerun them to finish downstream evidence.

**Subsequent live evidence:** Nano-B, Edge-B and FLUX-C each consumed two
additional real requests and executed 64 receiver-confirmed physical actions
with two resets. [Edge](e3-live-result.json) and [FLUX](f3-live-result.json)
completed cleanly; FLUX's actual terminal Jobs/Pods and lifecycle/log/result
hashes are [preserved on the PVC](f3-live-c-preservation.json). Nano's original
missing post-close marker/cleanup failure remains unchanged. Its separate
[external lifecycle witness](n3-live-external-witness.json), SHA-256
`09fcc4da523af38e0565977f7c96b4de26876629ddb5a134cbff158007bf72a3`,
verified 712 retained artifacts and actual native termination without claiming
that `app.close()` returned. **Totals: 24 native requests, 192 live actions,
six live resets, zero study episodes.** No qualification request may be
replayed to improve these receipts. Forecasts remain `decoded_unmapped`.

**Prospective A40 policy amendment, 23:16 UTC:** every proposed A100 Pod
(e/f/g and p1/p2/p3) has a live user-owned ablation queue, including sleeping
workers behind zero-utilization GPU snapshots. None was stopped or shared.
The orchestrator has approved [all three policy cohorts on A40](a40-policy-amendment.json),
using seven policy/simulator pairs and one spare device. All confirmation
data remain on A40 even if A100 capacity later becomes idle. Existing A100
qualification receipts retain their actual hardware identity; they are not
A40 compatibility evidence. The first genuine study request per model is
the A40 compatibility observation, with no new fixed-input campaign.
Kernel/NATTEN, device-memory or host-memory failures remain infrastructure
failures with no model score; stop only the affected model and preserve evidence.

The finite existing-Pod controller is pushed and deployed at
`14027a3fe5e3e262e788579461844b4adaebe1dc`, in
`/data/users/ali/sgw-01/current-20260924a/source-14027a3`.
Its CPU materialization at `materialization-14027a3` binds all 87 layouts and
1,566 cells; environment-binding SHA-256 is
`230982e7fb555255d001bff913bd578144c483aa5c2e01a5da978debc0278fcd`.
Observed-clock fixtures were derived from the already consumed native logs,
without new model or physics requests. Prepared A100 inputs remain
unlaunched historical plans, not current allocation authority. New A40 inputs
must use a separate immutable binding and the amendment receipt.
These bare Pods have no Job UID: bind actual Pod and finite supervisor
identities rather than fabricate Job owners. At amendment time there were
zero study releases, requests and episodes.

The first three A40 study-phase startups created releases but consumed **zero
model requests, actions or episodes**. All stopped during model construction
because the socket guard incorrectly required `/proc/net/tcp6` in these
IPv4-only namespaces. Their [original statuses, terminal supervisors and logs](a40-ipv4-startup-preservation.json)
remain unchanged under `study/`. The guard now permits only a missing IPv6
table, still requiring readable IPv4 evidence and process-group socket-inode
ownership. All three old policy supervisors terminated with no owned descendants.
Their idle simulator lanes received identity-bound stop instructions.
The authorized relaunch uses one fixed source and a fresh `study-a40-v2/`
cohort, not rewritten release hashes or reused attempts.

The fresh capacity check also found live ablation queues on A40e/f
(PIDs 39208 and 36943); both remain excluded. Only the 11 single-GPU Pods
g..q were clean. The approved useful fleet is five pairs plus one spare:
initial N3 i-to-m, E3 j-to-g, and F3 k-to-h, then provisional N3 l-to-n and
F3 o-to-p after each model's first request succeeds; q is unclaimed.

The screenshot's A40 names were abbreviated: actual names end in
`-a40-2gpu`. Read-only telemetry found live `lerobot-train` in A40a/b/c/d
(PIDs 1604, 965, 979, 979 respectively), with 11.2-11.4 GiB occupied and
resident data workers. Leave those Pods and their second GPUs untouched.
A40e/f on nodes188/201 had only PID1 `sleep`, no compute processes, and four
idle A40 GPUs. Their [actual allocation metadata](user-a40-reservation-metadata.json)
is retained. The initial exact-name-only [reservation read](user-named-reservations.json)
did not match abbreviated A40 aliases; it is not evidence that these allocations
were absent. Simulator lanes, not the number of reserved A100s, limit useful
parallelism. All B200/V100 and unrelated user workloads remain excluded.

The [latest user instruction](completion-instruction.json) extends the
objective through all 1,566 unique study outcomes and verified video/raw
manifests, not merely launch. Keep every actual recording on the PVC and push
compact indexes, hashes, provenance and derived results. Do not add video
blobs to Git or Git LFS. Retain full-quality originals, including original
resolution, frame counts and timestamps. Create separate H.264 MP4 viewing
derivatives with their own hashes and master references. **Only after all
1,566 episodes and required outputs are finished/accounted**, download the
study viewport and exposed prediction derivatives to
`/Users/SZ5VJY/Downloads/world-action-model-steerability-videos`, with a
manifest-driven, checksum-verified local receipt. Preserve the PVC originals,
safe hierarchy and resumable partial files; do not overwrite unrelated files
or delete other user data for space. Check total derivative bytes against
fresh laptop headroom before transfer. If insufficient, report the exact
capacity needed for the user's external drive; do not start partial delivery
before full-study accounting.

Once the study is actually healthy and running, use one light receipt/scoped
Pod-state check about every 30-60 minutes, with nonempty evidence commits about
hourly or at completed-partition milestones. No full raw-data rehashing or
inference for monitoring. Switch immediately to focused diagnosis on failure
or abnormal lack of progress, then return to sparse monitoring after recovery.
Do not arm that monitor before launch or make cluster progression depend on
the monitor, laptop, or app remaining open.

The sole resource/output coordinator is session
`5ed7dc81-68d8-493f-a8c4-81a4b6cb59f6`, acting on the user's instruction relayed
by `c230f3cd-3fe9-4f1f-9ee4-e8b857151a60`. The current instruction permits
verified-idle existing capacity as needed, not the historical four-GPU cap.
It does not permit paid capacity, preemption, stopping other workloads, or
changing the frozen scenes, cameras, prompts, splits or scoring.

## Persistent inputs and observed results

- Exact delivered source: `6dbdecc37b397b2ab7b9f064008da40e067a5ceb`.
  Cluster checkout: `/data/users/ali/sgw-01/current-20260924a/source`.
- [Materialization](materialization.json): all 87 layouts and 1,566 planned
  bindings regenerated at
  `/data/users/ali/sgw-01/current-20260924a/materialization`.
  This is still a physical-only binding, not a released queue.
- [Destination check](destination-check.json): LAT-P01, two resets, three
  current-position holds, 15 exact sensor/RGB matches, zero physical goal
  trials. The Job exited zero on an idle-checked, UUID-locked A40. Current
  camera configuration was unchanged. No broader camera campaign was run.
- Current-input Nano diagnostic source:
  `f6b3f17f4c0710167ac4455fe2a85edf9f3a08c8`, checked out separately at
  `/data/users/ali/sgw-01/current-20260924a/source-f6b3f17`.
  Registration:
  `/data/users/ali/sgw-01/current-20260924a/current-n3-registration.json`,
  SHA-256 `2ee4773e5b72023330c4e397f622069c363ad28de962e4347119ee59d8576ef8`.
  Frozen LAT-P01 effective seed: `2026092201`. Six requests maximum, no
  executed actions, no automatic retry.
- Nano attempt A failed during guardrail startup with missing `libxcb.so.1`;
  [original failure](n3-check-a-failure.json) and
  [actual Job](jobs/n3-check-a.json) are retained. Attempt B used the repaired
  linker path, then found missing `uvx` on `PATH`;
  [original failure](n3-check-b-failure.json) and
  [actual Job](jobs/n3-check-b.json) are retained. **Both started zero model
  requests.** Neither is a behavioral failure or scored zero. Their raw
  evidence remains under `n3-check/` and `n3-check-b/` in the cohort root.
- E3/F3 adapter implementation, immutable file identities, official source
  references and CPU checks are recorded in
  [checkpoint_integrations.json](../../experiments/workshops/spatial_grounding_v1/checkpoint_integrations.json).
  Actual fixed-input results are retained below.

## Completed native fixed-input checks

The [terminal Job/Pod identities](fixed-input-job-outcomes.json) record all
three Jobs exiting zero with no container restarts. Submitted manifests are
in `jobs/n3-check-c.json`, `jobs/e3-check-a.json` and `jobs/f3-check-a.json`.
Nano ran source `4c39c450b1dace8470edc7d907fb4e86a88bd0e3`; Edge and FLUX ran
`1b45b1fedaa5377d2d3dd7717607b18f5266be54`. All used separately idle-checked,
UUID-locked A100-SXM4-80GB allocations on `dcwipphai0061.edc.nam.gm.com`.

- [Nano result](n3-fixed-input-result.json), with
  [loaded runtime](n3-loaded-runtime.json): six valid native responses;
  repeated actions and all three offline latent redecodes were bit-identical.
  Opposite-prompt action RMS difference was `0.08661260613195104`.
- [Edge result](e3-fixed-input-result.json): six valid native responses and
  six decoded same-request futures; repeated actions were identical.
  Opposite-prompt action RMS difference was `0.03079543058790927`.
- [FLUX result](f3-fixed-input-result.json): six valid native responses,
  three with same-request latent/video capture and three without capture.
  All three matched capture-on/off action arrays were exactly equal (maximum
  absolute differences `0.0`). Opposite-prompt RMS difference was
  `0.12912268060309118`.

These differences are descriptive model outputs, not physical success scores.
All use the frozen effective seed `2026092201`. A separate CPU read verified
45 retained action/future/latent/redecode artifact hashes (21 Nano, 12 Edge,
12 FLUX) without making more model requests. Raw bytes, native traces and
logs remain under `n3-check-c/`, `e3-check-a/` and `f3-check-a/` on the PVC.
FLUX's three no-capture outputs are deliberately `not_exposed`, not missing
scored zeros. Exposed forecasts remain physically unmapped.

## Reproducible startup repair

Use the checked-in
[`tools/cluster_policy_bootstrap.sh`](../../tools/cluster_policy_bootstrap.sh)
for subsequent policy commands, including native workers with the corresponding
model interpreter. It prepends that interpreter's `bin/` to `PATH` so the
pinned Cosmos checkpoint resolver finds its existing `uvx`, and prepends:

```text
/data/users/ali/vla_wam/envs/robolab-native-libs-ubuntu2204/usr/lib/x86_64-linux-gnu
/data/users/ali/glvnd/lib
/data/users/ali/vla_wam/envs/fastwam-native-libs/lib
/usr/lib/x86_64-linux-gnu
```

`SGW01_NATIVE_LIBRARY_DIRS` can explicitly bind a relocated colon-separated
directory list; nonexistent or relative entries are rejected. These are
native shared libraries, not alternate model packages. No guardrail is
disabled. No Python environment or upstream source was modified to fix these
two failures.

Also bind `UV_CACHE_DIR` to
`/data/users/ali/sgw-01/current-20260924a/cache/uv`. The subsequent CPU-only
resolver check found that a numeric-UID staging process otherwise selected
unwritable `/.cache/uv` and `/.local/share/uv/tools`. The bootstrap now requires
an explicit absolute, writable cache before a Cosmos command and places
`UV_TOOL_DIR` under that cache unless explicitly bound elsewhere; it never
relies on those root-home defaults.

With both paths bound, the pinned `GUARDRAIL1_CHECKPOINT.download()` resolver
passed on CPU against its existing offline snapshot
`d6d4bfa899a71454a700907664f3e88f503950cf`; no guardrail weights were downloaded,
no guardrail was disabled, and no model was constructed. `uvx` installed its
pinned `hf@1.16.4` helper into the writable tool cache.

The new Edge source `cf5d68c00d97ccd2480a2320ed652b92dec63102` and checkpoint
`a7c7288f9b6ac1684e993007b0f9703dd26e58ef` are staged separately under this
cohort's `external/cosmos-cf5d68c` and `checkpoints/cosmos3-edge-a7c7288`.
`verify_identity("E3")` passed for these fresh files; the older
`vla_wam/checkpoints/cosmos3_edge_policy_droid` did not match the new
`transformer/config.json` identity and was not changed. The FLUX policy and
base snapshots in `checkpoint_integrations.json` also passed full registered
file verification. Its isolated `envs/flux-e2dd1d8` environment has Python
3.12.13, Torch 2.10.0+cu128, NATTEN 0.21.6+torch2100cu128, and the study's
recording dependencies. These are CPU staging results, not runtime qualification.

The corrected Nano Job is retained as `jobs/n3-check-c.json`, using source
`4c39c450b1dace8470edc7d907fb4e86a88bd0e3` and new output `n3-check-c`.
It passed the fresh idle allocation check on
`GPU-9b784824-3fad-dcf1-8e3e-abee22db4a8e` (A100-SXM4-80GB), completed all
six requests and the three offline redecodes, then exited zero.

For Edge/FLUX, use the new bounded `checkpoint_fixed_input.py` entrypoint
documented in `docs/STANDALONE_RUNTIME.md`. Its CPU tests exercise fake
backends only. Neither those tests, imports, weight hashing nor a Running Pod
qualifies a model or starts a behavioral episode.

The following **CPU-only** startup check passed in the approved container:

```sh
UV_CACHE_DIR=/data/users/ali/sgw-01/current-20260924a/cache/uv \
bash tools/cluster_policy_bootstrap.sh --check-only N3 \
  /data/users/ali/vla_wam/envs/cosmos-nano-411d25b-v3-exact/bin/python
```

It verifies `uvx 0.10.8` and imports OpenCV/RetinaFace without model construction.
OpenCV is `4.13.0`. A normal invocation runs that same startup check and then
executes the supplied command:

```sh
UV_CACHE_DIR=/data/users/ali/sgw-01/current-20260924a/cache/uv \
bash tools/cluster_policy_bootstrap.sh N3 \
  /data/users/ali/vla_wam/envs/cosmos-nano-411d25b-v3-exact/bin/python \
  -m experiments.workshops.spatial_grounding_v1.nano_fixed_input \
  --registration /data/users/ali/sgw-01/current-20260924a/current-n3-registration.json \
  --output /data/users/ali/sgw-01/current-20260924a/NEW-DIAGNOSTIC-OUTPUT
```

This is a **diagnostic**, not a study command. Use only in a newly registered,
finite, owned Job after its idle/UUID/model-lock checks. The literal
`NEW-DIAGNOSTIC-OUTPUT` above must not be used as a shared default. Never rerun
the completed physical campaign or clear failed output/claim paths.

## Actual environment and ownership

Context `prod-dcwi-warrenq1-vmkub007`, namespace `211247-prod`, PVC
`211247-prod-pvc` mounted at `/data`; UID/GID `816149040/2518800`.
All current Jobs use approved image
`artifactory-ci.gm.com/docker-approved/devcontainers/base@sha256:03f5ce7d090fbd378070a8216d0aedfc6e473c52da99b40b0cf53918612a297c`.
The exact submitted diagnostic Jobs are retained in [jobs/](jobs/).
They have exact nodes, finite deadlines, `backoffLimit: 0`, no service-account
token, exclusive output creation, and shared physical-GPU locks.

RoboLab remains `0aef241fb088ca21bb4ebd24448940ed56620d17` at
`/data/users/ali/vla_wam/external/RoboLab-pi05-v3-0aef241`,
with Python 3.11.13 at
`/data/users/ali/vla_wam/envs/robolab-v2-isaac50/bin/python`.
N3 remains source `411d25b2e35bc441126f48c44a4b93e1c0564274` at
`/data/users/ali/vla_wam/external/cosmos-framework-411d25b`,
checkpoint `6706d7680581c255ff61e0f3bb49d90eac55c79e` at
`/data/users/ali/vla_wam/checkpoints/cosmos3_nano_policy_droid`,
and Python 3.13.6 at
`/data/users/ali/vla_wam/envs/cosmos-nano-411d25b-v3-exact/bin/python`.
`HF_HOME=/data/users/ali/vla_wam/cache/huggingface-cosmos`; credentials are
not stored here.

The protected training Pod `211247-ali-b200-1gpu`, UID
`b58e8416-9412-4db5-921b-110420433480`, was observed Running and was not touched.
Never use its node `dcwipphhgc225.edc.nam.gm.com` or GPU
`GPU-60b3065c-79cb-61e6-b92a-32d0ae3750f3` for this study.

Physical locks remain `/data/users/ali/sgw-01/locks/gpu-<UUID>.lock`.
Model locks are
`/data/users/ali/sgw-01/current-20260924a/locks/<N3|E3|F3>.lock`.
Future releases must remain sibling directories in this same new cohort
parent. Do not import old cohort completion pointers or evade model locks
with different parents.

## Hardware selection, not advertised availability

The user's requested [bounded hardware inventory](hardware-inventory.json)
was read at 19:44:49 UTC. Kubernetes advertises 95 A100 80GB, 64 A100 40GB,
42 A40, 40 B200, 16 V100 32GB and eight RTX PRO 6000 Blackwell GPUs.
These are capacity counts, **not idle counts**. Only this namespace's
reservations are visible; the inventory cannot establish current physical
availability across other namespaces.

Use **A100-SXM4-80GB (SM80) for N3/E3/F3 inference** and **A40 (SM86) for the
separate RoboLab headless/RTX renderer**. Those roles have current successful
native evidence, on two distinct A100 devices and one A40 device. Their prior
idle snapshots are not fresh admission receipts. A100 lacks RT cores and is
not an Isaac renderer substitute. The installed policy builds are Torch
2.10/CUDA 12.8 for Nano/FLUX and Torch 2.10/CUDA 13.0 for Edge, with exact
NATTEN builds recorded in the inventory. Driver 580.95.05 was demonstrated.
Torch architecture flags alone do not qualify all NATTEN/native kernel paths.
No peak VRAM was recorded, so no lower-memory fit or minimum VRAM is claimed.

The initial bounded placement used up to three policy lanes on node0061 and
separate A40 simulator lanes on nodes191/192/193. The snapshot showed no
namespace-visible GPU reservations on those candidate nodes, but each new
useful Job must still pass fresh actual-device checks. Invoke
`gpu_idle_probe --expected-name "NVIDIA A100-SXM4-80GB"` for policy lanes and
`--expected-name "NVIDIA A40"` for simulator lanes, in addition to count,
idle-process and physical-UUID locks. New release bindings should also set
`model_gpu_names` per model; the worker checks those exact device names before
construction. Preserve actual blocked receipts rather than trying other
placements in a loop. Extra hardware does not waive one worker per model,
whole partitions, P -> D -> C, or the protected node exclusion.

## Live admission and owned-terminal reconciliation

The six submitted `jobs/live-*-a.json` Jobs used exact deployed source
`8ac48581eec62143dbd8be7d4cd77cce6de10887` and
[fresh source/path materialization](live-materialization.json). That CPU
materialization preserves all 87 layouts, 1,566 bindings and the unchanged
camera hash; it is not another native scene campaign.

[Actual admission evidence](live-admission-a.json) records all three simulator
Pods and the F3 policy Pod rejected before container startup:
`UnexpectedAdmissionError`, requested `nvidia.com/gpu: 1`, available `0`.
N3/E3 obtained two idle A10080 devices, but their 180-second identity waits
expired with exit 1 and zero restarts. The
[PVC pre-execution snapshot](live-pre-execution-state-a.json) confirms no
simulator identity, mailbox or model-evidence directory for any model.
**This batch produced zero live model requests, physical actions, or study
episodes.** It is an infrastructure failure, not a model score.

The user then authorized one bounded owned-terminal allocation reconciliation.
[Eight exact terminal Jobs](terminal-reconciliation-before.json) were checked:
the six failed live-A Jobs, the completed current destination check, and
the completed historical simulator
`sgw01-ali-main-p-20260923dn-simulator-02`, Job UID
`3c020853-eca6-4fa4-a96b-510e4ea7b9ef`, Pod UID
`4062ded0-056f-4673-9858-7ee2ed30e1a7`. Their complete pre-cleanup Kubernetes
snapshots and output-owner/log hashes were
[preserved on PVC](terminal-reconciliation-preservation.json) before deleting
only these terminal Kubernetes objects. All matching Pods were then absent.
No PVC claim, raw output, old result, unrelated workload or protected training
allocation was changed. Historical results were not reanalyzed or imported.

A single new useful Nano simulator-B admission on the **same node191**
subsequently succeeded. Its actual Job UID is
`52fc58f5-9c87-48a3-9ae6-0dd6c0f158d8`, Pod UID
`91ff3894-b12a-4820-831f-2f906e976bce`; the identity was bound before creating
its policy counterpart. Attempt B uses the distinct
`/data/users/ali/sgw-01/current-20260924a/closed-loop-N3-b` output, not cleared
or reused attempt-A paths. Admission alone does not establish live inference.
Prefer sequential documented model checks on this one compatible
A10080/A40 pair, not a speculative multi-node placement loop.

The [renderer](../../tools/render_runtime_closed_loop_jobs.py) reproduces the
submitted A manifests exactly. An explicit `--attempt-suffix` gives a distinct
Job/output identity, and `--simulator-node` can select one of the three
registered A40 candidate nodes for sequential use; type/idle/UUID/model locks,
finite deadlines and no automatic retries remain unchanged. Registration and
actual UID binding are still separate required steps. Do not resubmit any
recorded attempt or treat an old idle snapshot as current admission.

The successful Edge check uses source
`a68a0bc4aef413f400dede291cbd83f139b996bf` and
[its source-only materialization](lifecycle-materialization.json), including
the outer Isaac shutdown witness. The initial source bundle import exposed
the delivered depth-one history boundary; the new checkout explicitly retains
the real `6dbdecc` shallow boundary. No commit or historical checkout was
rewritten. The incomplete import remains separate on the PVC.

The user's newer resource direction requests
[three independent model lanes](three-lane-plan.json): three A10080 policy
GPUs plus three A40 simulator GPUs, not one unsuitable physical GPU per model.
The supplied node inventory establishes compatible advertised capacity only.
One useful distinct FLUX pair was attempted: node0063 allocated an
[actually idle A10080](f3-live-b-pre-execution.json), but node190's A40
[admission was rejected](f3-live-b-admission.json) with requested 1/available 0.
No simulator identity was published and no FLUX live request or action ran.
This is not three running lanes. The user clarified that protection applies
to Edge's evidence/claims, not indefinite retention of terminal allocation
objects. After [full Edge preservation](e3-live-b-preservation.json) and
[failed FLUX preservation](f3-live-b-terminal-preservation.json), only their
four verified terminal Jobs/Pods were recycled. FLUX's prior policy exited
1 at 21:21:07 UTC, and its shared model lock was independently available.
Fresh FLUX-C is separately registered and admitted on the proven0061/191
pair; its actual simulator UID was bound before proceeding. Its live requests
have not previously been consumed. No Nano/Edge requests are replayed.
The separate protected training workload remains untouched. No paid resources,
new cluster, speculative placement sweep, or lower hardware guard is allowed.

## Remaining gates and resume

Do not repeat the completed fixed-input construction/inference checks or
capture parity. Establish the live physical action-prefix/camera/time
correspondence with the separately bounded closed-loop technical check.
Its implementation and CPU contracts are present; the first native admission
failed before execution and the reconciled Nano attempt is separately bound.
Native check success is not yet claimed. Follow the
[two-phase registration instructions](../../docs/STANDALONE_RUNTIME.md#bounded-live-model-to-simulator-check)
to preserve planned-cell status and actual simulator Job/Pod identity.
Preserve unavailable forecasts explicitly. Complete guarded runtime/fixture
receipts before creating any full model/family/stage release.

There is currently **no release to resume**. Once released, the existing
`native_worker_entrypoint --release <immutable-release> --model <model>
--family <family> --stage <stage> --resume --max-valid-episodes <6|24|144>`
is the resume interface, using the same runtime binding and shared cohort
completion pointers. Keep P -> D -> C and all six conditions in each block.
This per-release command is not itself a durable 27-partition supervisor.
Full-study progression must run on Kubernetes independently of the app,
retain real finite deadlines/resumption, and honor shared locks and stage gates.
Never substitute a diagnostic registration or `bound-cells.jsonl` for its
released `queue.jsonl`. Retain all raw arrays/videos/request traces on the
PVC and commit only compact evidence and hashes.

The worker now supports an explicitly opted-in, hash-bound
[replacement-Job admission](../../docs/STANDALONE_RUNTIME.md#resuming-under-a-replacement-job).
This fixes the otherwise unavoidable stale Job/Pod UID in an immutable
allocation receipt without rewriting scientific release hashes or replaying
completed cells. Its regression check stops after one synthetic completion,
rejects the replacement Job's old allocation, then resumes only the remaining
five cells with fresh operational authority. This is CPU engineering evidence,
not a native study-resume claim.
