# Current cluster continuation

The user separately authorized runtime integration, bounded checks, and the
committed study on 24 September 2026. This supersedes the preparation-only
permission recorded in the original delivery. **Genuine study execution is
running on five A40 policy/simulator pairs.** At 2026-09-25 15:18 UTC,
396 unique episodes were complete: N3 135/522, E3 144/522 and F3 117/522.
These comprise all 54 pilots, 216 development and 126 confirmation episodes,
with 392 valid model failures and four valid successes; the five technical
attempts remain separate.
The frozen pilot barrier released development at 03:01:35.850529 UTC.
See [the operational snapshot](progress-20260925-1516.json),
[first completed confirmation evidence for all five pairs](first-confirmation-completions-20260925.json),
[the applied boundary-loan evidence](lane-loan-20260925a.json),
[the periodic timing/capacity report](report-20260925-1212.json) and
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

Current pairs are N3 i/m and l/n, E3 j/g and o/p, and F3 k/h (policy/simulator
aliases). Pod q remains unclaimed for GPU work. Other A40/A100 queues and the
protected B200 are untouched. Full 1,566-cell completion, final analysis and
final-only local H.264 delivery remain pending. No local video transfer has
started. Progress receipts are collected hourly; capacity can be reassigned
only at a verified quiescent boundary without losing an in-flight attempt.

**15:18 UTC hourly progress:** 34 additional unique completions since 14:16
correspond to **32.90 episodes/hour**, with 529 additional requests and
15,909 additional recorded actions. Three unfinished attempts have genuine
requests/actions; two are starting with zero requests. There are **1,170 C
cells remaining**. All five lanes retain their current C partitions, none
of which has completed. No boundary loan, restart or new pair was introduced.

The [control receipt](control-20260925-1517.json), captured at 15:17 UTC,
verifies unchanged guardian, notification-observer, roster and owner-index
identities. All ten owner heartbeats in the progress capture are fresh.
No new technical attempt, OOM, terminal owner or fleet hold was observed;
execution remains on `a94696d`. Only bounded metadata was read, not raw
artifacts or another timing census.

The 403 finalized manifests account for **3,197.145 GiB**. They include
the five preserved technical attempts and two further finalized results
outside the initial 396-cell completion-pointer enumeration. Unindexed
native/in-flight actual bytes remain separately unmeasured. The guardian
reported **134.283 TiB and 71,485,524 inodes available**; per-UID/GID quota
remains unverified and raw masters remain remote. Isolated expansion still
awaits explicit replacement-Pod names; shared a-f remain untouched.
The next full capacity/conditional-ETA/barriers report is due around
**16:10 UTC**, even though this preceding hourly snapshot will be less than
55 minutes old.

**14:16 UTC hourly progress:** 37 additional unique completions since 13:14
correspond to **35.74 episodes/hour**, with 542 additional requests and
16,259 additional recorded actions. All five unfinished attempts have
genuine requests/actions. There are **1,204 C cells remaining**; all five
lanes retain their current C partitions, with no whole C partition complete.
No boundary loan, restart or additional physical pair was introduced.

The [control receipt](control-20260925-1416.json), captured at 14:15 UTC,
retains the exact guardian, storage observer, boundary observer, roster and
owner-index identities. The 14:16 progress receipt has fresh heartbeats for
all ten owners. No new technical attempt, OOM, terminal owner or fleet hold
was observed. These are bounded metadata reads, not a timing census or
raw-artifact scan; executable source remains `a94696d`.

The 367 finalized manifests, including the five preserved technical
attempts, account for **2,911.628 GiB**. Unindexed native/in-flight actual
bytes remain separately unmeasured. The guardian reported **134.617 TiB
and 71,708,782 inodes available**; per-UID/GID quota remains unverified.
All masters stay remote. Isolated expansion still awaits explicit
replacement-Pod names; shared a-f remain untouched. The next full report
remains due around 16:10 UTC; the 12:12 conditional estimate is unchanged
historical evidence, not a newly calculated ETA.

