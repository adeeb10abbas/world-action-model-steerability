# Scripted scene records

The [final registry](../artifacts/workshops/spatial_grounding_v1/scene_package_20260924/scene-registry.json)
selects **87 layouts**, each with six passing scripted trials. The
[completion receipt](../handoff/physical-scene-completion.json) verifies the
29-per-family quotas, side balance and selection order. These are physical
feasibility checks, not learned-policy outcomes.

The [recording index](../handoff/scene-records.json) covers all 95 completed
candidates used by the final selection campaign: 87 qualifying layouts and
eight rejections. It also identifies which logical P/D/C layout uses each
qualified candidate. Earlier development records and interrupted attempts
remain separately preserved. The registry's 205 `pending_evidence` entries
are unused registered candidates; the completed quotas require no further runs.

Each completed candidate has two complementary archives:

- `raw-arrays.tar.zst`: the losslessly archived arrays, with the original
  `archive.json` recording their identities.
- `trial-records.tar.zst`: videos, commands, state JSON, initial camera
  captures, scene/configuration files, qualification and verification records.
  `companion-receipt.json` lists every included file and its digest.

Every indexed archive was checked by SHA-256 when copied. The final index
checks the retained verification receipts, raw/companion identity links and
current file sizes; it does not repeat hashing approximately 149.8 GB of
already verified compressed archives.

## Locations

The complete indexed archive collection is on this Mac:

`/Users/ali-adeeb/Downloads/astra_creative_director/sgw_scene_raw_20260924`

Original workstation evidence and non-array records remain under:

`/home/ali/sgw-scene-design-20260923/evidence`

Companion archives also remain under the workstation's
`evidence/scene-record-backups/` tree. Some raw-array archives were relocated
to the verified Mac copy to keep workstation storage available. Their
`archive-location.json` receipts identify that move. Use the recording index
for exact paths, byte sizes and digests; do not assume every raw archive is
still present at its original workstation path.

To inspect a complete scripted trial, copy its two indexed archives and
receipts, check their digests, and extract both archives into a new empty
candidate directory. Their relative paths combine the arrays and companion
records. Retain the original receipts unchanged. The recorded action and
physical timestamps determine timing; presentation video FPS does not.

The compact records and scene inputs in Git are sufficient for the
[offline scene materializer](SCENE_MATERIALIZATION.md). Raw recording transfer
is needed only when inspecting or reprocessing the scripted trajectories.
Destination-specific overlays must still be regenerated against the pinned
RoboLab installation. None of these archives contains a learned-policy run
from the planned 1,044-episode study.
