"""Checkpoint lineage and tensor audit for RQA-20261006 readout lanes (CPU only).

python -m experiments.robolab_vqa.eligibility --output <dir> [--workers 16]

For each lane: hash every weight file the native reasoner loads, compare with the Hugging Face LFS sha256 of
the pinned revision, classify tensors as reasoner (understanding tower, vision encoder/projector, embeddings,
LM head) or generation-only with the same drop rules as vLLM's Cosmos3/Cosmos3-Edge weight mappers, and
compare reasoner tensors byte-for-byte between each base and policy checkpoint.
"""
from __future__ import annotations

import argparse
import json
import re
import struct
import sys
import urllib.request
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from . import common as C

LANES = {
    "N3-base": {"family": "N3", "role": "base_reasoner", "repo": "nvidia/Cosmos3-Nano",
                "revision": "e59a53c25979a090fa8706c9acc0c254a6e89b92",
                "path": "/data/users/ali/rqa-20261006/checkpoints/Cosmos3-Nano-e59a53c", "mapper": "cosmos3",
                "weights": ["transformer/*.safetensors", "vision_encoder/*.safetensors"]},
    "N3-policy": {"family": "N3", "role": "executed_policy_reasoner", "repo": "nvidia/Cosmos3-Nano-Policy-DROID",
                  "revision": "6706d7680581c255ff61e0f3bb49d90eac55c79e",
                  "path": "/data/users/ali/vla_wam/checkpoints/cosmos3_nano_policy_droid", "mapper": "cosmos3",
                  "weights": ["transformer/*.safetensors", "vision_encoder/*.safetensors"]},
    "E3-base": {"family": "E3", "role": "base_reasoner", "repo": "nvidia/Cosmos3-Edge",
                "revision": "ff48d22144de52de296a7b4d3a78914831007212",
                "path": "/data/users/ali/vla_wam/checkpoints/cosmos3_edge_base_ff48d221", "mapper": "cosmos3_edge",
                "weights": ["transformer/*.safetensors", "vision_encoder/*.safetensors"]},
    "E3-policy": {"family": "E3", "role": "executed_policy_reasoner", "repo": "nvidia/Cosmos3-Edge-Policy-DROID",
                  "revision": "a7c7288f9b6ac1684e993007b0f9703dd26e58ef",
                  "path": "/data/users/ali/sgw-01/current-20260924a/checkpoints/cosmos3-edge-a7c7288", "mapper": "cosmos3_edge",
                  "weights": ["transformer/*.safetensors", "vision_encoder/*.safetensors"]},
    "F3-qwen3vl4b": {"family": "F3", "role": "released_shared_text_encoder_component", "repo": "black-forest-labs/flux-3-action-base",
                     "revision": "62878e2925e59b7a89ec14463ce89932624c490d", "subfolder": "text_encoder",
                     "path": "/data/users/ali/sgw-01/current-20260924a/checkpoints/flux-3-action-base-62878e2/text_encoder",
                     "mapper": "qwen3_vl", "weights": ["*.safetensors"],
                     "upstream": {"repo": "Qwen/Qwen3-VL-4B-Instruct", "revision": "ebb281ec70b05090aa6165b016eac8ec08e71b17"}},
    "N3-upstream-qwen3vl8b": {"family": "N3", "role": "upstream_ancestor_named_in_policy_config", "repo": "Qwen/Qwen3-VL-8B-Instruct",
                              "revision": "0c351dd01ed87e9c1b53cbc748cba10e6187ff3b",
                              "path": "/data/users/ali/rqa-20261006/checkpoints/Qwen3-VL-8B-Instruct-0c351dd", "mapper": "qwen3_vl",
                              "weights": ["*.safetensors"]},
}
PAIRS = [("N3-base", "N3-policy"), ("E3-base", "E3-policy")]
META_FILES = ["config.json", "chat_template.json", "chat_template.jinja", "generation_config.json", "preprocessor_config.json",
              "processor_config.json", "video_preprocessor_config.json", "tokenizer.json", "tokenizer_config.json",
              "special_tokens_map.json", "vocab.json", "merges.txt", "model.safetensors.index.json", "model_index.json",
              "text_tokenizer/tokenizer.json", "text_tokenizer/tokenizer_config.json", "text_tokenizer/chat_template.jinja",
              "transformer/config.json", "vision_encoder/config.json", "checkpoint.json"]

