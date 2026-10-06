"""Build the RQA-20261006 data release (images, gold labels, exact queries, audit packets). Cluster, CPU only.

python -m experiments.robolab_vqa.prepare --spec-dir docs/robolab-vqa-20261006 \
    --source-root /data/users/ali/rws-20260926 --inventory <inventory-dir> --output <release-dir> \
    --implementation-commit <git sha>

Outputs in <release-dir>:
  images/<image_id>.png         lossless RGB views (ids are content hashes; no labels in names)
  frames.json                   frame bindings (times, ticks, source attempts, view ids/hashes)
  payloads.jsonl                model payloads only (what the runner reads; no gold/hidden metadata)
  query_manifest.jsonl          full query rows (payload + gold + answerability + provenance)
  dev_fixtures.jsonl            six development fixture payloads (D00 material, non-catalog wording)
  audit/                        human answerability audit sheets and review CSV templates
  release.json                  hashes, counts, frozen settings, status
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np

from . import common as C
from . import labels as L
from . import prompts as P
from .inventory import COMPOSITE_HW, decode_frame


class ImageStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        (root / "images").mkdir(parents=True, exist_ok=True)
        self.index: dict[str, dict] = {}

    def add(self, array: np.ndarray, provenance: dict) -> str:
        from PIL import Image

        arr = np.ascontiguousarray(array, dtype=np.uint8)
        raw = C.raw_rgb_sha256(arr)
        image_id = "img-" + raw[:24]
        path = self.root / "images" / f"{image_id}.png"
        if image_id not in self.index:
            if not path.exists():
                Image.fromarray(arr, mode="RGB").save(path, format="PNG", optimize=False, compress_level=6)
            back = np.asarray(Image.open(path).convert("RGB"))
            if C.raw_rgb_sha256(back) != raw:
                raise RuntimeError(f"PNG round trip mismatch for {image_id}")
            self.index[image_id] = {"image_id": image_id, "path": f"images/{image_id}.png", "raw_rgb_sha256": raw,
                                    "array_sha256": C.array_sha256(arr), "png_sha256": C.sha256_file(path),
                                    "height": int(arr.shape[0]), "width": int(arr.shape[1]), "provenance": [provenance]}
        else:
            self.index[image_id]["provenance"].append(provenance)
        return image_id


def composite_views(frame: np.ndarray) -> dict[str, np.ndarray]:
    return {v: frame[sl] for v, sl in C.COMPOSITE_SLICES.items()}


def visibility(tick: dict, objects: list[str], cameras: dict, hw: dict, views: tuple[str, ...]) -> dict:
    out = {}
    for o in objects:
        vis = L.object_visibility(tick, o, {v: cameras[v] for v in views}, {v: hw[v] for v in views})
        out[o] = {"views": vis, "centre_visible_any": any(x["centre_in_image"] for x in vis.values()),
                  "views_considered": list(views)}
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec-dir", type=Path, default=C.SPEC_DIR)
    ap.add_argument("--source-root", type=Path, default=C.DEFAULT_SOURCE_ROOT)
    ap.add_argument("--inventory", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--implementation-commit", default="uncommitted")
    args = ap.parse_args()
    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    catalog = C.load_catalog(args.spec_dir)
    selection = C.load_frame_selection(args.spec_dir)
    protocol = C.load_protocol(args.spec_dir)
    inv = C.load_json(args.inventory / "inventory.json")
    sec_ticks = C.load_json(args.inventory / "secondary_ticks.json")
    starts = {s["physical_start_id"]: s for s in inv["starts"]}
    sec_inv = {s["frame_id"]: s for s in inv["secondary"]}
    goals = C.goals_by_scene(catalog)
    instr = C.instructions_by_scene(catalog)
    placement = catalog["placement_controls"]
    store = ImageStore(out)
    native_hw = {v: (720, 1280) for v in C.VIEW_KEYS}
    comp_hw = {v: (sl[0].stop - sl[0].start, sl[1].stop - sl[1].start) for v, sl in C.COMPOSITE_SLICES.items()}

    # ------------------------------------------------------------------ frames
    frames: dict[str, dict] = {}
    for sel in selection["initial"]:
        slot = sel["physical_start_id"]
        st = starts[slot]
        if st.get("primary_bank_status") != "verified_common_request0_observation":
            frames[sel["frame_id"]] = {**sel, "available": False, "unavailable_reason": st.get("primary_bank_status")}
            continue
        with np.load(args.source_root / "states" / slot / "first_obs.npz") as z:
            ids = {v: store.add(z[v], {"frame_id": sel["frame_id"], "view": v, "source": f"states/{slot}/first_obs.npz"})
                   for v in C.VIEW_KEYS}
        tick = C.load_json(args.inventory / "initial_ticks" / f"{slot}.json")
        frames[sel["frame_id"]] = {
            "frame_id": sel["frame_id"], "bank": "initial", "scene_id": sel["scene_id"], "physical_start_id": slot,
            "available": True, "requested_time_s": 0.0, "observed_time_s": 0.0, "tick": 0,
            "source": "cached request-0 first observation (states/<slot>/first_obs.npz), common to every original cell",
            "source_episode_id": None, "cells_verified": st["cells"]["cells"], "views": ids,
            "presentation": "native 720x1280 per view", "wrist_moving": False, "role_binding": st["role_binding"],
            "cameras": st["camera_calibration"], "_tick": tick}
    for sel in selection["secondary"]:
        si = sec_inv[sel["frame_id"]]
        if si.get("binding_status") != "bound":
            frames[sel["frame_id"]] = {**sel, "bank": "secondary", "available": False, "unavailable_reason": si.get("binding_status")}
            continue
        frame = decode_frame(Path(si["composite_uri"]), si["observed_tick"], *COMPOSITE_HW)
        if C.raw_rgb_sha256(frame) != si["composite_frame_sha256_recorded"]:
            raise RuntimeError(f"{sel['frame_id']}: composite hash mismatch")
        ids = {v: store.add(img, {"frame_id": sel["frame_id"], "view": v, "source": si["composite_uri"],
                                  "frame_index": si["observed_tick"]}) for v, img in composite_views(frame).items()}
        slot = sel["physical_start_id"]
        frames[sel["frame_id"]] = {
            "frame_id": sel["frame_id"], "bank": "secondary", "scene_id": sel["scene_id"], "physical_start_id": slot,
            "available": True, "requested_time_s": sel["requested_time_s"], "observed_time_s": si["observed_time_s"],
            "tick": si["observed_tick"], "horizon_fraction": sel["horizon_fraction"],
            "observation_after_last_executed_action": si["observation_after_last_executed_action"],
            "source": "lossless executed composite stream frame (libx264rgb qp0), split into its three policy views",
            "source_episode_id": sel["source_episode_id"], "source_attempt_id": si["attempt_id"],
            "source_model_id": sel["source_model_id"], "source_display_form": sel["source_display_form"],
            "source_goal_id": sel["source_goal_id"], "composite_frame_sha256": si["composite_frame_sha256_recorded"],
            "views": ids, "presentation": "policy-input composite resolution: wrist 360x640, exterior 180x320 each",
            "wrist_moving": True, "role_binding": starts[slot]["role_binding"], "cameras": starts[slot]["camera_calibration"],
            "_tick": sec_ticks[sel["frame_id"]]["tick"], "_tick0": sec_ticks[sel["frame_id"]]["tick0"]}

    # ------------------------------------------------------------------ gold labels per frame
    gold: dict[tuple, dict] = {}
    frame_flags: dict[str, dict] = {}
    for fid, fr in frames.items():
        if not fr.get("available"):
            continue
        scene, tick, rb = fr["scene_id"], fr["_tick"], fr["role_binding"]
        objects = list(tick["objects"].keys())
        views = C.VIEW_KEYS if fr["bank"] == "initial" else ("over_shoulder_left_camera", "over_shoulder_right_camera")
        hw = native_hw if fr["bank"] == "initial" else comp_hw
        vis = visibility(tick, objects, fr["cameras"], hw, views)
        grasp = L.grasp_state(tick, objects)
        ident = L.bowl_identity(fr["_tick0"], tick, rb) if (scene == "S5" and fr["bank"] == "secondary") else None
        frame_flags[fid] = {"visibility": vis, "gripper_contact": grasp, "bowl_identity": ident}
        for g in goals[scene]:
            lab = L.a_label(tick, scene, g, rb)
            gold[("A", fid, g["goal_id"])] = lab
            for item in instr[scene]:
                if item["goal"] == g["goal_id"]:
                    gold[("C", fid, item["prompt_id"])] = L.c_label(tick, scene, g, rb, item)
            if fr["bank"] == "initial":
                for item in placement:
                    if item["scene_id"] == scene and item["goal_id"] == g["goal_id"]:
                        gold[("C", fid, item["prompt_id"])] = L.c_label(tick, scene, g, rb, item)

    def answerability(test: str, fid: str, key: str, target: str, reference: str) -> tuple[bool, str | None, list[str]]:
        fr = frames[fid]
        lab = gold[(test, fid, key)]
        flags = frame_flags[fid]
        reasons = []
        if lab.get("boundary_flag"):
            reasons.append("cone_" + lab["boundary_reason"])
        for o in (lab["target_asset"], lab["reference_asset"]):
            if not flags["visibility"][o]["centre_visible_any"]:
                reasons.append(f"not_projected_in_presented_views_precheck:{o}")
        if flags["bowl_identity"] and flags["bowl_identity"]["both_moved"]:
            reasons.append("bowl_identity_not_followable_both_bowls_moved")
        if test == "C" and fr["bank"] == "secondary":
            if any(flags["gripper_contact"].get(o) for o in (lab["target_asset"], lab["reference_asset"])):
                reasons.append("target_or_reference_in_gripper_contact_final_arrangement_ambiguous")
        advisory = []
        if test == "A" and fr["bank"] == "secondary" and any(flags["gripper_contact"].get(o) for o in (lab["target_asset"], lab["reference_asset"])):
            advisory.append("gripper_contact_possible_occlusion")
        return (not reasons), (";".join(reasons) if reasons else None), advisory

    # ------------------------------------------------------------------ queries
    rows: list[dict] = []
    start_ref = {f["physical_start_id"]: f["views"] for f in frames.values() if f.get("bank") == "initial" and f.get("available")}

    def image_refs(segs: list[dict], fr: dict | None) -> list[dict]:
        refs = []
        for s in segs:
            if s["type"] == "image":
                meta = store.index[s["image_id"]]
                role = "current"
                if fr is not None and fr["bank"] == "secondary" and s["image_id"] in start_ref.get(fr["physical_start_id"], {}).values():
                    role = "start_reference"
                refs.append({"view": s["view"], "time_role": role, "image_id": s["image_id"], "path": meta["path"],
                             "raw_rgb_sha256": meta["raw_rgb_sha256"], "png_sha256": meta["png_sha256"],
                             "height": meta["height"], "width": meta["width"]})
        return refs

    def add(query_id, test, bank, family, scene, fr, goal_id, item_prompt_id, display_form, instruction, segs, pair_id,
            equivalence_status, gold_answer, answerable, exclusion_reason, provenance, advisory=None):
        rows.append({
            "query_id": query_id, "order_key": C.order_key(query_id), "test": test, "bank": bank, "family": family,
            "scene_id": scene, "physical_start_id": fr["physical_start_id"] if fr else None,
            "frame_id": fr["frame_id"] if fr else None, "source_episode_id": fr.get("source_episode_id") if fr else None,
            "requested_time_s": fr["requested_time_s"] if fr else None, "observed_time_s": fr["observed_time_s"] if fr else None,
            "view_paths_and_sha256": image_refs(segs, fr), "goal_id": goal_id, "original_prompt_id": item_prompt_id,
            "display_form": display_form, "instruction_utf8": instruction,
            "instruction_utf8_sha256": C.sha256_text(instruction) if instruction is not None else None,
            "segments": segs, "full_prompt": P.full_prompt_text(segs), "full_prompt_sha256": C.sha256_text(P.full_prompt_text(segs)),
            "pair_id": pair_id, "equivalence_status": equivalence_status, "gold_answer": gold_answer,
            "answerable": answerable, "exclusion_reason": exclusion_reason, "advisory_flags": advisory or [],
            "annotation_version": L.LABEL_VERSION, "label_provenance": provenance,
            "main_equivalent_wording_pool": scene in C.MAIN_POOL_SCENES})

    vocab_by_scene = {s: instr[s][0]["object_vocabulary"] for s in C.SCENES}
    # text-only B (36 + 16) and no-image C (36)
    for item in catalog["original_instructions"]:
        scene, gid = item["scene"], item["goal"]
        segs = P.build_segments(test="B", instruction=item["prompt"], objects=vocab_by_scene[scene])
        add(f"B.no_image.{item['prompt_id']}", "B", "no_image", "original", scene, None, gid, item["prompt_id"],
            item["display_form"], item["prompt"], segs, f"B.no_image.{scene}-{gid}", item["equivalence_status"],
            item["gold_B"], True, None, {"source": "question_catalog gold_B"})
        segs = P.build_segments(test="C", instruction=item["prompt"])
        add(f"C.no_image.{item['prompt_id']}", "C", "no_image", "original", scene, None, gid, item["prompt_id"],
            item["display_form"], item["prompt"], segs, f"C.no_image.{scene}-{gid}", item["equivalence_status"],
            None, None, "reused_against_initial_frame_labels_at_analysis", {"reuse": "scored against each initial frame's C label"})
    for item in placement:
        scene, gid = item["scene_id"], item["goal_id"]
        segs = P.build_segments(test="B", instruction=item["prompt"], objects=vocab_by_scene[scene])
        add(f"PB.no_image.{item['prompt_id']}", "B", "no_image", "placement", scene, None, gid, item["prompt_id"],
            item["display_form"], item["prompt"], segs, f"PB.no_image.{scene}-{gid}", "clause_order_control",
            item["gold_B"], True, None, {"source": "question_catalog placement gold_B"})
    # image banks
    for fid, fr in frames.items():
        if not fr.get("available"):
            continue
        scene, bank = fr["scene_id"], fr["bank"]
        s5_sec = scene == "S5" and bank == "secondary"
        common_kw = dict(current=fr["views"], wrist_moving=fr["wrist_moving"], current_time_s=fr["observed_time_s"],
                         start_reference=start_ref[fr["physical_start_id"]] if s5_sec else None)
        for g in goals[scene]:
            lab = gold[("A", fid, g["goal_id"])]
            ok, why, adv = answerability("A", fid, g["goal_id"], g["target"], g["reference"])
            for q in g["scene_questions"]:
                segs = P.build_segments(test="A", question_text=q["question"], **common_kw)
                add(f"A.{bank}.{fid}.{g['goal_id']}.{q['form']}", "A", bank, "original", scene, fr, g["goal_id"], None,
                    q["form"], None, segs, f"A.{bank}.{fid}.{g['goal_id']}", "same_physical_predicate",
                    "yes" if lab["value"] else "no", ok, why, lab, adv)
            for item in [i for i in instr[scene] if i["goal"] == g["goal_id"]]:
                lab = gold[("C", fid, item["prompt_id"])]
                ok, why, adv = answerability("C", fid, item["prompt_id"], None, None)
                segs = P.build_segments(test="C", instruction=item["prompt"], **common_kw)
                add(f"C.{bank}.{fid}.{item['prompt_id']}", "C", bank, "original", scene, fr, g["goal_id"], item["prompt_id"],
                    item["display_form"], item["prompt"], segs, f"C.{bank}.{fid}.{scene}-{g['goal_id']}",
                    item["equivalence_status"], "yes" if lab["value"] else "no", ok, why, lab, adv)
                if bank == "initial":
                    segs = P.build_segments(test="B", instruction=item["prompt"], objects=vocab_by_scene[scene], **common_kw)
                    add(f"B.{bank}.{fid}.{item['prompt_id']}", "B", bank, "original", scene, fr, g["goal_id"], item["prompt_id"],
                        item["display_form"], item["prompt"], segs, f"B.{bank}.{fid}.{scene}-{g['goal_id']}",
                        item["equivalence_status"], item["gold_B"], True, None, {"source": "question_catalog gold_B"})
            if bank == "initial":
                for item in [p for p in placement if p["scene_id"] == scene and p["goal_id"] == g["goal_id"]]:
                    segs = P.build_segments(test="B", instruction=item["prompt"], objects=vocab_by_scene[scene], **common_kw)
                    add(f"PB.{bank}.{fid}.{item['prompt_id']}", "B", bank, "placement", scene, fr, g["goal_id"], item["prompt_id"],
                        item["display_form"], item["prompt"], segs, f"PB.{bank}.{fid}.{scene}-{g['goal_id']}",
                        "clause_order_control", item["gold_B"], True, None, {"source": "question_catalog placement gold_B"})
                    lab = gold[("C", fid, item["prompt_id"])]
                    ok, why, adv = answerability("C", fid, item["prompt_id"], None, None)
                    segs = P.build_segments(test="C", instruction=item["prompt"], **common_kw)
                    add(f"PC.{bank}.{fid}.{item['prompt_id']}", "C", bank, "placement", scene, fr, g["goal_id"], item["prompt_id"],
                        item["display_form"], item["prompt"], segs, f"PC.{bank}.{fid}.{scene}-{g['goal_id']}",
                        "clause_order_control", "yes" if lab["value"] else "no", ok, why, lab, adv)
    rows.sort(key=lambda r: (0 if r["bank"] in ("initial", "no_image") else 1, r["order_key"]))
    counts = {}
    for r in rows:
        k = f"{r['family']}|{r['test']}|{r['bank']}"
        counts[k] = counts.get(k, 0) + 1
    planned = {"original|A|initial": 192, "original|B|no_image": 36, "original|B|initial": 288, "original|C|initial": 288,
               "placement|B|no_image": 16, "placement|B|initial": 128, "placement|C|initial": 128,
               "original|C|no_image": 36, "original|A|secondary": 384, "original|C|secondary": 576}
    if counts != planned:
        raise RuntimeError(f"query counts {counts} != planned {planned}")

    # ------------------------------------------------------------------ dev fixtures (D00 / development material only)
    dev = []
    dev_frames = {}
    for slot in ("S1-D00", "S3-D00", "S4-D00"):
        with np.load(args.source_root / "states" / slot / "first_obs.npz") as z:
            dev_frames[slot] = {v: store.add(z[v], {"frame_id": f"dev-{slot}", "view": v, "source": f"states/{slot}/first_obs.npz"})
                                for v in C.VIEW_KEYS}
    dev_ep = args.source_root / "runs/episodes/RWS-N3-S1-D00-L-D/COMPLETE.json"
    dev_att = Path(C.load_json(dev_ep)["attempt_dir"])
    dev_hash = C.load_json(dev_att / "stream_frame_hashes.json")["composite"]
    dframe = decode_frame(Path(dev_hash["uri"]), 225, *COMPOSITE_HW)
    if C.raw_rgb_sha256(dframe) != dev_hash["frame_sha256"][225]:
        raise RuntimeError("dev composite frame hash mismatch")
    dev_frames["S1-D00-dev225"] = {v: store.add(img, {"frame_id": "dev-S1-D00-tick225", "view": v, "source": dev_hash["uri"]})
                                   for v, img in composite_views(dframe).items()}
    fixtures = [
        ("F1", "A", dict(question_text="Is the banana to the left of the bowl?", current=dev_frames["S1-D00"])),
        ("F2", "B", dict(instruction="Put the banana in front of the bowl", objects=vocab_by_scene["S1"])),
        ("F3", "B", dict(instruction="Place the raisin box to the left of the butter box.", objects=vocab_by_scene["S3"],
                         current=dev_frames["S3-D00"])),
        ("F4", "C", dict(instruction="Put the raisin box behind the mustard bottle.", current=dev_frames["S4-D00"])),
        ("F5", "C", dict(instruction="Put the banana behind the bowl")),
        ("F6", "A", dict(question_text="Is the banana to the right of the Rubik's cube?", current=dev_frames["S1-D00-dev225"],
                         wrist_moving=True, current_time_s=15.0)),
    ]
    for fx_id, test, kw in fixtures:
        segs = P.build_segments(test=test, **kw)
        dev.append({"query_id": f"DEV.{fx_id}", "test": test, "bank": "dev", "segments": segs,
                    "full_prompt": P.full_prompt_text(segs), "full_prompt_sha256": C.sha256_text(P.full_prompt_text(segs)),
                    "view_paths_and_sha256": image_refs(segs, None),
                    "purpose": "loading, image reception, output format, latency and memory; no accuracy gate"})

    # ------------------------------------------------------------------ write
    payload_fields = ("query_id", "order_key", "test", "bank", "segments", "full_prompt_sha256")
    payloads = [{k: r[k] for k in payload_fields} for r in rows]
    for p in payloads:
        p["image_files"] = {s["image_id"]: store.index[s["image_id"]]["path"] for s in p["segments"] if s["type"] == "image"}
    C.write_jsonl(out / "payloads.jsonl", payloads)
    C.write_jsonl(out / "dev_fixtures.jsonl", [{**d, "image_files": {s["image_id"]: store.index[s["image_id"]]["path"]
                                                                     for s in d["segments"] if s["type"] == "image"}} for d in dev])
    frames_out = {fid: {k: v for k, v in fr.items() if not k.startswith("_")} for fid, fr in frames.items()}
    C.write_json_atomic(out / "frames.json", {"frames": frames_out, "frame_flags": frame_flags})
    C.write_json_atomic(out / "images.json", store.index)
    content = {"payloads_sha256": C.sha256_file(out / "payloads.jsonl"), "frames_sha256": C.sha256_file(out / "frames.json"),
               "images_sha256": C.sha256_file(out / "images.json"),
               "gold_sha256": C.canonical_sha256([{k: r[k] for k in ("query_id", "gold_answer", "answerable", "exclusion_reason")} for r in rows]),
               "frozen_text": P.frozen_text_constants()}
    release_content_sha256 = C.canonical_sha256(content)
    for r in rows:
        r["release_sha256"] = release_content_sha256
    C.write_jsonl(out / "query_manifest.jsonl", rows)
    write_audit(out, rows, frames, frame_flags, store)
    spec_hashes = {p.name: C.sha256_file(p) for p in sorted(Path(args.spec_dir).glob("*")) if p.is_file()}
    release = {
        "study_id": C.STUDY_ID, "protocol_version": C.PROTOCOL_VERSION, "implementation_version": C.IMPLEMENTATION_VERSION,
        "implementation_commit": args.implementation_commit, "created_utc": C.utc_now(),
        "status": "frozen_provisional_human_answerability_review_pending",
        "release_content_sha256": release_content_sha256, "content": content,
        "files": {name: C.sha256_file(out / name) for name in ("payloads.jsonl", "query_manifest.jsonl", "frames.json",
                                                                "images.json", "dev_fixtures.jsonl")},
        "spec_files_sha256": spec_hashes, "inventory_sha256": C.sha256_file(args.inventory / "inventory.json"),
        "source_root": str(args.source_root), "source_release_sha256": inv["release_json"]["sha256"],
        "counts": {"queries_by_family_test_bank": counts, "total": len(rows), "images": len(store.index),
                   "frames_available": sum(1 for f in frames.values() if f.get("available")),
                   "answerable_by_family_test_bank": _answerable_counts(rows), "dev_fixtures": len(dev)},
        "frozen_settings": {
            "order": "within each bank: sha256('6106|'+query_id); primary (initial + no_image) before secondary",
            "label_version": L.LABEL_VERSION,
            "label_rules": {"cone_deg": L.CONE_DEG, "boundary_deg": L.BOUNDARY_DEG, "center_min_m": L.CENTER_MIN_M,
                            "contact_force_n": L.CONTACT_FORCE_N, "support_cone_deg": L.SUPPORT_CONE_DEG,
                            "footprint_tolerance_m": L.FOOTPRINT_TOL_M, "bowl_identity_move_m": L.BOWL_IDENTITY_MOVE_M,
                            "A": "instantaneous named relation (support/nesting words included for TOP and S5)",
                            "C": "instruction-specific requested arrangement: relation + table support when the instruction "
                                 "says 'on the table'; TOP = centroid in reference footprint AND supported on reference; "
                                 "S5 DIR/TF stacked_on = pinned open-top containment AND contact; S5 RF literal "
                                 "on_top_supported = centroid in footprint AND supported (force cone); no dwell/speed/history",
                            "exclusions": "cone boundary (<5 deg) or centres <1 cm; object centre not projected in any presented "
                                          "view (automated pre-check, exterior views only for secondary frames); S5 secondary "
                                          "both bowls moved >2 cm; C secondary target/reference in gripper contact"},
            "visibility": "automated projection pre-check only; human answerability review pending",
            "presentation": {"initial": "three native 720x1280 RGB views (wrist, left, right) from the cached request-0 observation",
                             "secondary": "three views split from the lossless 540x640 executed composite stream "
                                          "(wrist 360x640; exterior 180x320) at the bound tick",
                             "s5_secondary": "start-time (t=0) reference views + current views, explicit time labels",
                             "multi_image": "native multi-image chat input; no panels, crops, overlays or enhancement",
                             "legend": "calibration-derived camera headers (wrist orientation stated only for the starting pose)"},
            "text": P.frozen_text_constants(),
            "decoding": {"temperature": 0.0, "greedy": True, "max_new_tokens": 256, "thinking": "disabled via native chat "
                         "template when the template supports it (Cosmos3-Edge enable_thinking=False)",
                         "self_consistency": False, "retries": "infrastructure only; never answer-conditioned"},
        },
        "provenance_note": "Gold labels computed from saved simulator tick records; no model answers, outcomes or forecast "
                           "labels were read. Human answerability audit packets are in audit/; review not performed.",
    }
    C.write_json_atomic(out / "release.json", release)
    print(json.dumps({"release_content_sha256": release_content_sha256, "release_json_sha256": C.sha256_file(out / "release.json"),
                      "counts": release["counts"]}, indent=1))


def _answerable_counts(rows: list[dict]) -> dict:
    out: dict = {}
    for r in rows:
        k = f"{r['family']}|{r['test']}|{r['bank']}"
        a = out.setdefault(k, {"proposed": 0, "answerable": 0, "excluded": 0, "reused": 0})
        a["proposed"] += 1
        if r["answerable"] is True:
            a["answerable"] += 1
        elif r["answerable"] is False:
            a["excluded"] += 1
        else:
            a["reused"] += 1
    return out


def write_audit(out: Path, rows: list[dict], frames: dict, flags: dict, store: ImageStore) -> None:
    """Human answerability audit sheets (labels + calibration overlays). Not model inputs."""
    from PIL import Image, ImageDraw

    adir = out / "audit"
    (adir / "sheets").mkdir(parents=True, exist_ok=True)
    order = sorted((fid for fid, f in frames.items() if f.get("available")), key=lambda f: C.sha256_text(f"6106|audit|{f}"))
    sample2 = set(order[: max(1, round(0.2 * len(order)))])
    items = [r for r in rows if r["frame_id"] and r["test"] in ("A", "C")]
    flagged_frames = {r["frame_id"] for r in items if r["answerable"] is False or r["advisory_flags"]}
    with open(adir / "answerability_review_template.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["frame_id", "bank", "scene_id", "query_family", "test", "goal_id", "item", "display_form",
                    "proposed_gold", "proposed_answerable", "proposed_exclusion", "advisory_flags", "second_review_required",
                    "reviewer1_answerable(y/n)", "reviewer1_gold_agrees(y/n)", "reviewer1_notes",
                    "reviewer2_answerable(y/n)", "reviewer2_gold_agrees(y/n)", "reviewer2_notes", "adjudication"])
        for r in sorted(items, key=lambda r: (r["frame_id"], r["test"], r["query_id"])):
            item = r["original_prompt_id"] or r["display_form"]
            w.writerow([r["frame_id"], r["bank"], r["scene_id"], r["family"], r["test"], r["goal_id"], item, r["display_form"],
                        r["gold_answer"], r["answerable"], r["exclusion_reason"] or "", ";".join(r["advisory_flags"]),
                        "yes" if (r["frame_id"] in sample2 or r["frame_id"] in flagged_frames) else "no"] + [""] * 7)
    for fid, fr in frames.items():
        if not fr.get("available"):
            continue
        tiles = []
        tick = fr["_tick"]
        for v in C.VIEW_KEYS:
            meta = store.index[fr["views"][v]]
            im = Image.open(out / meta["path"]).convert("RGB").resize((640, 360))
            if not (v == "wrist_cam" and fr["wrist_moving"]):
                dr = ImageDraw.Draw(im)
                for name, o in tick["objects"].items():
                    uv, z = L.project(np.asarray([o["centroid"]]), fr["cameras"][v])
                    if z[0] > 0:
                        u, w = uv[0, 0] * 640 / 1280, uv[0, 1] * 360 / 720
                        dr.ellipse([u - 5, w - 5, u + 5, w + 5], outline=(255, 0, 0), width=2)
                        dr.text((u + 7, w - 6), name, fill=(255, 255, 0))
            tiles.append(im)
        sheet = Image.new("RGB", (640 * 3, 360 + 420), (255, 255, 255))
        for i, im in enumerate(tiles):
            sheet.paste(im, (640 * i, 0))
        d = ImageDraw.Draw(sheet)
        lines = [f"{fid}  bank={fr['bank']}  t={fr['observed_time_s']:.2f}s  (audit sheet: proposed labels; not a model input)"]
        for r in sorted([r for r in items if r["frame_id"] == fid], key=lambda r: r["query_id"]):
            if r["display_form"] in ("reference_subject", "reference_late"):
                continue
            lines.append(f"{r['test']} {r['goal_id']:>3} {(r['original_prompt_id'] or ''):<26} gold={r['gold_answer']:<3} "
                         f"answerable={r['answerable']} {r['exclusion_reason'] or ''}")
        fl = flags[fid]
        lines.append("gripper contact: " + ", ".join(f"{k}={v}" for k, v in fl["gripper_contact"].items()))
        if fl["bowl_identity"]:
            lines.append(f"bowl displacement (m): {fl['bowl_identity']['xy_displacement_m']}")
        for i, line in enumerate(lines[:26]):
            d.text((8, 368 + 15 * i), line, fill=(0, 0, 0))
        sheet.save(adir / "sheets" / f"{fid}.jpg", quality=88)
    C.write_json_atomic(adir / "audit_manifest.json", {
        "frames": len([f for f in frames.values() if f.get("available")]), "second_review_sample_frames": sorted(sample2),
        "flagged_frames": sorted(flagged_frames), "status": "prepared_not_reviewed",
        "instructions": "Reviewer 1: inspect every sheet; record whether both objects, their relative placement and any "
                        "required support/containment are discernible, and whether the proposed gold label is correct in "
                        "the robot frame. Reviewer 2: all flagged frames plus the deterministic 20% sample. Do not consult "
                        "model answers."})


if __name__ == "__main__":
    sys.exit(main())
