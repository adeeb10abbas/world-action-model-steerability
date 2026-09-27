"""Blinded forecast annotation packets and post-freeze unblinding (CLUSTER_EXECUTION_SPEC section 7).

build:    one packet per (episode, window) with a decodable future; opaque IDs from a secret salt; packets hold only
          the resampled mapped forecast frames, a contact sheet and a scene legend. The key lives outside packets/.
unblind:  two independent label files (+ optional adjudication) -> forecast_labels.jsonl with intended-goal semantics.

    python -m experiments.robolab_workshop.annotation build --runs $R/runs --features $R/analysis/conf_features.jsonl \
        --out $R/annotation
    python -m experiments.robolab_workshop.annotation unblind --out $R/annotation --labels a.jsonl b.jsonl \
        [--adjudication adj.jsonl] --dest $R/analysis/forecast_labels.jsonl
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import hmac
import json
import secrets
from pathlib import Path

import numpy as np

from .catalog import ALTERNATIVES, SCENES

W, WRIST_H, EXT_H = 640, 360, 184
FIELDS = ["moving_object", "direction", "visible_final_relation", "relation_object", "possible_release",
          "missing_object", "hallucinated_object", "unknown_reason"]
EXTERIOR = ("over_shoulder_left_camera", "over_shoulder_right_camera")
KIND_RELATION = {"cone:L": "left_of", "cone:R": "right_of", "cone:F": "closer_to_robot_than",
                 "cone:B": "farther_from_robot_than", "on_top": "on_top_of", "container": "inside", "stacked": "stacked_in"}
KIND_DIRECTION = {"cone:L": "left", "cone:R": "right", "cone:F": "closer_to_robot", "cone:B": "farther_from_robot"}


def canonical_frame(frame: np.ndarray) -> np.ndarray:
    """Resample every model's composite to one layout so resolution cannot identify the model."""
    from PIL import Image

    if frame.shape[1] != W:
        frame = np.asarray(Image.fromarray(frame).resize((W, round(frame.shape[0] * W / frame.shape[1])), Image.BILINEAR))
    wrist, ext = frame[:WRIST_H], frame[WRIST_H:]
    if ext.shape[0] != EXT_H:
        ext = np.asarray(Image.fromarray(ext).resize((W, EXT_H), Image.BILINEAR))
    return np.concatenate([wrist, ext], 0)


def legend_numbers(scene_id: str, names: list[str]) -> dict[str, int]:
    return {n: i + 1 for i, n in enumerate(sorted(names))}


def _project(cam: dict, p: np.ndarray) -> tuple[float, float] | None:
    from .scripted import quat_to_mat

    R = quat_to_mat(np.array(cam["quat_w_ros"], dtype=np.float64))
    K = np.array(cam["intrinsics"], dtype=np.float64)
    pc = R.T @ (np.asarray(p, dtype=np.float64) - np.array(cam["pos_w"], dtype=np.float64))
    if pc[2] <= 0.05:
        return None
    return K[0, 0] * pc[0] / pc[2] + K[0, 2], K[1, 1] * pc[1] / pc[2] + K[1, 2]


def draw_legend(first_obs: dict, tick0: dict, cams: dict, numbers: dict[str, int]) -> np.ndarray:
    from PIL import Image, ImageDraw, ImageFont

    font = ImageFont.load_default(size=30)
    panes = []
    zs = [(np.array(o["bbox_min"])[2]) for o in tick0["objects"].values()]
    table_z = float(min(zs)) if zs else 0.0
    for cam_name in EXTERIOR:
        img = Image.fromarray(np.asarray(first_obs[cam_name]))
        d = ImageDraw.Draw(img)
        for name, k in numbers.items():
            o = tick0["objects"][name]
            uv = _project(cams[cam_name], (np.array(o["bbox_min"]) + np.array(o["bbox_max"])) / 2)
            if uv is None:
                continue
            u, v = uv
            d.ellipse([u - 30, v - 30, u + 30, v + 30], outline=(255, 255, 0), width=5)
            d.text((u + 34, v - 60), str(k), fill=(255, 255, 0), font=font, stroke_width=3, stroke_fill=(0, 0, 0))
        centres = np.array([(np.array(o["bbox_min"]) + np.array(o["bbox_max"])) / 2 for o in tick0["objects"].values()])
        anchor = np.array([centres[:, 0].mean(), centres[:, 1].min() - 0.25, table_z])
        for vec, label, colour in (([0, 0.15, 0], "robot-left", (0, 255, 255)), ([0.15, 0, 0], "farther", (255, 0, 255))):
            a, b = _project(cams[cam_name], anchor), _project(cams[cam_name], anchor + np.array(vec))
            if a and b:
                d.line([a, b], fill=colour, width=7)
                d.ellipse([b[0] - 10, b[1] - 10, b[0] + 10, b[1] + 10], fill=colour)
                d.text((b[0] + 12, b[1] - 20), label, fill=colour, font=font, stroke_width=3, stroke_fill=(0, 0, 0))
        panes.append(np.asarray(img))
    return np.concatenate(panes, 1)