GEN_SUBSTR = ("_moe_gen", ".add_q_proj.", ".add_k_proj.", ".add_v_proj.", ".to_add_out.", ".norm_added_q.", ".norm_added_k.",
              ".k_norm_und_for_gen.")
GEN_PREFIX = ("proj_in.", "proj_out.", "time_embedder.", "audio_proj_in.", "audio_proj_out.", "action_proj_in.",
              "action_proj_out.")
GEN_REGEX = (re.compile(r"^audio_modality_embed(\..*)?$"), re.compile(r"^action_modality_embed(\..*)?$"))


def is_generation_only(name: str) -> bool:
    return (any(s in name for s in GEN_SUBSTR) or name.startswith(GEN_PREFIX) or any(r.match(name) for r in GEN_REGEX))


def component(name: str) -> str:
    n = name
    if n.startswith(("model.visual.", "visual.", "blocks.", "merger.", "patch_embed.", "pos_embed.", "deepstack_merger_list.")) \
            or n.startswith(("model.vision", "vision_model.", "encoder.", "embeddings.", "post_layernorm.", "head.")):
        return "vision_encoder"
    if "projector" in n or n.startswith(("mlp1.", "multi_modal_projector.")):
        return "projector"
    if "lm_head" in n:
        return "lm_head"
    if "embed_tokens" in n or n.endswith("embeddings.weight"):
        return "token_embedding"
    if ".self_attn." in n:
        return "attention"
    if ".mlp." in n:
        return "mlp"
    if "layernorm" in n or n.endswith("norm.weight") or ".norm." in n:
        return "norm"
    return "other"