**13:14 UTC hourly progress:** 37 additional unique completions since 12:12
correspond to **35.63 episodes/hour**, with 538 additional requests and
16,135 additional recorded actions. Five attempts remain unfinished: one
has zero requests at startup, one has 450 actions awaiting publication,
and three have recorded requests/actions. There are **1,241 C cells
remaining**. All five lanes retain their original current C partitions;
no whole C partition has completed and no further lane loan was applied.

The [current control receipt](control-20260925-1315.json) checks only
protection, roster, partition and lane metadata, not another timing or raw
artifact scan. All ten owners, guardian and both notification observers
retain their exact identities, with fresh heartbeats and no new technical
attempt, OOM, terminal owner or fleet hold. No process was restarted, no
new physical pair was admitted, and running source remains `a94696d`.

The 331 finalized manifests account for **2,626.114 GiB**. They include
the five preserved technical attempts and a finishing result outside the
initial 325-cell completion-pointer enumeration. Finalized-manifest count
is not a unique-completion count. Unindexed native/in-flight actual bytes
remain separately unmeasured. The guardian reported **135.000 TiB and
71,921,906 inodes available**; per-UID/GID quota remains unverified.
All masters remain remote. Isolated expansion still awaits the explicit
replacement-Pod-name relay; shared a-f remain untouched. The next full
capacity/conditional-ETA/barriers report remains due around 16:10 UTC.

**12:12 UTC four-hour report: genuine confirmation execution is verified
on all five current pairs.** Each pair's first completed C episode retained
15 requests and 450 recorded actions, matched to its frozen r4 release,
current supervisor and Pod identity. All five first episodes are valid model
failures, not technical invalidities or task successes. The earliest recorded
C request is `LAT-C01-E3-I-POS:request:0` at 11:32:16.880451 UTC, after the
11:28:27.905266 development barrier. These witnesses supersede the earlier
startup-only observation without changing it.

Current assignments are N3 `LAT-C` and `HEIGHT-C`, E3 `HEIGHT-C` and `LAT-C`,
and F3 `LAT-C`. The snapshot has 18 completed C cells and five unfinished
attempts; one has zero requests at startup and one has 450 actions awaiting
publication. This is not five simultaneous inference calls. No new loan,
physical pair, technical attempt, OOM or fleet hold occurred. The single
o/p F3-to-E3 loan remains the only actual reassignment. Since 08:12, 83
additional unique completions, 1,276 requests and 38,319 actions correspond
to 20.74 episodes/hour; the interval includes development-barrier waiting
and C startup, not steady confirmation throughput.

The 294 finalized manifests account for **2,332.667 GiB**. They include the
five technical attempts and a result finalized during collection that is
not in the earlier 288-cell completion-pointer catalogue. Unindexed native
and in-flight actual bytes remain separately unmeasured. The guardian
reported **135.428 TiB and 72,164,566 inodes available**. Per-UID/GID quota
remains unverified; raw masters stay remote, with no derivatives or local
media transfer started.

The [timing evidence](control-timing-20260925-1215.json) uses all 216 D cells
and exactly the 18 C identities in the progress snapshot. A timestamp cutoff
alone included a concurrently finalized extra C cell. The selected identity
catalogue was instead required to match the original progress catalogue's
SHA-256 and every selected pointer digest. Three later timing rows were
excluded; no outcome, pointer or recorded hash was changed. Detailed timing
and catalogue reconciliation are preserved on the PVC, with compact hashes
and aggregates committed here.

Early C mean intent-to-pointer times are N3 **581.2 s** (six samples), E3
**491.1 s** (eight) and F3 **488.9 s** (four). The projection conservatively
uses the larger of each model's D and early C mean, hence **511.1 s** for
F3. These C samples cover only initial confirmation layouts. It uses the
five actual C assignments and remaining cells, does not schedule D again,
and does not recharge startup for current partitions. Complete D24
verification overhead is scaled to C144; full C verification cost remains
unmeasured. Future loans retain the observed 886.7 s coordination allowance.

