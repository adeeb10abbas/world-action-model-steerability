import glob, io, json, os, sys, tarfile
R = "/data/users/ali/rws-20260926"
os.chdir(R)
files = ["states/accepted_states.json", "states/state_candidates.jsonl", "release/release.json",
         "release/analysis_freeze.json", "release/EXECUTION_RECORD.at_release.md", "release/bound_confirmation_episodes.jsonl",
         "annotation/build_receipt.json", "annotation/ANNOTATION_INSTRUCTIONS.md"]
for pat in ["states/_scripted*/*/scripted_attempts.jsonl", "states/_candidates/*/proposals.jsonl", "dev/servers/*/server_receipt.json",
            "runs/lanes/*.jsonl", "analysis/*.json", "analysis/*.jsonl", "results/*", "results_vlm/*", "annotation/labels_vlm_*.jsonl", "annotation/vlm_agreement.json",
            "annotation/_key/key.jsonl", "annotation/disagreements.jsonl",
            "vlm/*.json"]:
    files += sorted(glob.glob(pat))
for d in sorted(glob.glob("runs/episodes/*")):
    c = json.load(open(f"{d}/COMPLETE.json"))
    files.append(f"{d}/COMPLETE.json")
    a = os.path.relpath(c["attempt_dir"], R)
    for n in ("result.json", "initial_state.json", "episode_manifest.json"):
        if os.path.exists(f"{a}/{n}"):
            files.append(f"{a}/{n}")
files = [f for f in dict.fromkeys(files) if os.path.isfile(f)]
with tarfile.open(fileobj=sys.stdout.buffer, mode="w|gz") as t:
    for f in files:
        t.add(f)
print(len(files), file=sys.stderr)
