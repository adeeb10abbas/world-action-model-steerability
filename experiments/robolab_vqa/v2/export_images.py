"""Index the exact RQA model-input images committed to Git (CPU, standard library only).

The PNGs under artifacts/robolab_vqa_20261006/model_input_images/images/ are byte-identical copies of the R1 release
images (/data/users/ali/rqa-20261006/release/r1/images), which both V1 and V2 sent to the models. This script verifies
every file against release_r1/images.json and writes image_index.csv, SHA256SUMS and README.md next to them.

python3 experiments/robolab_vqa/v2/export_images.py [--root artifacts/robolab_vqa_20261006]
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

VIEWS = ("wrist_cam", "over_shoulder_left_camera", "over_shoulder_right_camera")
VIEW_LABEL = {"wrist_cam": "wrist", "over_shoulder_left_camera": "left exterior", "over_shoulder_right_camera": "right exterior"}


def read_jsonl(path: Path) -> list[dict]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt") as f:
        return [json.loads(line) for line in f if line.strip()]


def query_images(q: dict) -> list[str]:
    ids = [v["image_id"] for v in q.get("view_paths_and_sha256") or []]
    return ids or list((q.get("image_files") or {}).keys())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=Path("artifacts/robolab_vqa_20261006"))
    args = ap.parse_args()
    root = args.root
    out = root / "model_input_images"
    images = json.loads((root / "release_r1/images.json").read_text())

    bad, sizes = [], {}
    for image_id, meta in images.items():
        data = (out / meta["path"]).read_bytes()
        sizes[image_id] = len(data)
        if hashlib.sha256(data).hexdigest() != meta["png_sha256"]:
            bad.append(image_id)
    extra = sorted({p.name for p in (out / "images").iterdir()} - {Path(m["path"]).name for m in images.values()})
    if bad or extra:
        sys.exit(f"hash mismatch: {bad[:5]} ({len(bad)}); files not in images.json: {extra[:5]} ({len(extra)})")

    use = defaultdict(lambda: {"v1": set(), "v2": set(), "v1_tests": set(), "v2_kinds": set(), "fixtures": set()})
    frames: dict[str, dict] = {}
    for q in read_jsonl(root / "release_r1/query_manifest.jsonl.gz"):
        for i in query_images(q):
            use[i]["v1"].add(q["query_id"])
            use[i]["v1_tests"].add(f"{q['test']}-{q['bank']}" if q["family"] == "original" else f"{q['test']}-{q['family']}")
        if query_images(q):
            frames.setdefault(q["frame_id"], {k: q.get(k) for k in ("scene_id", "physical_start_id", "bank", "observed_time_s",
                                                                  "source_episode_id")})
    for q in read_jsonl(root / "release_r2_final/query_manifest.jsonl.gz"):
        for i in query_images(q):
            use[i]["v2"].add(q["query_id"])
            kind = f"B2-{q['condition']}" if q["kind"] == "B2" else f"C2-{q['bank']}"
            use[i]["v2_kinds"].add(kind if q["family"] == "original" else f"{kind}-{q['family']}")
    for name in ("release_r1/dev_fixtures.jsonl", "release_r2_final/dev_fixtures.jsonl"):
        for q in read_jsonl(root / name):
            for i in query_images(q):
                use[i]["fixtures"].add(q["query_id"])

    rows = []
    for image_id, meta in sorted(images.items(), key=lambda kv: (kv[1]["provenance"][0]["frame_id"],
                                                                 VIEWS.index(kv[1]["provenance"][0]["view"]))):
        u = use[image_id]
        groups = [g for g, ok in (("V1 evaluation", u["v1"]), ("V2 evaluation", u["v2"]), ("qualification fixtures", u["fixtures"])) if ok]
        frame_ids = [p["frame_id"] for p in meta["provenance"]]
        f0 = frames.get(frame_ids[0], {})
        rows.append({"file": meta["path"], "image_id": image_id, "view": meta["provenance"][0]["view"], "frame_id": ";".join(frame_ids),
                     "scene_id": f0.get("scene_id") or frame_ids[0].split("-")[1], "physical_start_id": f0.get("physical_start_id") or "",
                     "bank": f0.get("bank") or "development", "observed_time_s": f0.get("observed_time_s", ""),
                     "frame_index": ";".join(str(p.get("frame_index", "")) for p in meta["provenance"]),
                     "width": meta["width"], "height": meta["height"], "bytes": sizes[image_id], "png_sha256": meta["png_sha256"],
                     "raw_rgb_sha256": meta["raw_rgb_sha256"], "array_sha256": meta.get("array_sha256", ""), "used_in": "; ".join(groups),
                     "v1_query_ids_per_readout": len(u["v1"]), "v1_tests": ";".join(sorted(u["v1_tests"])),
                     "v2_query_ids_per_readout": len(u["v2"]), "v2_tests": ";".join(sorted(u["v2_kinds"])),
                     "qualification_fixtures": ";".join(sorted(u["fixtures"])),
                     "source_recording": ";".join(sorted({p["source"] for p in meta["provenance"]}))})
    unused = [r["image_id"] for r in rows if not r["used_in"]]
    if unused:
        sys.exit(f"images not referenced by any query: {unused[:5]}")

    with open(out / "image_index.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    (out / "SHA256SUMS").write_text("".join(f"{r['png_sha256']}  {r['file']}\n" for r in rows))

    sets = defaultdict(dict)
    for r in rows:
        sets[r["frame_id"]][r["view"]] = r
    order = {"V1 evaluation; V2 evaluation": 0, "V1 evaluation": 1, "qualification fixtures": 2}
    keyed = sorted(sets.items(), key=lambda kv: (order.get(next(iter(kv[1].values()))["used_in"], 9), kv[0]))
    count = defaultdict(int)
    for r in rows:
        count[r["used_in"]] += 1
    total_mb = sum(r["bytes"] for r in rows) / 1e6
    lines = [
        "# RQA-20261006 exact model-input images (V1 and V2)", "",
        f"These {len(rows)} lossless RGB PNG files ({total_mb:.1f} MB) are byte-identical to the images sent to the models in "
        "RQA V1 (`r1-20261006`) and V2 (`r2-final-20261007`). Durable source on the cluster: "
        "`/data/users/ali/rqa-20261006/release/r1/images/` (PVC `211247-prod-pvc`). V2 reused the R1 images unchanged; its "
        "release records `image_root` = the R1 release.", "",
        "| Used in | Images | View sets |", "|---|---:|---:|",
        *[f"| {k} | {v} | {v // 3} |" for k, v in sorted(count.items(), key=lambda kv: order.get(kv[0], 9))], "",
        "- **V1 and V2 evaluation:** S1/S3/S4, 24 initial and 48 fixed secondary view sets.",
        "- **V1 evaluation only:** S5, 8 initial and 16 secondary view sets (no V2 queries).",
        "- **Qualification fixtures only:** 4 development view sets used for the mechanical qualification calls, never "
        "scored.", "",
        "Every view set has three views, always sent in the order wrist, left exterior, right exterior.",
        "- **Initial frames:** 1280×720 per view, from each start's cached first policy observation (`first_obs.npz`), "
        "shared by every original cell of that start.",
        "- **Secondary frames:** decoded losslessly from the recorded execution composite video. The wrist view is "
        "640×360 and each exterior view 320×180.",
        "- Each readout's own unchanged image processor did any resizing at inference.", "",
        "**Paths.** Every `view_paths_and_sha256[].path` (and V2 fixture `image_files` path) in "
        "[`release_r1/query_manifest.jsonl.gz`](../release_r1/query_manifest.jsonl.gz) and "
        "[`release_r2_final/query_manifest.jsonl.gz`](../release_r2_final/query_manifest.jsonl.gz) resolves relative to "
        "this folder. File names are content IDs: `img-` plus the first 24 hex digits of the raw RGB SHA256.", "",
        "**Verification.** Run `shasum -a 256 -c SHA256SUMS` (or `sha256sum -c SHA256SUMS`) in this folder. "
        "[`image_index.csv`](image_index.csv) gives, for each image, its PNG, raw-RGB and array hashes, frame, view, "
        "scene, start, bank, source recording, and the V1/V2 tests and number of query IDs that used it. Query counts are "
        "per readout: V1 ran four readouts and V2 three.", "",
        "Regenerate the index with `python3 experiments/robolab_vqa/v2/export_images.py` (CPU, standard library only). It "
        "also re-verifies every file against [`release_r1/images.json`](../release_r1/images.json).", "",
        "## View sets", "",
        "| View set (frame) | Scene | Start | Bank | Time (s) | Used in | V2 tests | Wrist | Left exterior | Right exterior |",
        "|---|---|---|---|---:|---|---|---|---|---|"]
    for frame_id, views in keyed:
        r0 = next(iter(views.values()))
        links = [f"[{VIEW_LABEL[v]}]({views[v]['file']})" if v in views else "—" for v in VIEWS]
        t = r0["observed_time_s"]
        lines.append(f"| `{frame_id}` | {r0['scene_id']} | {r0['physical_start_id'] or '—'} | {r0['bank']} | "
                     f"{'' if t == '' else f'{float(t):.2f}'} | {r0['used_in']} | {r0['v2_tests'].replace(';', ', ') or '—'} | "
                     + " | ".join(links) + " |")
    (out / "README.md").write_text("\n".join(lines) + "\n")
    print(json.dumps({"images": len(rows), "view_sets": len(sets), "mb": round(total_mb, 1), "by_use": dict(count)}))


if __name__ == "__main__":
    main()