With five existing pairs and further approved intact-boundary loans,
conditional collection time is **50.3 hours remaining, around
27 September 14:30 UTC**. The same current roster with no further loans
gives 67.8 hours; a uniform 25% slowdown gives 62.9 hours. Using D means alone
gives 49.4 hours. These are engineering sensitivities, not promised deadlines
or launch instructions. Future scene costs, storage contention and
coordination latency remain uncertain; final artifact validation, analysis,
derivative encoding and local transfer remain additional, unestimated work.

There are **1,278 C cells remaining**, with no further global stage barrier
inside C. Nine whole 144-cell partitions, intact six-condition blocks,
continuous source/ownership/storage/technical-failure guards, and final
1,566-cell/27-authoritative-release accounting and artifact validation remain
mandatory. Forecast physical camera/time mapping and semantic qualification
remain unavailable, not scored zero. Isolated expansion still awaits an
explicit replacement-Pod-name relay; shared a-f remain excluded.

Current timing collection is separately versioned as
`deploy-storage-502d720/hourly_control_receipts_v4.py`, using both
`--lane-index` and `--boundary-registration` as below; it includes D/C timing
and completed C witnesses. The v3 collector remains preserved. Guardian,
storage observer and boundary observer identities are unchanged.
The next roughly four-hour report is due around 16:10 UTC.

**11:28 UTC development barrier release and boundary-observer recovery:**
`N3-DIST-D` published its final partition receipt at
**11:28:27.905266 UTC**, completing all nine D partitions without a restart.
The [11:31 startup capture](confirmation-startup-20260925-1131.json) records
the first C attempt intent and approved admission for `LAT-C01-E3-I-POS`,
created at 11:31:26 UTC against `sgw-current-E3-LAT-C-r4`.
It had zero requests/actions at that capture: this is **post-barrier
startup, not yet witnessed C inference or an episode result**. The latest
complete-episode count remains the 11:17 snapshot, not a new count.

The boundary notification connection independently failed at 11:26:49 UTC
with `tls: bad record MAC` (client stderr 07:26 EDT), while guardian and
storage-notification processes remained healthy. Only the exact orphan
PID 8142/start `152328157` was retired through its pidfd after its argv,
absence of children and unchanged protection identities were checked.
An unchanged replacement, PID 14892, exited normally after emitting a
**stale D loan hint**: its notification named `N3-DIST-D` even though that
partition had completed. Fresh FORCE_SYNC reconciliation rejected the hint;
no controller was stopped, lane loaned or episode replayed. The attempted
live verification found no process after this normal exit and failed before
any mutation; that diagnostic is preserved in the recovery receipt.

The external, read-only observer is now separately versioned as
`deploy-boundary-20260925a/watch_partition_boundary_v2.py`. It reuses the
existing statx FORCE_SYNC directory refresher, holds a singleton observer
lock, and saves immutable registration and terminal-result metadata before
notification. CPU cases cover the stale D hint, refreshed transition, owned
partition exclusion, C loan suggestion, all-complete and hold behavior.
**Model/admission source `a94696d`, lane plans, bindings, claims, guardian
and study workers were not changed.** The new observer is PID **14965**,
start **`153792717`**, under the same `sgw-boundary-loan-watch` handle with
command-scoped SPDY. Its identity and lock, absence of both earlier
observers, and one live local client PID 90022 were verified. The storage
observer remains PID 11261/start `152992038`. The underlying TLS fault
remains unproven; changing transport is not a claimed root-cause fix.

See [the complete recovery record](boundary-observer-recovery-20260925-1131.json)
for script hashes, the rejected hint, exact retirement/start identities and
the barrier evidence. At that recovery, timing collection was updated to
`hourly_control_receipts_v3.py --lane-index <current-active-lanes.json>
--boundary-registration
/data/users/ali/sgw-01/current-20260924a/deploy-boundary-20260925a/boundary-observer-start-v4.json`;
v2's hard-coded retired PID is historical. The v3 collector was compiled and
installed, with full collection deferred to the 12:10 report; the executed
D/C-aware v4 collector described above now supersedes it. The then-existing
12:10 fallback was retained.