def contact_sheet(frames: np.ndarray, every: int = 4) -> np.ndarray:
    idx = list(range(0, len(frames), every))
    if idx[-1] != len(frames) - 1:
        idx.append(len(frames) - 1)
    small = [f[::2, ::2] for f in frames[idx]]
    cols = 4
    while len(small) % cols:
        small.append(np.zeros_like(small[0]))
    rows = [np.concatenate(small[i:i + cols], 1) for i in range(0, len(small), cols)]
    return np.concatenate(rows, 0)


def _opaque(salt: bytes, episode_id: str, window: str) -> str:
    return "A" + hmac.new(salt, f"{episode_id}|{window}".encode(), hashlib.sha256).hexdigest()[:12]


def build(args) -> None:
    from PIL import Image

    from .recording import LosslessStream

    out = args.out
    packets, keydir = out / "packets", out / "_key"
    packets.mkdir(parents=True, exist_ok=True)
    keydir.mkdir(parents=True, exist_ok=True)
    salt_path = keydir / "salt.hex"
    if not salt_path.exists():
        salt_path.write_text(secrets.token_hex(32))
    salt = bytes.fromhex(salt_path.read_text().strip())
    rows = [json.loads(x) for x in args.features.read_text().splitlines() if x.strip()]
    if args.limit:
        rows = rows[:args.limit]
    if args.nshards > 1:
        rows = rows[args.shard::args.nshards]
    key = []
    for r in rows:
        ep = args.runs / "episodes" / r["episode_id"]
        adir = Path(json.loads((ep / "COMPLETE.json").read_text())["attempt_dir"])
        reqs = [json.loads(x) for x in (adir / "requests.jsonl").read_text().splitlines() if x.strip()]
        with gzip.open(adir / "states.jsonl.gz", "rt") as f:
            tick0 = json.loads(f.readline())
        scene = r["scene_id"]
        numbers = legend_numbers(scene, list(tick0["objects"]))
        roles = resolve_roles(scene, r["goal_id"], json.loads((adir / "initial_state.json").read_text())["role_binding"])
        pw = r["primary_window"]["request_index"] if r.get("primary_window") else None
        windows = [("primary", pw)] + ([("request0", 0)] if pw not in (None, 0) else [])
        legend_id = _opaque(salt, r["episode_id"], "legend")
        fo = np.load(adir / "first_observation.npz")
        legend = draw_legend({c: fo[c] for c in EXTERIOR}, tick0, reqs[0]["camera_transforms"], numbers)
        for window, ri in windows:
            base = {"episode_id": r["episode_id"], "window": window, "request_index": ri, "scene_id": scene,
                    "goal_id": r["goal_id"], "model_id": r["model_id"], "form": r["form"], "legend_numbers": numbers,
                    "roles": roles}
            if ri is None:
                key.append(base | {"annotation_id": None, "status": "no_window"})
                continue
            req = next(x for x in reqs if x["request_index"] == ri)
            if req.get("future_status") != "decoded":
                key.append(base | {"annotation_id": None, "status": "future_not_decodable",
                                   "reason": req.get("future_missing_reason")})
                continue
            aid = _opaque(salt, r["episode_id"], window)
            pdir = packets / aid
            pdir.mkdir(exist_ok=True)
            video = np.load(req["future"]["uri"])["video"]
            mapped = sorted(i for i in req["future_executed_frames"] if i < len(video))
            frames = np.stack([canonical_frame(video[i]) for i in mapped])
            s = LosslessStream(pdir / "forecast.mkv", frames.shape[1], frames.shape[2])
            for fr in frames:
                s.write(fr)
            rec = s.close()
            Image.fromarray(contact_sheet(frames)).save(pdir / "contact_sheet.png")
            Image.fromarray(legend).save(pdir / "legend.png")
            (pdir / "packet.json").write_text(json.dumps({"annotation_id": aid, "frames": len(frames), "fps": 15,
                                                          "legend_numbers": sorted(numbers.values())}, indent=2))
            key.append(base | {"annotation_id": aid, "status": "packet", "mapped_frames": mapped,
                               "future_sha256": req["future"]["sha256"], "forecast_frame_sha256": rec["frame_sha256"]})
    if args.nshards > 1:
        (keydir / f"key.shard{args.shard:02d}of{args.nshards:02d}.jsonl").write_text(
            "".join(json.dumps(k, sort_keys=True) + "\n" for k in key))
        print(json.dumps({"shard": args.shard, "entries": len(key)}))
        return
    _finalize(out, keydir, salt, key, len(rows), args.features)


