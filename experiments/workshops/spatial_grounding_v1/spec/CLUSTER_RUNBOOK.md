# Current cluster runbook

The operational handoff is maintained in [docs/CLUSTER_HANDOFF.md](../../../../docs/CLUSTER_HANDOFF.md), with the work split in [docs/AGENT_TASKS.md](../../../../docs/AGENT_TASKS.md). Use those documents and the implemented native worker, release and recovery paths. **No learned-policy study launch is authorized.**

The current handoff covers the 18 supported model × family × stage partitions, intact six-cell blocks, source/runtime bindings, selected clean-scene transfer, native model/time-map qualification, persistent recording, model locks, storage checks and bounded technical recovery. It does not invent image, PVC, namespace, GPU allocation or a runnable Job.

See [STANDALONE_RUNTIME.md](../../../../docs/STANDALONE_RUNTIME.md) for pinned dependencies and [SCENE_MATERIALIZATION.md](../../../../docs/SCENE_MATERIALIZATION.md) for portable scene overlays. Keep the frozen scientific files in this directory unchanged. `kubernetes/worker-job.yaml.in` is only a generic unbound reference; follow the current handoff when a concrete reviewed native Job is later prepared.