**11:17 UTC hourly progress:** all 270 pilot/development episodes now have
completion pointers, and no episode attempt is unfinished at the snapshot.
However, only **eight of nine D partition-completion receipts** are present.
`N3-DIST-D` is still finalizing; its lane remains running while the other
four lanes wait. **Confirmation has not started.** Episode completion alone
does not release the frozen global barrier or certify retirement quiescence.
No boundary loan can unlock already completed or already owned D work.

The ten additional completions since 10:15 correspond to 9.75 episodes/hour,
with 140 additional requests and 4,231 additional recorded actions. This
interval reaches the end of D and includes barrier waiting/finalization;
it is not an estimate of steady confirmation throughput. The
[control snapshot](control-20260925-1116.json) preserves the eight completed
partitions, remaining running partition, four waiting lane states and
unchanged guardian/observer identities. All ten owners and both local
notification clients remain alive, with no new technical attempt, OOM,
fleet hold, restart, loan or added physical pair.

The 275 finalized manifests, including the five technical attempts, account
for **2,181.983 GiB**. Unindexed native bytes remain separately unmeasured.
The guardian reported **135.735 TiB and 72,377,072 inodes available**;
per-UID/GID quota remains unverified and all raw masters stay remote.
The next roughly four-hour report remains due around 12:10 UTC and needs
a fresh, stage-aware observation even though this hourly receipt will be
less than 55 minutes old.

**10:15 UTC hourly progress:** 27 additional completions since 09:13
correspond to 26.10 episodes/hour, with 370 additional dispatched requests
and 11,094 additional recorded actions. Only two attempts remain in progress
at the snapshot, both with genuine requests/actions. FLUX has all 90
pilot/development episode completion pointers, but its `DIST-D` partition
finalization is still pending; this is not yet an intact completed boundary.
`E3-HEIGHT-D` now has its completed-partition receipt, and that Edge lane
waits alongside one Nano lane. The three remaining D partitions are already
owned, so no boundary loan would unlock additional D work.

The [control snapshot](control-20260925-1017.json) preserves six completed
D partition receipts and the current three running/two waiting lane states.
Only **ten D cells remain** (six N3, four E3), followed by completion of all
nine D partitions before C. No C episode has started. All ten owners,
guardian, storage observer and boundary observer retain their exact
identities; both local notification clients remain alive. No new technical
attempt, OOM, fleet hold, restart, loan or physical pair was added.

The 265 finalized manifests, including the five technical attempts, account
for **2,102.743 GiB**. Native/in-flight bytes remain separately unmeasured.
The guardian reported **135.996 TiB and 72,527,566 inodes available**;
per-UID/GID quota remains unverified and all masters remain remote.
Isolated expansion still awaits the explicit replacement-Pod-name relay;
shared a-f remain untouched. The next roughly four-hour report is due
around 12:10 UTC.

**09:13 UTC hourly progress and notification recovery:** 28 additional
completions since 08:12 correspond to 27.31 episodes/hour, with 426 additional
requests and 12,803 additional recorded actions. Four attempts are unfinished:
one Nano attempt is at 450 actions awaiting publication, one Edge attempt is
newly starting with zero requests, and two have recorded requests/actions.
The 239 finalized manifests account for **1,896.495 GiB**; this includes the
five technical attempts and a finishing attempt not yet represented by a
completion pointer. Finalized manifests are not unique completed cells.
Unindexed native/in-flight bytes remain separately unmeasured. The guardian
reported **136.354 TiB and 72,672,648 inodes available**. All ten owners remain
nonterminal, with no new technical attempt, OOM or fleet hold. No further
loan or new physical pair was admitted; 37 D cells remain.

The `storage-guard-events-v3` notification stream exited with
`tls: bad record MAC`, while the independent guardian continued unchanged.
Its stderr timestamp `05:11:31` is client-local EDT, corresponding to
**09:11:31 UTC**, roughly four hours after observer registration; it is
not evidence of a four-hour notification-delivery gap. The exact disconnect
cause remains unproven. The orphaned read-only observer PID 6144/start
`151516341` was retired through its verified pidfd after checking its exact
argv and absence of children. Guardian, current owner/roster indexes and
boundary observer remained unchanged before and after that retirement.