def safetensors_header(path: str) -> tuple[dict, int]:
    with open(path, "rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        header = json.loads(f.read(n))
    header.pop("__metadata__", None)
    return header, 8 + n


def tensor_hashes(path: str) -> dict:
    header, base = safetensors_header(path)
    out = {}
    with open(path, "rb") as f:
        for name, info in header.items():
            a, b = info["data_offsets"]
            f.seek(base + a)
            out[name] = {"sha256": C.sha256_bytes(f.read(b - a)), "dtype": info["dtype"], "shape": info["shape"],
                         "file": Path(path).name}
    return out


def read_tensor_f32(path: str, name: str) -> np.ndarray:
    header, base = safetensors_header(path)
    info = header[name]
    a, b = info["data_offsets"]
    with open(path, "rb") as f:
        f.seek(base + a)
        raw = f.read(b - a)
    if info["dtype"] == "BF16":
        u = np.frombuffer(raw, dtype=np.uint16).astype(np.uint32) << 16
        return u.view(np.float32).reshape(info["shape"])
    if info["dtype"] in ("F32", "F16"):
        return np.frombuffer(raw, dtype=np.float32 if info["dtype"] == "F32" else np.float16).astype(np.float32).reshape(info["shape"])
    raise ValueError(info["dtype"])


def diff_job(job: tuple) -> dict:
    fa, fb, n = job
    x, y = read_tensor_f32(fa, n), read_tensor_f32(fb, n)
    if x.shape != y.shape:
        return {"tensor": n, "component": component(n), "shape_mismatch": [list(x.shape), list(y.shape)]}
    d = (x.astype(np.float64) - y.astype(np.float64)).ravel()
    sq_d = float(d @ d)
    xb = x.astype(np.float64).ravel()
    sq_x = float(xb @ xb)
    return {"tensor": n, "component": component(n), "max_abs_diff": float(np.abs(d).max()),
            "rel_fro_diff": float(np.sqrt(sq_d / max(sq_x, 1e-24))), "sq_diff": sq_d, "sq_base": sq_x,
            "n_elements_different": int(np.count_nonzero(d)), "n_elements": int(d.size)}


def hf_lfs(repo: str, revision: str, subdir: str = "") -> dict:
    out = {}
    dirs = [subdir] if subdir else ["", "transformer", "vision_encoder", "text_tokenizer"]
    for d in dirs:
        url = f"https://huggingface.co/api/models/{repo}/tree/{revision}/{d}?expand=true"
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                for e in json.load(r):
                    if e.get("type") == "file":
                        rel = e["path"][len(subdir) + 1:] if subdir else e["path"]
                        out[rel] = (e.get("lfs") or {}).get("oid") or ("git-blob:" + e.get("oid", ""))
        except Exception as error:  # noqa: BLE001
            out[f"{d}/<error>"] = repr(error)[:200]
    return out


def git_blob_sha1(path: Path) -> str:
    import hashlib
    data = path.read_bytes()
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def file_job(path: str) -> tuple[str, str]:
    return path, C.sha256_file(path)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--lanes", default=",".join(LANES))
    args = ap.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    lanes = {k: LANES[k] for k in args.lanes.split(",")}
    files = {}
    for lane, spec in lanes.items():
        root = Path(spec["path"])
        index = root / "model.safetensors.index.json"
        if index.exists():
            # exactly the shards the native reasoner loader reads (vLLM filters shards by the root index)
            files[lane] = sorted(str(root / f) for f in set(json.loads(index.read_text())["weight_map"].values()))
        else:
            files[lane] = sorted(str(p) for pat in spec["weights"] for p in root.glob(pat))
    with ProcessPoolExecutor(args.workers) as pool:
        hashes = dict(pool.map(file_job, [p for v in files.values() for p in v]))
        tensor_maps = dict(zip([p for v in files.values() for p in v],
                               pool.map(tensor_hashes, [p for v in files.values() for p in v])))
    report = {"created_utc": C.utc_now(), "lanes": {}, "pairs": {}}
    tensors = {}
    for lane, spec in lanes.items():
        root = Path(spec["path"])
        remote = hf_lfs(spec["repo"], spec["revision"], spec.get("subfolder", ""))
        weight_files = {}
        for p in files[lane]:
            rel = str(Path(p).relative_to(root))
            weight_files[rel] = {"sha256": hashes[p], "bytes": Path(p).stat().st_size, "hf_lfs_sha256": remote.get(rel),
                                 "matches_hf_revision": remote.get(rel) == hashes[p]}
        meta = {}
        for rel in META_FILES:
            p = root / rel
            if p.exists():
                blob = git_blob_sha1(p)
                meta[rel] = {"sha256": C.sha256_file(p), "git_blob_sha1": blob,
                             "matches_hf_revision": remote.get(rel) in (f"git-blob:{blob}", C.sha256_file(p))}
        tmap = {}
        for p in files[lane]:
            tmap.update(tensor_maps[p])
        tensors[lane] = tmap
        reasoner = {n: t for n, t in tmap.items() if not is_generation_only(n)}
        comp: dict = {}
        for n, t in reasoner.items():
            c = comp.setdefault(component(n), {"tensors": 0, "params": 0})
            c["tensors"] += 1
            c["params"] += int(np.prod(t["shape"])) if t["shape"] else 1
        entry = {**{k: v for k, v in spec.items() if k != "weights"}, "weight_files": weight_files, "metadata_files": meta,
                 "all_weight_files_match_hf_revision": all(v["matches_hf_revision"] for v in weight_files.values()) and bool(weight_files),
                 "n_tensors": len(tmap), "n_reasoner_tensors": len(reasoner), "n_generation_only_tensors": len(tmap) - len(reasoner),
                 "reasoner_params": int(sum(c["params"] for c in comp.values())), "reasoner_components": comp,
                 "has_lm_head_tensor": any("lm_head" in n for n in reasoner),
                 "has_token_embedding": any("embed_tokens" in n for n in reasoner)}
        cfg = json.loads((root / "config.json").read_text())
        entry["tie_word_embeddings"] = cfg.get("tie_word_embeddings", (cfg.get("text_config") or {}).get("tie_word_embeddings"))
        entry["architectures"] = cfg.get("architectures")
        entry["model_type"] = cfg.get("model_type")
        if "upstream" in spec:
            up = hf_lfs(spec["upstream"]["repo"], spec["upstream"]["revision"])
            entry["upstream_comparison"] = {
                **spec["upstream"],
                "weight_files_identical": all(up.get(rel) == v["sha256"] for rel, v in weight_files.items()),
                "metadata_identical": {rel: up.get(rel) in (f"git-blob:{m['git_blob_sha1']}", m["sha256"]) for rel, m in meta.items()}}
        reasoner_digest = C.canonical_sha256({n: t["sha256"] for n, t in sorted(reasoner.items())})
        entry["reasoner_tensor_digest"] = reasoner_digest
        report["lanes"][lane] = entry
        C.write_json_atomic(args.output / f"tensors_{lane}.json", tmap, indent=None)
    for base, pol in PAIRS:
        if base not in tensors or pol not in tensors:
            continue
        a = {n: t for n, t in tensors[base].items() if not is_generation_only(n)}
        b = {n: t for n, t in tensors[pol].items() if not is_generation_only(n)}
        common = sorted(set(a) & set(b))
        diff = [n for n in common if a[n]["sha256"] != b[n]["sha256"]]
        by_comp: dict = {}
        for n in common:
            c = by_comp.setdefault(component(n), {"tensors": 0, "identical": 0, "different": 0, "max_abs_diff": 0.0,
                                                  "rel_fro_diff_max": 0.0, "examples_different": []})
            c["tensors"] += 1
            if a[n]["sha256"] == b[n]["sha256"]:
                c["identical"] += 1
                continue
            c["different"] += 1
            if len(c["examples_different"]) < 5:
                c["examples_different"].append(n)
        # numeric differences for every differing reasoner tensor
        jobs = []
        for n in diff:
            fa = next(p for p in files[base] if Path(p).name == a[n]["file"])
            fb = next(p for p in files[pol] if Path(p).name == b[n]["file"])
            jobs.append((fa, fb, n))
        with ProcessPoolExecutor(args.workers) as pool:
            numeric = list(pool.map(diff_job, jobs))
        for c in by_comp.values():
            c["sum_sq_diff"] = 0.0
            c["sum_sq_base"] = 0.0
        for m in numeric:
            if "shape_mismatch" in m:
                continue
            c = by_comp[m["component"]]
            c["max_abs_diff"] = max(c["max_abs_diff"], m["max_abs_diff"])
            c["rel_fro_diff_max"] = max(c["rel_fro_diff_max"], m["rel_fro_diff"])
            c["sum_sq_diff"] += m["sq_diff"]
            c["sum_sq_base"] += m["sq_base"]
        for name, c in by_comp.items():
            c["aggregate_rel_fro_diff_over_differing"] = (float(np.sqrt(c["sum_sq_diff"] / c["sum_sq_base"]))
                                                          if c["sum_sq_base"] > 0 else 0.0)
        report["pairs"][f"{base}__{pol}"] = {
            "base": base, "policy": pol, "reasoner_tensors_base": len(a), "reasoner_tensors_policy": len(b),
            "only_in_base": sorted(set(a) - set(b))[:50], "only_in_policy": sorted(set(b) - set(a))[:50],
            "common": len(common), "identical": len(common) - len(diff), "different": len(diff),
            "reasoner_tensor_identical": len(diff) == 0 and set(a) == set(b), "by_component": by_comp,
            "numeric_all_differing": numeric,
            "generation_path_tensors_different": sum(1 for n in set(tensors[base]) & set(tensors[pol])
                                                     if is_generation_only(n) and tensors[base][n]["sha256"] != tensors[pol][n]["sha256"]),
            "generation_path_tensors_common": sum(1 for n in set(tensors[base]) & set(tensors[pol]) if is_generation_only(n))}
    C.write_json_atomic(args.output / "eligibility_audit.json", report)
    print(json.dumps({lane: {k: v for k, v in e.items() if k in ("all_weight_files_match_hf_revision", "n_tensors", "n_reasoner_tensors",
                                                                   "reasoner_params", "has_lm_head_tensor", "tie_word_embeddings",
                                                                   "architectures", "reasoner_tensor_digest")}
                      for lane, e in report["lanes"].items()}, indent=1))
    print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk in ("common", "identical", "different", "reasoner_tensor_identical",
                                                                   "only_in_base", "only_in_policy")} | {
        "by_component": {c: {kk: vv for kk, vv in d.items() if kk != "examples_different"} for c, d in v["by_component"].items()}}
                      for k, v in report["pairs"].items()}, indent=1))


if __name__ == "__main__":
    sys.exit(main())
