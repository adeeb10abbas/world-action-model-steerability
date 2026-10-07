"""V2 answerability review: blinded packet, review-form ingestion, ledger and masks (CPU only).

python -m experiments.robolab_vqa.v2.review packet --release <r2>/release.json --output <packet-dir>
python -m experiments.robolab_vqa.v2.review ingest --packet <packet-dir> --forms <form.csv>[,<form.csv>...] --output <ledger-dir>

The packet hides model identity/answers, action outcomes and frame-selection provenance (opaque review IDs, shuffled
by hash). Reviewers answer neutral questions per view set; the simulator key lives in <packet>/key/ and is only used by
`ingest` after the forms are complete. Machine (agent) reviews must use reviewer_type=machine.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

import numpy as np

from .. import common as C
from .. import labels as L
from . import config as V
from .scoring import review_answerable

PAIR = {"S1": ("rubiks_cube", "bowl", "Rubik's cube", "bowl"),
        "S3": ("butter", "raisin_box", "butter box", "raisin box"),
        "S4": ("mustard_bottle", "raisin_box", "mustard bottle", "raisin box")}
GOAL_REL = {"L": "left", "R": "right", "F": "in_front", "B": "behind"}
FORM_COLUMNS = ["review_id", "reviewer_id", "reviewer_type", "objects_identifiable", "lateral_relation",
                "on_top_supported", "target_on_table", "transit_or_gripper", "occlusion_or_other_ambiguity", "confidence", "notes"]
ALLOWED = {"objects_identifiable": {"yes", "no"},
           "lateral_relation": {"left", "right", "in_front", "behind", "diagonal_ambiguous", "cannot_tell"},
           "on_top_supported": {"yes", "no", "cannot_tell", "na"}, "target_on_table": {"yes", "no", "cannot_tell", "na"},
           "transit_or_gripper": {"yes", "no", "cannot_tell"},
           "occlusion_or_other_ambiguity": {"none", "occlusion", "boundary", "other"},
           "confidence": {"high", "medium", "low"}, "reviewer_type": {"human", "machine"}}


def review_id(frame_id: str) -> str:
    return "RV-" + C.sha256_text(f"6106|v2review|{frame_id}")[:10]


def axis_dirs(camera: dict) -> dict:
    p0 = np.array([0.45, 0.0, 0.02])
    uv, _ = L.project(np.stack([p0, p0 + [0.10, 0, 0], p0 + [0, 0.10, 0]]), camera)
    far, left = uv[1] - uv[0], uv[2] - uv[0]
    return {"farther": far / np.linalg.norm(far), "left": left / np.linalg.norm(left)}


def draw_legend(draw, x0: int, y0: int, dirs: dict | None, font=None) -> None:
    cx, cy, r = x0 + 110, y0 + 110, 80
    if dirs is None:
        draw.text((x0 + 10, y0 + 60), "wrist camera moves\nwith the gripper:\nno fixed legend", fill=(0, 0, 0))
        return
    for key, color in (("left", (200, 0, 0)), ("farther", (0, 0, 200))):
        d = dirs[key]
        ex, ey = cx + r * d[0], cy + r * d[1]
        draw.line([(cx, cy), (ex, ey)], fill=color, width=4)
        ang = math.atan2(d[1], d[0])
        for da in (2.6, -2.6):
            draw.line([(ex, ey), (ex + 14 * math.cos(ang + da), ey + 14 * math.sin(ang + da))], fill=color, width=4)
    draw.text((x0 + 10, y0 + 205), "red arrow = robot LEFT", fill=(200, 0, 0))
    draw.text((x0 + 10, y0 + 222), "blue arrow = FARTHER from robot", fill=(0, 0, 200))
    draw.text((x0 + 10, y0 + 245), "(right = opposite of LEFT;\n in front = closer to robot)", fill=(0, 0, 0))


def build_packet(release_path: Path, out: Path) -> dict:
    from PIL import Image, ImageDraw

    rel = C.load_json(release_path)
    r1 = Path(rel["image_root"])
    frames = C.load_json(r1 / "frames.json")["frames"]
    images = C.load_json(r1 / "images.json")
    rows = C.read_jsonl(release_path.parent / "query_manifest.jsonl")
    r1rows = {r["query_id"]: r for r in C.read_jsonl(r1 / "query_manifest.jsonl")}
    catalog = C.load_catalog()
    goals = {s: [g for g in catalog["goals"] if g["scene_id"] == s] for s in V.SCENES}
    fids = sorted({r["frame_id"] for r in rows if r["kind"] == "C2" and r["bank"] in ("initial", "secondary")})
    assert len(fids) == 72
    (out / "sheets").mkdir(parents=True, exist_ok=True)
    (out / "views").mkdir(exist_ok=True)
    (out / "key").mkdir(exist_ok=True)
    order = sorted(fids, key=review_id)
    key_labels, frame_map, form_rows, item_count = [], {}, [], 0
    for fid in order:
        fr = frames[fid]
        rid = review_id(fid)
        frame_map[rid] = fid
        scene = fr["scene_id"]
        secondary = fr["bank"] == "secondary"
        scale = 2 if secondary else 1
        views = []
        for v in C.VIEW_KEYS:
            im = Image.open(r1 / images[fr["views"][v]]["path"]).convert("RGB")
            im.save(out / "views" / f"{rid}_{C.VIEW_SHORT[v]}.png")
            views.append((v, im.resize((im.width * scale, im.height * scale), Image.NEAREST)))
        W = max(im.width for _, im in views) + 300
        H = sum(im.height + 40 for _, im in views) + 230
        sheet = Image.new("RGB", (W, H), (255, 255, 255))
        d = ImageDraw.Draw(sheet)
        y = 10
        for v, im in views:
            label = {"wrist_cam": "Wrist camera", "over_shoulder_left_camera": "Left exterior camera",
                     "over_shoulder_right_camera": "Right exterior camera"}[v]
            d.text((10, y), f"{label} ({im.width // scale}x{im.height // scale} evaluation pixels"
                            f"{', shown 2x pixel-replicated' if scale == 2 else ''})", fill=(0, 0, 0))
            sheet.paste(im, (10, y + 18))
            dirs = None if (v == "wrist_cam" and secondary) else axis_dirs(fr["cameras"][v])
            draw_legend(d, im.width + 20, y + 18, dirs)
            y += im.height + 40
        t, ref, tn, rn = PAIR[scene]
        qs = [f"Review {rid}. Objects: TARGET = {tn}, REFERENCE = {rn}. Robot frame: left/right from the robot's viewpoint; "
              "in front = closer to the robot; behind = farther.",
              f"Q1 Are the {tn} and the {rn} both identifiable? (yes/no)",
              f"Q2 Where is the {tn} relative to the {rn} (dominant horizontal direction)? left / right / in_front / behind / "
              "diagonal_ambiguous / cannot_tell",
              (f"Q3 Is the {tn} resting on top of and supported by the {rn}? yes/no/cannot_tell   "
               f"Q4 Is the {tn} resting on the table? yes/no/cannot_tell") if scene != "S1" else "Q3/Q4: na for this scene",
              "Q5 Is either object touching/held by the gripper or visibly in transit? yes/no/cannot_tell",
              "Q6 Occlusion/boundary/other ambiguity? none/occlusion/boundary/other.  Q7 Confidence: high/medium/low"]
        for i, q in enumerate(qs):
            d.text((10, int(y + 20 * i)), q, fill=(0, 0, 0))
        sheet.save(out / "sheets" / f"{rid}.png")
        form_rows.append({"review_id": rid, "reviewer_id": "", "reviewer_type": "", "objects_identifiable": "", "lateral_relation": "",
                          "on_top_supported": "na" if scene == "S1" else "", "target_on_table": "na" if scene == "S1" else "",
                          "transit_or_gripper": "", "occlusion_or_other_ambiguity": "", "confidence": "", "notes": ""})
        for g in goals[scene]:
            item_count += 1
            a_lab = r1rows[f"A.{fr['bank']}.{fid}.{g['goal_id']}.target_subject"]
            tf = next(i for i in catalog["original_instructions"] if i["scene"] == scene and i["goal"] == g["goal_id"] and i["form"] == "S")
            c_lab = r1rows[f"C.{fr['bank']}.{fid}.{tf['prompt_id']}"]
            key_labels.append({"review_id": rid, "frame_id": fid, "bank": fr["bank"], "scene_id": scene, "goal_id": g["goal_id"],
                               "gold_A": a_lab["gold_answer"], "gold_C": c_lab["gold_answer"], "r1_answerable_A": a_lab["answerable"],
                               "r1_answerable_C": c_lab["answerable"], "r1_exclusion_A": a_lab["exclusion_reason"],
                               "r1_exclusion_C": c_lab["exclusion_reason"]})
    with open(out / "review_form_blank.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FORM_COLUMNS)
        w.writeheader()
        w.writerows(form_rows)
    r1audit = C.load_json(V.R1_RELEASE_DIR / "audit/audit_manifest.json") if (V.R1_RELEASE_DIR / "audit/audit_manifest.json").exists() else {}
    second = sorted(review_id(f) for f in r1audit.get("second_review_sample_frames", []) if f in fids)
    C.write_json_atomic(out / "key" / "frame_map.json", frame_map)
    C.write_json_atomic(out / "key" / "labels.json", key_labels)
    (out / "REVIEW_INSTRUCTIONS.md").write_text(INSTRUCTIONS.format(n_frames=len(order), n_items=item_count, second=", ".join(second)))
    manifest = {"study_id": C.STUDY_ID, "design_version": V.DESIGN_VERSION, "created_utc": C.utc_now(),
                "release_content_sha256": rel["release_content_sha256"], "frames": len(order), "frame_goal_items": item_count,
                "second_review_fixed_r1_sample": second, "blinding": "no model names/answers/outcomes/selection provenance in sheets "
                "or form; key/ holds frame map and simulator labels for post-review comparison only",
                "files": {str(p.relative_to(out)): C.sha256_file(p) for p in sorted(out.rglob("*")) if p.is_file()}}
    manifest["packet_sha256"] = C.canonical_sha256(manifest["files"])
    C.write_json_atomic(out / "packet_manifest.json", manifest)
    return manifest


INSTRUCTIONS = """# RQA V2 answerability review packet