The [replacement notification observer](notification-observer-start-v4.json)
is PID **11261**, start identity **`152992038`**, using the unchanged observer
script and a new immutable registration. The command-scoped setting
`KUBECTL_REMOTE_COMMAND_WEBSOCKETS=false` selects SPDY for
`storage-guard-events-v4`; it does not change cluster configuration or TLS
security. Its singleton lock and remote identity were verified, and the
single local kubectl client PID 80027 was still alive after 98 seconds.
The startup `read_bash` was interrupted by steering, so that direct process
check supplements the remote verification. This does not prove that the
underlying intermittent transport fault is eliminated. No guardian, model,
simulator, claim or raw output was restarted or changed. The boundary
observer still uses PID 8142/start `152328157` and its original connection.
See [the compact control record](control-20260925-0919.json) and
[the exact orphan retirement](notification-observer-retirement-20260925-0916.json).
The next roughly four-hour report remains due around 12:10 UTC.

**08:12 UTC four-hour report:** since 04:08, 118 additional completions
correspond to 29.06 episodes/hour, with 1,772 additional dispatched requests
and 53,153 additional recorded actions. Four partitions are active and one
N3 lane waits because no remaining D partition is unclaimed. Four attempts
are unfinished, including one already at 450 actions awaiting final
publication; they are not four simultaneous inference calls. The o/p
F3-to-E3 loan has five completed E3-DIST-D episodes. No further loan,
new technical attempt, OOM or fleet hold occurred.

Finalized manifests account for **1,666.433 GiB** across 210 attempts,
including the five preserved technical attempts. Actual unindexed native
and in-flight bytes remain separately unmeasured. The guardian reported
**136.762 TiB and 72,981,706 inodes available**; per-UID quota remains
unverified. All raw masters remain remote. Guardian identity, its ten-owner
index, the current five-pair roster and the boundary observer are unchanged.

The [current timing evidence](control-timing-20260925-0810.json) uses all
151 D completions in the progress snapshot. Mean intent-to-pointer times
are N3 570.6 s, E3 471.5 s and F3 512.0 s. Actual completed 24-cell D
partitions spent 1,155.6-1,387.1 s between the last completion pointer and
partition-summary publication. The projection now uses that measured D
overhead, rather than extrapolating only the six-cell pilots, and charges
each future loan the first observed 886.7 s boundary-to-admission interval
(including coordinator latency, one sample only).

With the **five currently verified pairs**, unchanged observed costs and
further approved boundary loans, conditional collection time is **53.5 hours
remaining, around 27 September 13:45 UTC**. Without further loans from the
current post-loan roster, the same calculation gives 72.0 hours. A uniform
25% slowdown gives 66.9 hours. These are engineering projections, not
guaranteed deadlines: confirmation-scene costs, future storage contention
and future handoff latency are unmeasured. Final full-artifact validation,
analysis, derivative encoding and local transfer remain additional,
unestimated work; hypothetical future loan events are not launch instructions.

The remaining execution barrier is **65 more D episodes**, completing all
216 D cells and nine whole D partitions (270 cumulative P+D), before any
of the 1,296 C cells. The current conditional barrier projection is
25 September 11:34 UTC. There is no additional global barrier inside C,
but nine whole 144-cell partitions and all six-condition blocks stay intact.
Final analysis still requires all 1,566 cells and 27 authoritative release
identities with complete accounting and artifact validation; final-only
video delivery additionally requires verified derivatives and local space.
Physical forecast mapping and semantic qualification remain unavailable,
not scored zero. The next roughly four-hour report is due around 12:10 UTC.

**First approved lane loan applied at 07:23 UTC:** o/p changed from F3 to E3
after its intact `F3-HEIGHT-D` boundary completed at 07:09:41.903574 UTC.
The observer's earlier N3 suggestion was only a hint: fresh inspection found
`N3-DIST-D` already owned and `E3-DIST-D` the only remaining unclaimed D
partition. The destination uses E3's own frozen binding, interpreter and
runtime environment with unchanged model execution source `a94696d`.

