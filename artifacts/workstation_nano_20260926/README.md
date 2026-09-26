# Nano stock-scene workstation run

This folder retains compact records from the separately scoped six-condition
workstation run. See `docs/WORKSTATION_NANO_20260926.md` for the experiment and
runtime details.

`startup_attempts.json` records the first five infrastructure attempts. None
returned actions or produced a completed episode. Full logs and raw arrays
remain on `workstation` under `/home/ali/wam-nano-stock-20260926`.

The three PNG files are unmodified RGB observations from attempt 004, first
request, before any robot action. They show the original RoboLab scene cameras
and wrist camera. The original NPZ is retained locally and remotely and is
excluded from Git by the repository's existing raw-array rule. These images
establish rendered inputs, not policy performance.

No performance estimate or forecast-accuracy claim follows from these files.

`first_execution_receipt.json` records attempt 006's first completed request:
32 finite actions, 33 saved predicted frames, and 32 executed simulator steps.
`runtime_receipt.json` records the exact loaded configuration and CPU parameter
placement. `offload_qualification/` contains the separate small-model test;
those tests are not Nano experimental outcomes. The batch was still running
when the first-execution snapshot was taken.
