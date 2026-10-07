"""Frozen V2 constants: scope, wrappers, option orders, output constraints, budgets and paths."""
from __future__ import annotations

import json
from pathlib import Path

from .. import common as C
from .. import prompts as P

DESIGN_VERSION = "2.0"
V2_IMPLEMENTATION_VERSION = "rqa-v2-impl-1"
V2_PARSER_VERSION = "rqa-v2-parse-1"
V2_LABEL_VERSION = "rqa-gold-1"  # unchanged R1 geometry labels
SPEC_DIR = C.SPEC_DIR / "v2-final"

R1_SOURCE_COMMIT = "acbe7ce13947f43b52ac0585bf9e6929579e8c83"
R1_RELEASE_CONTENT_SHA256 = "1e691df6b85576e0d75925cc7902a1f4e303267098483a81726f6ff63cda3046"
R1_RELEASE_JSON_SHA256 = "ccccd81eeb908b8001fa8ff70c0d28917bebc6f1df2a96d8fd335161f54cf7a9"
R1_RUN_ID = "r1-20261006"

WORK_ROOT = C.DEFAULT_WORK_ROOT
R1_RELEASE_DIR = WORK_ROOT / "release" / "r1"
R1_RUN_DIR = WORK_ROOT / "runs" / R1_RUN_ID

SCENES = C.MAIN_POOL_SCENES  # S1, S3, S4 only; no new S5 queries
LANES = ("N3-policy", "E3-policy", "F3-qwen3vl4b")
# Loaded-parameter digests recorded in R1 run receipts (vLLM apply_model over all named parameters).
R1_LOADED_DIGESTS = {
    "N3-policy": "eb00cb168c30728df7c7e33601f251cbd115b39eb181ac46949264d5724c731b",
    "E3-policy": "d5a618633fb5ae1cb794257ed9b2db7ea1725c9a4d439d08bceaf0f4fb291fe6",
    "F3-qwen3vl4b": "866dddcec41c1fd6c4521081fb89aa8a61041c4eefdfe0bade7c35df8d5cccdb",
}
LANE_ROLE = {
    "N3-policy": "executed Nano policy reasoner (identical to Qwen3-VL-8B-Instruct)",
    "E3-policy": "executed Edge policy reasoner (identical to Cosmos3-Edge base reasoner)",
    "F3-qwen3vl4b": "FLUX frozen shared Qwen3-VL-4B component: text-only B2 = language path; image tests auxiliary",
}

# ---------------------------------------------------------------- budgets (protocol.json)
EVAL_PER_LANE = {"b2_original": 540, "b2_placement": 144, "c2_initial": 480, "c2_secondary": 960, "c2_no_image": 60}
MAX_EVAL_PER_LANE = 2184
MAX_EVAL_TOTAL = 6552
MAX_QUAL_PER_LANE = 6
MAX_RETRIES_TOTAL = 30
MAX_RETRIES_PER_QUERY = 1
MAX_CONSECUTIVE_INFRA = 3
MAX_ATTEMPTS_TOTAL = 6600
MAX_NEW_TOKENS = 256

# ---------------------------------------------------------------- B2
B2_CONDITIONS = ("T", "H", "I", "IH")
B2_PLACEMENT_CONDITIONS = ("T", "IH")
HEADER_STRINGS = tuple(P.VIEW_HEADERS_START_POSE[v] for v in C.VIEW_KEYS)
RELATIONS = list(C.RELATION_VOCABULARY)


def b2_schema(objects: list[str]) -> dict:
    """Schema-constrained B2 output: one object, three required keys, complete scene vocabularies, no pruning."""
    vocab = sorted(objects)
    return {"type": "object",
            "properties": {"target": {"type": "string", "enum": vocab},
                           "reference": {"type": "string", "enum": vocab},
                           "relation": {"type": "string", "enum": RELATIONS}},
            "required": ["target", "reference", "relation"],
            "additionalProperties": False}


# ---------------------------------------------------------------- C2 (fixed wording, spec section 6)
C2_BODY = (
    "Instruction:\n{instruction}\n\n"
    "Treat the instruction as a description of a desired spatial relation between the named objects.\n"
    "Evaluate only their arrangement in the supplied current camera views. Whether anyone moved an object,\n"
    "whether a robot action occurred, and whether the arrangement was held over time are irrelevant.\n\n"
    "Which statement is supported by the current views?\n"
    "{options}\n"
    "Return exactly one code: A, B, or U."
)
OPTION_MATCH = "The current arrangement matches the spatial relation requested by the instruction."
OPTION_NONMATCH = "The current arrangement does not match the spatial relation requested by the instruction."
OPTION_UNKNOWN = "The supplied visual evidence is insufficient to determine whether it matches."
C2_ORDERS = {
    0: {"A": "match", "B": "nonmatch", "U": "unknown"},
    1: {"A": "nonmatch", "B": "match", "U": "unknown"},
}
SEMANTIC_TEXT = {"match": OPTION_MATCH, "nonmatch": OPTION_NONMATCH, "unknown": OPTION_UNKNOWN}
C2_CODES = ["A", "B", "U"]


def c2_options(order: int) -> str:
    m = C2_ORDERS[order]
    return "\n".join(f"{code}: {SEMANTIC_TEXT[m[code]]}" for code in C2_CODES)


def c2_body(instruction: str, order: int) -> str:
    return C2_BODY.format(instruction=instruction, options=c2_options(order))


def output_constraint(kind: str, objects: list[str] | None = None) -> dict:
    if kind == "B2":
        # Stored as an order-preserving JSON string: xgrammar enforces declared property order (target, reference,
        # relation, matching the wrapper's example) and manifests are written with sorted dictionary keys.
        return {"type": "json_schema", "schema_json": json.dumps(b2_schema(objects), separators=(",", ":"))}
    if kind == "C2":
        return {"type": "choice", "choices": list(C2_CODES)}
    raise ValueError(kind)


def constraint_sha256(constraint: dict) -> str:
    return C.canonical_sha256(constraint)


ENGINE_STRUCTURED = {"backend": "xgrammar", "disable_any_whitespace": True}


def frozen_v2_text() -> dict:
    return {"c2_body": C2_BODY, "c2_options": {o: c2_options(o) for o in C2_ORDERS}, "c2_orders": C2_ORDERS,
            "header_strings_removed_in_I_and_T": list(HEADER_STRINGS), "b2_wrapper": P.B_WRAPPER,
            "preamble": P.PREAMBLE, "relation_vocabulary": RELATIONS}


def v2_paths(release: str = "r2-final", run_id: str | None = None) -> dict[str, Path]:
    out = {"release": WORK_ROOT / "release" / release}
    if run_id:
        out["run"] = WORK_ROOT / "runs" / run_id
    return out


def assert_not_r1_path(path: Path) -> None:
    """V2 outputs must never be written into the R1 release or R1 run directories."""
    p = Path(path).resolve()
    for protected in (R1_RELEASE_DIR, R1_RUN_DIR):
        q = Path(protected).resolve()
        if p == q or q in p.parents:
            raise ValueError(f"refusing to write V2 output inside protected R1 path {q}")


def schema_of(constraint: dict) -> dict:
    return json.loads(constraint["schema_json"])


def schema_property_order(constraint: dict) -> list[str]:
    pairs = json.loads(constraint["schema_json"], object_pairs_hook=lambda kv: kv)
    props = dict(pairs)["properties"]
    return [k for k, _ in props]