Both old owners had no worker/native child or pending simulator request.
The policy controller was briefly frozen using its exact pidfd, then its
owned tree was checked again to close the new-claim race. The guardian index
excluded the two retiring owners before a completed guardian observation and
their intentional retirement. The policy's original negative-15 terminal
receipt and the simulator's clean zero exit are preserved; no in-flight model
or native process was interrupted and no technical-invalid episode was added.
The pinned RoboLab Python lacked the coordinator-only pidfd API; that first
CPU invocation failed before any signal or index change. The existing base
image Python supplied the API; model and simulator interpreters did not change.

Fresh idle UUID checks, new immutable plans/control roots and exact new
supervisor identities admitted E3 on the same o/p GPUs. Guardian ownership
transitioned from 10 to 8 to 9 to 10 watched owners, without restarting the
guardian or clearing a hold. The initial 07:28 publication only established
controller startup and the `E3-DIST-D` claim. At **07:28:42 UTC**, the
[first genuine loan request/action witness](lane-loan-20260925a-first-request.json)
recorded `DIST-D01-E3-C-POS:request:0` and 30 subsequent actions.
Its admission receipt was independently matched to the new E3 supervisor,
Pod o and the exact `sgw-current-E3-DIST-D-r4` release. This establishes
actual execution on the loan, not a completed episode or successful outcome.
The other four pairs were not restarted or reassigned.

**Current monitoring inputs:** use
`study-a40-v2/active-lanes.json`, not the frozen initial-lane index, and
`deploy-storage-502d720/study_progress_snapshot_v2.py --lane-index
/data/users/ali/sgw-01/current-20260924a/study-a40-v2/active-lanes.json`.
The original metadata collector remains preserved. At 07:26, the boundary
observer completed its notification and was rearmed against the new index
as PID 8142/start `152328157`; the 11:31 recovery above supersedes that
observer with PID 14965/start `153792717` under the same
`sgw-boundary-loan-watch` handle.
The first-action observer `sgw-loan-first-action-20260925a` completed after
reading that witness; it never sent an inference request. Further progress must use the new
roster so the intentionally retired F3 owners are not reported as live failures.

The 07:26 snapshot has three unfinished attempts; the fourth active partition
is the newly started E3 loan, and one N3 lane waits for a claimable partition.
There is no fleet hold or new technical attempt. Isolated expansion still
awaits the parent's recreated-Pod-name relay; shared a-f remain excluded.

**06:11 UTC progress:** 34 additional completions since 05:09 correspond to
33.03 episodes/hour, with 516 additional dispatched requests and 15,509
additional recorded actions. Four attempts had genuine requests/actions
in flight. E3 had all 24 LAT development completion pointers, but no
partition-completion receipt had been published at the 06:12 control read.
This is not sufficient evidence to certify a quiescent boundary or retire
its controllers. No lane was loaned or restarted. All ten current owner
heartbeats were fresh, with no new technical attempt, OOM or fleet hold.
The guardian and both notification observers retained their exact process
identities; the active-owner index was unchanged.

Finalized manifests account for 1,285.576 GiB across 162 attempts, including
the five preserved technical attempts. Native/in-flight bytes not indexed
by those manifests remain separately unmeasured. The guardian reported
137.483 TiB and 73,695,527 inodes available. No media was downloaded and no
new capacity was polled or bound; the isolation-only expansion still awaits
the parent's recreated-Pod-name relay.

**Current expansion decision, 05:38 UTC:** the
[isolation-only authorization](isolated-a40-expansion-authorization.json)
supersedes the six-pair proposal below. Target **eight isolated pairs**:
the existing five plus r/s, t/u and v/q. The parent will relay recreated
r/s/t/v Pod names using the g-q isolation template. Until then, do not poll,
recreate or bind them. Verify the new actual Pod identities, exactly one
visible idle GPU and a fresh PVC-only check, then use unchanged `a94696d`
admission and the selected policy's frozen binding at an intact partition
boundary. Choose the model with the most remaining claimable work.
q's CPU guardian and the existing physical allocations remain unchanged;
the separately approved model-family boundary loans still apply.

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

No throughput change had been deployed at that timing snapshot. The preferred proposal was a loan of
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
