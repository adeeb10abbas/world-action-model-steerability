"""Frozen answer parsers (guide section 8). Frozen before inference; no post-result repair.

A/C: trim surrounding whitespace and at most one terminal punctuation mark; accept case-insensitive exact
yes/no/unknown. Anything else (verbose, conflicting, truncated, empty) is invalid.
B: exactly one JSON object with exactly the keys target/reference/relation, string values from the scene's
object vocabulary and the relation vocabulary. Duplicate keys are rejected. One frozen normalisation: a single
surrounding Markdown code fence (``` or ```json) is removed before parsing.
"""
from __future__ import annotations

import json
import re

PARSER_VERSION = "rqa-parse-1"
TERMINAL_PUNCT = ".!?,;:"
FENCE = re.compile(r"^```(?:json|JSON)?[ \t]*\n(.*)\n```$", re.DOTALL)


def parse_yes_no(text: str | None) -> dict:
    if text is None:
        return {"valid": False, "answer": None, "reason": "no_text"}
    s = text.strip()
    if s and s[-1] in TERMINAL_PUNCT:
        s = s[:-1].rstrip()
    low = s.lower()
    if low in ("yes", "no", "unknown"):
        return {"valid": True, "answer": low, "reason": None}
    return {"valid": False, "answer": None, "reason": "not_exactly_yes_no_unknown"}


class _DuplicateKey(ValueError):
    pass


def _no_dupes(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise _DuplicateKey(k)
        out[k] = v
    return out


def parse_b(text: str | None, objects: list[str], relations: list[str]) -> dict:
    if text is None:
        return {"valid": False, "answer": None, "reason": "no_text", "fence_removed": False}
    s = text.strip()
    fence = False
    m = FENCE.match(s)
    if m:
        s, fence = m.group(1).strip(), True
    try:
        obj = json.loads(s, object_pairs_hook=_no_dupes)
    except _DuplicateKey:
        return {"valid": False, "answer": None, "reason": "duplicate_key", "fence_removed": fence}
    except (json.JSONDecodeError, ValueError):
        return {"valid": False, "answer": None, "reason": "not_exactly_one_json_object", "fence_removed": fence}
    if not isinstance(obj, dict):
        return {"valid": False, "answer": None, "reason": "json_not_object", "fence_removed": fence}
    if set(obj) != {"target", "reference", "relation"}:
        return {"valid": False, "answer": None, "reason": "keys_not_exactly_target_reference_relation", "fence_removed": fence}
    if not all(isinstance(obj[k], str) for k in obj):
        return {"valid": False, "answer": None, "reason": "non_string_value", "fence_removed": fence}
    if obj["target"] not in objects or obj["reference"] not in objects:
        return {"valid": False, "answer": obj, "reason": "object_not_in_vocabulary", "fence_removed": fence}
    if obj["relation"] not in relations:
        return {"valid": False, "answer": obj, "reason": "relation_not_in_vocabulary", "fence_removed": fence}
    return {"valid": True, "answer": {k: obj[k] for k in ("target", "reference", "relation")}, "reason": None,
            "fence_removed": fence}