{n_frames} view sets, {n_items} frame-goal relations. Fill `review_form_blank.csv` (one row per review ID) **before**
looking at anything in `key/`. Sheets show the exact evaluation-resolution views (secondary views are also shown 2x
pixel-replicated; the original files are in `views/`). Arrows beside each view show the robot's LEFT and FARTHER
directions derived from camera calibration; the moving wrist camera of saved-rollout frames has no fixed legend.

Answer for TARGET relative to REFERENCE in the robot frame: left/right from the robot's viewpoint, in_front = closer to
the robot, behind = farther. Use `diagonal_ambiguous` when the dominant direction is near 45 degrees and `cannot_tell`
when it is not visible. Q3/Q4 (support, table contact) apply to scenes with a raisin box. Mark `transit_or_gripper=yes`
if either object touches the gripper or appears in motion. Confidence low means you would not rely on the answer.

Protocol: reviewer 1 completes all rows; reviewer 2 completes all flagged rows (any ambiguity, low confidence, or a
post-comparison discrepancy) plus the fixed second-review sample: {second}. Resolve disagreements without model
responses; unresolved items are unanswerable. Set reviewer_type to human or machine truthfully.

Rescore without new inference:
`python -m experiments.robolab_vqa.v2.review ingest --packet <this dir> --forms <form1.csv>,<form2.csv> --output <ledger dir>`
then `python -m experiments.robolab_vqa.v2.analyze ... --mask <ledger dir>/mask.json`.
"""


def ingest(packet: Path, forms: list[Path], out: Path) -> dict:
    labels = C.load_json(packet / "key" / "labels.json")
    reviews: dict[str, list[dict]] = {}
    problems = []
    for path in forms:
        with open(path) as f:
            for row in csv.DictReader(f):
                for k, allowed in ALLOWED.items():
                    if row.get(k, "") not in allowed:
                        problems.append(f"{path.name}:{row.get('review_id')}:{k}={row.get(k)!r}")
                reviews.setdefault(row["review_id"], []).append(row)
    if problems:
        raise ValueError(f"invalid review values: {problems[:20]}")
    ledger = []
    for lab in labels:
        for rv in reviews.get(lab["review_id"], []):
            scene, goal = lab["scene_id"], lab["goal_id"]
            lateral = rv["lateral_relation"]
            if goal == "TOP":
                discernible = rv["on_top_supported"] in ("yes", "no")
                proposed_a = {"yes": "yes", "no": "no"}.get(rv["on_top_supported"])
                proposed_c = proposed_a
                support = "yes" if discernible else "no"
                proposed_rel = {"yes": "on_top_supported", "no": "not_on_top"}.get(rv["on_top_supported"], "none")
            else:
                discernible = lateral in GOAL_REL.values()
                proposed_a = ("yes" if lateral == GOAL_REL[goal] else "no") if discernible else None
                support = "na" if scene == "S1" else ("yes" if rv["target_on_table"] in ("yes", "no") else "no")
                if scene == "S1":
                    proposed_c = proposed_a
                else:
                    proposed_c = (("yes" if (proposed_a == "yes" and rv["target_on_table"] == "yes") else "no")
                                  if discernible and support == "yes" else None)
                proposed_rel = lateral
            ambiguity = rv["occlusion_or_other_ambiguity"]
            if goal != "TOP" and lateral == "diagonal_ambiguous":
                ambiguity = "boundary" if ambiguity == "none" else ambiguity
            row = {"review_id": lab["review_id"], "frame_id": lab["frame_id"], "bank": lab["bank"], "scene_id": scene, "goal_id": goal,
                   "reviewer_id": rv["reviewer_id"], "reviewer_type": rv["reviewer_type"],
                   "objects_identifiable": rv["objects_identifiable"], "relation_discernible": "yes" if discernible else "no",
                   "support_visible": support, "ambiguity": ambiguity, "transit_or_gripper": rv["transit_or_gripper"],
                   "confidence": rv["confidence"], "proposed_visible_relation": proposed_rel,
                   "proposed_label_A": proposed_a, "proposed_label_C": proposed_c, "gold_A": lab["gold_A"], "gold_C": lab["gold_C"],
                   "discrepancy_A": None if proposed_a is None else proposed_a != lab["gold_A"],
                   "discrepancy_C": None if proposed_c is None else proposed_c != lab["gold_C"],
                   "r1_answerable_A": lab["r1_answerable_A"], "r1_answerable_C": lab["r1_answerable_C"], "notes": rv.get("notes", "")}
            for test in ("A", "C"):
                ok, why = review_answerable(row, test)
                row[f"review_answerable_{test}"] = ok
                row[f"review_exclusion_{test}"] = ";".join(why) or None
            ledger.append(row)
    out.mkdir(parents=True, exist_ok=True)
    keys = list(ledger[0]) if ledger else []
    with open(out / "review_ledger.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(ledger)
    types = sorted({r["reviewer_type"] for r in ledger})
    reviewed_frames = {r["frame_id"] for r in ledger}
    mask = {"study_id": C.STUDY_ID, "created_utc": C.utc_now(), "reviewer_types": types,
            "human_coverage": {"frames": len({r["frame_id"] for r in ledger if r["reviewer_type"] == "human"}), "of": len({l['frame_id'] for l in labels})},
            "machine_coverage": {"frames": len({r["frame_id"] for r in ledger if r["reviewer_type"] == "machine"}), "of": len({l['frame_id'] for l in labels})},
            "complete": len(reviewed_frames) == len({l["frame_id"] for l in labels}),
            "rule": "revised = R1 original mask AND review-answerable (scoring.review_answerable); strict also excludes discrepancies",
            "items": {}}
    for r in ledger:
        k = f"{r['frame_id']}|{r['goal_id']}"
        e = mask["items"].setdefault(k, {"A": True, "C": True, "A_strict": True, "C_strict": True, "reviewers": []})
        e["reviewers"].append(f"{r['reviewer_type']}:{r['reviewer_id']}")
        for test in ("A", "C"):
            e[test] &= bool(r[f"review_answerable_{test}"])
            e[f"{test}_strict"] &= bool(r[f"review_answerable_{test}"]) and not bool(r[f"discrepancy_{test}"])
    C.write_json_atomic(out / "mask.json", mask)
    summary = {"ledger_rows": len(ledger), "frames_reviewed": len(reviewed_frames), "reviewer_types": types,
               "review_answerable_A": sum(1 for r in ledger if r["review_answerable_A"]),
               "review_answerable_C": sum(1 for r in ledger if r["review_answerable_C"]),
               "discrepancy_A": sum(1 for r in ledger if r["discrepancy_A"]), "discrepancy_C": sum(1 for r in ledger if r["discrepancy_C"]),
               "mask_sha256": C.sha256_file(out / "mask.json"), "ledger_sha256": C.sha256_file(out / "review_ledger.csv")}
    C.write_json_atomic(out / "ingest_summary.json", summary)
    return summary


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("packet")
    p.add_argument("--release", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    q = sub.add_parser("ingest")
    q.add_argument("--packet", type=Path, required=True)
    q.add_argument("--forms", required=True)
    q.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    if args.cmd == "packet":
        m = build_packet(args.release, args.output)
        print(json.dumps({"packet_sha256": m["packet_sha256"], "frames": m["frames"], "items": m["frame_goal_items"],
                          "second_review": len(m["second_review_fixed_r1_sample"])}, indent=1))
    else:
        print(json.dumps(ingest(args.packet, [Path(x) for x in args.forms.split(",")], args.output), indent=1))


if __name__ == "__main__":
    sys.exit(main())