def finalize(args) -> None:
    keydir = args.out / "_key"
    salt = bytes.fromhex((keydir / "salt.hex").read_text().strip())
    shards = sorted(keydir.glob(f"key.shard*of{args.nshards:02d}.jsonl"))
    if len(shards) != args.nshards:
        raise SystemExit(f"expected {args.nshards} shard keys, found {len(shards)}")
    key = [json.loads(x) for p in shards for x in p.read_text().splitlines() if x.strip()]
    rows = [json.loads(x) for x in args.features.read_text().splitlines() if x.strip()]
    if len({k["episode_id"] for k in key}) != len(rows):
        raise SystemExit("shard keys do not cover every feature row")
    order = {r["episode_id"]: i for i, r in enumerate(rows)}
    key.sort(key=lambda k: (order[k["episode_id"]], k["window"] != "primary"))
    _finalize(args.out, keydir, salt, key, len(rows), args.features)


def _finalize(out: Path, keydir: Path, salt: bytes, key: list, n_rows: int, features: Path) -> None:
    (keydir / "key.jsonl").write_text("".join(json.dumps(k, sort_keys=True) + "\n" for k in key))
    ids = [k["annotation_id"] for k in key if k["annotation_id"]]
    order = sorted(ids, key=lambda a: hashlib.sha256(salt + a.encode()).hexdigest())
    with open(out / "labels_template.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["annotation_id"] + FIELDS)
        for a in order:
            w.writerow([a] + [""] * len(FIELDS))
    counts = {}
    for k in key:
        counts[k["status"]] = counts.get(k["status"], 0) + 1
    (out / "build_receipt.json").write_text(json.dumps({"episodes": n_rows, "counts": counts,
                                                        "features_sha256": hashlib.sha256(features.read_bytes()).hexdigest()},
                                                       indent=2))
    print(json.dumps(counts))


def resolve_roles(scene_id: str, goal_id: str, binding: dict) -> dict:
    g = SCENES[scene_id]["goals"][goal_id]
    mover, ref = g["mover"], g["reference"]
    if binding.get("left_bowl"):
        mover, ref = ((binding["left_bowl"], binding["right_bowl"]) if goal_id == "LR"
                      else (binding["right_bowl"], binding["left_bowl"]))
    return {"mover": mover, "reference": ref}


def semantics(label: dict, k: dict) -> dict:
    inv = {str(v): n for n, v in k["legend_numbers"].items()}
    roles = k["roles"]

    def role(x):
        x = str(x).strip()
        if x in inv:
            n = inv[x]
            return "mover" if n == roles["mover"] else "reference" if n == roles["reference"] else "other"
        return x or "unknown"

    scene, goal = k["scene_id"], k["goal_id"]
    kind = SCENES[scene]["goals"][goal]["kind"]
    mv, rel, robj = role(label["moving_object"]), label["visible_final_relation"].strip(), role(label["relation_object"])
    if rel in ("ambiguous", "unknown"):
        fr = rel
    elif mv == "mover" and robj == "reference" and rel == KIND_RELATION[kind]:
        fr = "goal"
    elif mv == "mover" and any(rel == KIND_RELATION[SCENES[scene]["goals"][a]["kind"]] and
                               robj == ("reference" if SCENES[scene]["goals"][a]["reference"] == SCENES[scene]["goals"][goal]["reference"] else "other")
                               for a in ALTERNATIVES[scene][goal]):
        fr = "alternative_goal"
    else:
        fr = "not_goal"
    d = label["direction"].strip()
    if d in ("left", "right", "closer_to_robot", "farther_from_robot"):
        fd = ("goal_direction" if KIND_DIRECTION[kind] == d else "other_direction") if kind in KIND_DIRECTION else "lateral"
    else:
        fd = d or "unknown"
    return {"episode_id": k["episode_id"], "annotation_id": k["annotation_id"], "fc_moving_object_role": mv,
            "fc_direction": fd, "fc_visible_final_relation": fr,
            "fc_possible_release": label["possible_release"].strip() or "unknown",
            "fc_missing_object": label["missing_object"].strip() or "unknown",
            "fc_hallucinated_object": label["hallucinated_object"].strip() or "unknown"}


def _load_labels(path: Path) -> dict:
    if path.suffix == ".csv":
        with open(path) as f:
            return {r["annotation_id"]: r for r in csv.DictReader(f)}
    return {r["annotation_id"]: r for r in (json.loads(x) for x in path.read_text().splitlines() if x.strip())}


def unblind(args) -> None:
    key = [json.loads(x) for x in (args.out / "_key" / "key.jsonl").read_text().splitlines() if x.strip()]
    a, b = (_load_labels(p) for p in args.labels)
    adj = _load_labels(args.adjudication) if args.adjudication else {}
    out, disagreements = [], []
    for k in key:
        if k["window"] != "primary" or not k["annotation_id"]:
            continue
        la, lb = a.get(k["annotation_id"]), b.get(k["annotation_id"])
        if la is None or lb is None:
            raise SystemExit(f"missing label for {k['annotation_id']}")
        diff = [f for f in FIELDS if str(la.get(f, "")).strip() != str(lb.get(f, "")).strip()]
        if diff:
            if k["annotation_id"] not in adj:
                disagreements.append({"annotation_id": k["annotation_id"], "fields": diff})
                continue
            lab = adj[k["annotation_id"]]
        else:
            lab = la
        out.append(semantics(lab, k))
    if disagreements:
        (args.out / "disagreements.jsonl").write_text("".join(json.dumps(d) + "\n" for d in disagreements))
        raise SystemExit(f"{len(disagreements)} packets need adjudication; see disagreements.jsonl")
    args.dest.write_text("".join(json.dumps(x, sort_keys=True) + "\n" for x in out))
    print(f"wrote {len(out)} unblinded primary-window labels -> {args.dest}")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--runs", type=Path, required=True)
    b.add_argument("--features", type=Path, required=True)
    b.add_argument("--out", type=Path, required=True)
    b.add_argument("--limit", type=int, default=0)
    b.add_argument("--shard", type=int, default=0)
    b.add_argument("--nshards", type=int, default=1)
    fz = sub.add_parser("finalize")
    fz.add_argument("--out", type=Path, required=True)
    fz.add_argument("--features", type=Path, required=True)
    fz.add_argument("--nshards", type=int, required=True)
    u = sub.add_parser("unblind")
    u.add_argument("--out", type=Path, required=True)
    u.add_argument("--labels", type=Path, nargs=2, required=True)
    u.add_argument("--adjudication", type=Path, default=None)
    u.add_argument("--dest", type=Path, required=True)
    args = ap.parse_args()
    {"build": build, "finalize": finalize, "unblind": unblind}[args.cmd](args)


if __name__ == "__main__":
    main()
