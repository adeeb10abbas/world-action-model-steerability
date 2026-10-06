"""Native reasoner readouts for RQA-20261006 lanes (vLLM offline engine, one isolated request at a time).

Every lane uses the checkpoint's own weights, LM head, tokenizer, processor and chat template through vLLM's
registered native class (Cosmos3 reasoner tower for the Cosmos3 unified checkpoints, Qwen3-VL for the released
FLUX shared encoder and the upstream Qwen ancestor). No head is attached, swapped or trained.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

from . import common as C

VLLM_PYTHON = "/data/users/ali/vla_wam/envs/cosmos3-edge-vllm-omni-900a7f08-py313/bin/python"

LANES: dict[str, dict[str, Any]] = {
    "N3-base": {"family": "N3", "role": "base_reasoner", "repo": "nvidia/Cosmos3-Nano",
                "revision": "e59a53c25979a090fa8706c9acc0c254a6e89b92",
                "path": "/data/users/ali/rqa-20261006/checkpoints/Cosmos3-Nano-e59a53c",
                "native_class": "Cosmos3ForConditionalGeneration"},
    "N3-policy": {"family": "N3", "role": "executed_policy_reasoner", "repo": "nvidia/Cosmos3-Nano-Policy-DROID",
                  "revision": "6706d7680581c255ff61e0f3bb49d90eac55c79e",
                  "path": "/data/users/ali/vla_wam/checkpoints/cosmos3_nano_policy_droid",
                  "native_class": "Cosmos3ForConditionalGeneration"},
    "E3-base": {"family": "E3", "role": "base_reasoner", "repo": "nvidia/Cosmos3-Edge",
                "revision": "ff48d22144de52de296a7b4d3a78914831007212",
                "path": "/data/users/ali/vla_wam/checkpoints/cosmos3_edge_base_ff48d221",
                "native_class": "Cosmos3EdgeForConditionalGeneration"},
    "E3-policy": {"family": "E3", "role": "executed_policy_reasoner", "repo": "nvidia/Cosmos3-Edge-Policy-DROID",
                  "revision": "a7c7288f9b6ac1684e993007b0f9703dd26e58ef",
                  "path": "/data/users/ali/sgw-01/current-20260924a/checkpoints/cosmos3-edge-a7c7288",
                  "native_class": "Cosmos3EdgeForConditionalGeneration",
                  "reasoner_view": "/data/users/ali/rqa-20261006/views/E3-policy-reasoner-a7c7288"},
    "F3-qwen3vl4b": {"family": "F3", "role": "released_shared_text_encoder_component_auxiliary",
                     "repo": "black-forest-labs/flux-3-action-base", "revision": "62878e2925e59b7a89ec14463ce89932624c490d",
                     "subfolder": "text_encoder",
                     "path": "/data/users/ali/sgw-01/current-20260924a/checkpoints/flux-3-action-base-62878e2/text_encoder",
                     "native_class": "Qwen3VLForConditionalGeneration"},
    "N3-upstream-qwen3vl8b": {"family": "N3", "role": "upstream_ancestor_spans_more_than_robot_adaptation",
                              "repo": "Qwen/Qwen3-VL-8B-Instruct", "revision": "0c351dd01ed87e9c1b53cbc748cba10e6187ff3b",
                              "path": "/data/users/ali/rqa-20261006/checkpoints/Qwen3-VL-8B-Instruct-0c351dd",
                              "native_class": "Qwen3VLForConditionalGeneration"},
}

DECODING = {"temperature": 0.0, "max_tokens": 256, "seed": C.ORDER_SEED, "n": 1}
CHAT_TEMPLATE_KWARGS = {"enable_thinking": False}
ENGINE = {"dtype": "bfloat16", "max_model_len": 16384, "enforce_eager": True, "enable_prefix_caching": False,
          "max_num_seqs": 1, "limit_mm_per_prompt": {"image": 6, "video": 0}, "seed": C.ORDER_SEED,
          "trust_remote_code": False, "attention_backend": "FLASH_ATTN"}
# Precompiled kernels only (the pod has no CUDA toolkit for FlashInfer JIT); greedy decoding needs no sampler kernel.
ENGINE_ENV = {"VLLM_ENABLE_V1_MULTIPROCESSING": "0", "VLLM_USE_FLASHINFER_SAMPLER": "0", "TOKENIZERS_PARALLELISM": "false",
              "HF_HUB_OFFLINE": "1"}
ADAPTER_VERSION = "rqa-adapter-1"
# rqa-adapter-1 (packaging fix, documented before any evaluation query): vLLM 0.26's Cosmos3-Edge mapper drops
# generation-tower tensors (_moe_gen, add_*_proj, to_add_out, norm_added_*) but not the generation-path key norm
# `layers.N.self_attn.k_norm_und_for_gen.weight` (config use_und_k_norm_for_gen=true), so loading the released
# Edge checkpoints fails. The reasoner tower has no q/k norm (qk_norm_for_text=false) and never reads it; the
# patch drops it exactly like the other generation-only tensors. No reasoner weight is altered.
EDGE_LOADER_PATCH = {".k_norm_und_for_gen.": None}


# rqa-adapter-1 (packaging view): the released Edge policy config.json declares the unified omni class
# (Cosmos3ForConditionalGeneration / model_type cosmos3_omni) although its reasoner fields (text_config,
# vision_config, projector_config, special token ids, tie_word_embeddings) are identical to the Edge reasoner
# config. The view directory symlinks every policy file and rewrites only `architectures` and `model_type` in a
# copy of the policy's own config.json, so vLLM's native Cosmos3-Edge reasoner class loads the policy weights.
VIEW_CONFIG_EDITS = {"architectures": ["Cosmos3EdgeForConditionalGeneration"], "model_type": "cosmos3_edge"}


def materialize_view(lane: str) -> str:
    spec = LANES[lane]
    view = spec.get("reasoner_view")
    if not view:
        return spec["path"]
    src, dst = Path(spec["path"]), Path(view)
    dst.mkdir(parents=True, exist_ok=True)
    for entry in src.iterdir():
        if entry.name in ("config.json", ".cache"):
            continue
        link = dst / entry.name
        if not link.exists() and not link.is_symlink():
            link.symlink_to(entry)
    cfg = json.loads((src / "config.json").read_text())
    cfg.update(VIEW_CONFIG_EDITS)
    tmp = dst / ".config.json.tmp"
    tmp.write_text(json.dumps(cfg, indent=2, sort_keys=True))
    tmp.replace(dst / "config.json")
    return str(dst)


def view_receipt(lane: str) -> dict | None:
    spec = LANES[lane]
    if not spec.get("reasoner_view"):
        return None
    dst = Path(spec["reasoner_view"])
    return {"path": str(dst), "config_edits": VIEW_CONFIG_EDITS, "config_sha256": C.sha256_file(dst / "config.json"),
            "source_config_sha256": C.sha256_file(Path(spec["path"]) / "config.json"),
            "symlinks": {p.name: str(p.resolve()) for p in sorted(dst.iterdir()) if p.is_symlink()}}


def apply_loader_patches(lane: str) -> list[str]:
    applied = []
    if LANES[lane]["native_class"] == "Cosmos3EdgeForConditionalGeneration":
        from vllm.model_executor.models import cosmos3_edge

        mapper = cosmos3_edge.Cosmos3EdgeForConditionalGeneration.hf_to_vllm_mapper
        for key, value in EDGE_LOADER_PATCH.items():
            mapper.orig_to_new_substr[key] = value
            applied.append(f"Cosmos3EdgeForConditionalGeneration.hf_to_vllm_mapper.orig_to_new_substr[{key!r}]={value!r}")
    return applied


class Readout:
    def __init__(self, lane: str, gpu_memory_utilization: float = 0.85) -> None:
        for key, value in ENGINE_ENV.items():
            os.environ[key] = value
        from vllm import LLM, SamplingParams

        self.lane = lane
        self.spec = LANES[lane]
        kwargs = dict(ENGINE)
        kwargs["gpu_memory_utilization"] = gpu_memory_utilization
        self.loader_patches = apply_loader_patches(lane)
        self.model_path = materialize_view(lane)
        self.view = view_receipt(lane)
        t = time.time()
        self.llm = LLM(model=self.model_path, **kwargs)
        self.load_s = time.time() - t
        self.engine_kwargs = kwargs
        self.sampling = SamplingParams(temperature=DECODING["temperature"], max_tokens=DECODING["max_tokens"],
                                       seed=DECODING["seed"], n=1)
        tok = self.llm.get_tokenizer()
        template = getattr(tok, "chat_template", None)
        self.tokenizer_template_sha256 = C.sha256_text(template) if isinstance(template, str) else None
        self._images: dict[str, Any] = {}

    def image(self, root: Path, image_id: str, rel: str, expected_raw_sha: str | None = None):
        if image_id not in self._images:
            import numpy as np
            from PIL import Image

            im = Image.open(root / rel).convert("RGB")
            im.load()
            if expected_raw_sha and C.raw_rgb_sha256(np.asarray(im)) != expected_raw_sha:
                raise RuntimeError(f"image {image_id} pixels differ from release")
            self._images[image_id] = im
        return self._images[image_id]

    def messages(self, payload: dict, root: Path, image_meta: dict) -> list[dict]:
        content = []
        for seg in payload["segments"]:
            if seg["type"] == "text":
                content.append({"type": "text", "text": seg["text"]})
            else:
                meta = image_meta[seg["image_id"]]
                content.append({"type": "image_pil",
                                "image_pil": self.image(root, seg["image_id"], meta["path"], meta["raw_rgb_sha256"])})
        return [{"role": "user", "content": content}]

    def generate(self, payload: dict, root: Path, image_meta: dict) -> dict:
        msgs = self.messages(payload, root, image_meta)
        t = time.time()
        outs = self.llm.chat(msgs, sampling_params=self.sampling, use_tqdm=False,
                             chat_template_kwargs=CHAT_TEMPLATE_KWARGS)
        latency = time.time() - t
        out = outs[0]
        comp = out.outputs[0]
        tok = self.llm.get_tokenizer()
        raw_with_special = tok.decode(list(comp.token_ids), skip_special_tokens=False)
        return {"raw_response": comp.text, "raw_response_with_special_tokens": raw_with_special,
                "finish_reason": comp.finish_reason, "output_token_ids": list(comp.token_ids),
                "prompt_tokens": len(out.prompt_token_ids or []), "output_tokens": len(comp.token_ids),
                "rendered_prompt": out.prompt, "rendered_prompt_sha256": C.sha256_text(out.prompt or ""),
                "latency_s": latency}

    def loaded_parameter_digest(self) -> dict:
        def digest(model):
            import torch

            h = hashlib.sha256()
            names = []
            count = 0
            for name, p in sorted(model.named_parameters(), key=lambda kv: kv[0]):
                t = p.detach().contiguous().view(-1).view(torch.uint8).cpu().numpy().tobytes()
                h.update(name.encode() + b"\0" + str(p.dtype).encode() + str(tuple(p.shape)).encode() + b"\0")
                h.update(hashlib.sha256(t).digest())
                names.append(name)
                count += p.numel()
            buffers = sorted(n for n, _ in model.named_buffers())
            return {"sha256": h.hexdigest(), "n_parameters": len(names), "numel": int(count),
                    "names_sha256": hashlib.sha256("\n".join(names).encode()).hexdigest(), "n_buffers": len(buffers)}

        return self.llm.apply_model(digest)[0]

    def name_insensitive_value_digest(self) -> dict:
        """Digest of loaded parameter values in sorted-name order without names (cross-class comparison aid)."""
        def digest(model):
            import torch

            vals = []
            for name, p in model.named_parameters():
                t = p.detach().contiguous().view(-1).view(torch.uint8).cpu().numpy().tobytes()
                vals.append(hashlib.sha256(t).hexdigest())
            return hashlib.sha256("\n".join(sorted(vals)).encode()).hexdigest()

        return {"sorted_value_hashes_sha256": self.llm.apply_model(digest)[0]}


def environment_receipt() -> dict:
    import platform
    import subprocess

    out: dict[str, Any] = {"python": platform.python_version(), "host": platform.node()}
    for mod in ("vllm", "torch", "transformers", "PIL", "numpy"):
        try:
            m = __import__(mod)
            out[mod] = getattr(m, "__version__", None)
        except Exception as error:  # noqa: BLE001
            out[mod] = f"unavailable: {error}"
    try:
        import torch

        out["cuda"] = torch.version.cuda
        out["gpu"] = torch.cuda.get_device_name(0)
    except Exception:  # noqa: BLE001
        pass
    try:
        out["nvidia_smi"] = subprocess.run(["nvidia-smi", "--query-gpu=name,uuid,driver_version,memory.total",
                                            "--format=csv,noheader"], capture_output=True, text=True).stdout.strip()
    except Exception:  # noqa: BLE001
        pass
    out["env"] = {k: os.environ.get(k) for k in ("VLLM_ENABLE_V1_MULTIPROCESSING", "CUDA_VISIBLE_DEVICES",
                                                  "NVIDIA_VISIBLE_DEVICES", "HF_HUB_OFFLINE", "VLLM_BATCH_INVARIANT")}
    return out


def payload_sha256(payload: dict, image_meta: dict) -> str:
    segs = [s if s["type"] == "text" else {"type": "image", "image_id": s["image_id"],
                                            "raw_rgb_sha256": image_meta[s["image_id"]]["raw_rgb_sha256"]}
            for s in payload["segments"]]
    return C.canonical_sha256({"query_id": payload["query_id"], "segments": segs})


def lane_manifest(lane: str, eligibility_audit: dict | None) -> dict:
    spec = LANES[lane]
    root = Path(spec["path"])
    files = {}
    for rel in ("config.json", "generation_config.json", "preprocessor_config.json", "processor_config.json",
                "video_preprocessor_config.json", "tokenizer.json", "tokenizer_config.json", "chat_template.json",
                "chat_template.jinja", "model.safetensors.index.json", "vocab.json", "merges.txt", "special_tokens_map.json"):
        if (root / rel).exists():
            files[rel] = C.sha256_file(root / rel)
    audit = (eligibility_audit or {}).get("lanes", {}).get(lane, {})
    manifest = {"lane": lane, **{k: v for k, v in spec.items()}, "metadata_files_sha256": files,
                "weight_files": audit.get("weight_files"), "reasoner_tensor_digest": audit.get("reasoner_tensor_digest"),
                "all_weight_files_match_hf_revision": audit.get("all_weight_files_match_hf_revision"),
                "engine": ENGINE, "engine_env": ENGINE_ENV, "decoding": DECODING, "chat_template_kwargs": CHAT_TEMPLATE_KWARGS,
                "reasoner_view_config_edits": VIEW_CONFIG_EDITS if spec.get("reasoner_view") else None,
                "adapter_version": ADAPTER_VERSION,
                "loader_patch": (EDGE_LOADER_PATCH if spec["native_class"] == "Cosmos3EdgeForConditionalGeneration" else None)}
    manifest["checkpoint_manifest_sha256"] = C.canonical_sha256(manifest)
    return manifest
