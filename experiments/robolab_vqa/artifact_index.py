"""Durable artifact index for an RQA-20261006 run (hashes of raw artifacts kept outside Git).

python -m experiments.robolab_vqa.artifact_index --work-root /data/users/ali/rqa-20261006 --run-id <id> --output <json>
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import common as C


def entry(path: Path, role: str, root: Path) -> dict:
    return {"path": str(path), "relative_to_work_root": str(path.relative_to(root)), "role": role,
            "bytes": path.stat().st_size, "sha256": C.sha256_file(path), "availability": "shared PVC 211247-prod-pvc (/data)"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work-root", type=Path, default=C.DEFAULT_WORK_ROOT)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--release", default="r1")
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    root = args.work_root
    rel = root / "release" / args.release
    run = root / "runs" / args.run_id
    items = []
    for name in ("release.json", "validation.json", "payloads.jsonl", "query_manifest.jsonl", "frames.json", "images.json",
                 "dev_fixtures.jsonl"):
        items.append(entry(rel / name, "frozen release", root))
    for name in ("audit/answerability_review_template.csv", "audit/audit_manifest.json"):
        items.append(entry(rel / name, "human answerability audit template (not reviewed)", root))
    images = sorted((rel / "images").glob("*.png"))
    sheets = sorted((rel / "audit/sheets").glob("*.jpg"))
    items.append({"path": str(rel / "images"), "role": "lossless RGB model inputs (PNG)", "files": len(images),
                  "bytes": sum(p.stat().st_size for p in images),
                  "listing_sha256": C.canonical_sha256({p.name: C.sha256_file(p) for p in images}),
                  "per_file_hashes": "release images.json (png_sha256 and raw_rgb_sha256)"})
    items.append({"path": str(rel / "audit/sheets"), "role": "audit sheets with proposed labels and calibration overlays",
                  "files": len(sheets), "bytes": sum(p.stat().st_size for p in sheets),
                  "listing_sha256": C.canonical_sha256({p.name: C.sha256_file(p) for p in sheets})})
    for name in ("inventory/inventory.json", "inventory/cells.jsonl", "inventory/secondary_ticks.json",
                 "inventory/secondary_camera.json", "eligibility/eligibility_audit.json"):
        items.append(entry(root / name, "evidence inventory / checkpoint audit", root))
    for p in sorted((root / "inventory/initial_ticks").glob("*.json")):
        items.append(entry(p, "initial tick record used for gold labels", root))
    for p in sorted((root / "eligibility").glob("tensors_*.json")):
        items.append(entry(p, "per-tensor sha256 map", root))
    for lane_dir in sorted(d for d in run.iterdir() if d.is_dir() and not d.name.startswith("_")):
        for p in sorted(lane_dir.iterdir()):
            if p.is_file():
                role = ("raw responses" if p.name == "responses.jsonl" else "rendered prompts" if p.name.startswith("rendered_prompts")
                        else "development fixture responses" if p.name.startswith("dev_fixture") else "receipt/manifest")
                items.append({**entry(p, role, root), "lane": lane_dir.name})
    for p in sorted(run.glob("*.json")) + sorted(run.glob("*.csv")):
        items.append(entry(p, "qualification summary", root))
    for p in sorted((run / "_logs").glob("*.log")):
        items.append(entry(p, "process log", root))
    analysis = run / "analysis"
    if analysis.exists():
        for p in sorted(analysis.iterdir()):
            if p.is_file():
                items.append(entry(p, "analysis output", root))
    out = {"study_id": C.STUDY_ID, "run_id": args.run_id, "created_utc": C.utc_now(), "work_root": str(root),
           "storage": "Kubernetes namespace 211247-prod, PVC 211247-prod-pvc mounted at /data (NFS); not in Git",
           "items": items}
    C.write_json_atomic(args.output, out)
    print(json.dumps({"items": len(items), "bytes": sum(i.get("bytes", 0) for i in items)}))


if __name__ == "__main__":
    sys.exit(main())
