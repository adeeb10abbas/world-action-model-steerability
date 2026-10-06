"""Frozen RQA-20261006 query wrappers (design v1.0 guide section 4) and message rendering.

A query payload is a list of segments: {"type": "text", "text": ...} or {"type": "image", "image_id": ...}.
The exact original instruction bytes are inserted unchanged. Nothing here sees gold labels or outcomes.
"""
from __future__ import annotations

from . import common as C

WRAPPER_VERSION = "rqa-wrappers-1"

PREAMBLE = (
    "Task: answer a question about a robot's tabletop workspace.\n"
    "Coordinate frame: all spatial terms use the robot's frame of reference. The robot faces the workspace; "
    "\"left\" and \"right\" are from the robot's point of view, \"in front of\" means closer to the robot, and "
    "\"behind\" means farther from the robot."
)

# Calibration-derived legend (pinned camera extrinsics at the robot's starting pose; identical for all 32
# starts). Exterior cameras are static. Wording fixed before any model answer was generated.
VIEW_HEADERS_START_POSE = {
    "wrist_cam": ("Wrist camera (mounted on the robot's gripper; in this image the robot's left is toward the "
                  "image's right side and farther from the robot is toward the image's bottom):"),
    "over_shoulder_left_camera": ("Left exterior camera (mounted on the robot's left side; in this image the robot's left "
                                  "is toward the image's lower left and farther from the robot is toward the image's upper left):"),
    "over_shoulder_right_camera": ("Right exterior camera (mounted on the robot's right side; in this image the robot's left "
                                   "is toward the image's upper left and farther from the robot is toward the image's upper right):"),
}
WRIST_HEADER_MOVING = ("Wrist camera (mounted on the robot's gripper; it moves with the gripper, so its image "
                       "orientation is not fixed):")

A_ANSWER_LINE = ("Answer with exactly one of: yes, no, unknown. Judge the current visible scene in the robot "
                 "coordinate frame.")

B_WRAPPER = (
    "Instruction:\n{instruction}\n\n"
    "Interpret the requested outcome, not the current arrangement. Return one JSON object:\n"
    "{{\"target\": \"...\", \"reference\": \"...\", \"relation\": \"...\"}}\n"
    "The target is the object the instruction asks to move. The relation is the target's\n"
    "requested final relation to the reference. Use the provided object and relation vocabulary."
)

C_WRAPPER = (
    "Instruction:\n{instruction}\n\n"
    "Does the current scene show the final spatial arrangement requested by this instruction?\n"
    "Judge the arrangement now, not whether the robot moved the correct object or will succeed later.\n"
    "Do not require a one-second dwell or infer an unseen action history.\n"
    "Answer with exactly one of: yes, no, unknown."
)

S5_IDENTITY_NOTE = ("Bowl names that refer to left or right (such as \"the left bowl\" or \"the bowl initially on the "
                    "left\") refer to the bowls' positions at the start of the episode (t = 0.0 s), not their current "
                    "positions.")


def vocabulary_block(objects: list[str]) -> str:
    return ("Object vocabulary: " + ", ".join(sorted(objects)) + "\n"
            "Relation vocabulary: " + ", ".join(C.RELATION_VOCABULARY))


def view_segments(images: dict[str, str], wrist_moving: bool, title: str) -> list[dict]:
    segs: list[dict] = [{"type": "text", "text": title}]
    for view in C.VIEW_KEYS:
        header = WRIST_HEADER_MOVING if (view == "wrist_cam" and wrist_moving) else VIEW_HEADERS_START_POSE[view]
        segs.append({"type": "text", "text": "\n" + header + "\n"})
        segs.append({"type": "image", "image_id": images[view], "view": view})
    return segs


def build_segments(*, test: str, question_text: str | None = None, instruction: str | None = None,
                   objects: list[str] | None = None, current: dict[str, str] | None = None,
                   current_time_s: float | None = None, wrist_moving: bool = False,
                   start_reference: dict[str, str] | None = None) -> list[dict]:
    """Assemble one fresh single-turn user message. Images are referenced by release image id."""
    segs: list[dict] = [{"type": "text", "text": PREAMBLE}]
    if start_reference is not None:
        segs.append({"type": "text", "text": "\n\n" + S5_IDENTITY_NOTE + "\n\n"})
        segs += view_segments(start_reference, False, "Camera views at the start of the episode (t = 0.0 s), "
                                                     "captured at the same moment:")
        segs.append({"type": "text", "text": "\n\n"})
        segs += view_segments(current, wrist_moving, f"Camera views at the current time (t = {current_time_s:.1f} s), "
                                                     "captured at the same moment:")
    elif current is not None:
        segs.append({"type": "text", "text": "\n\n"})
        segs += view_segments(current, wrist_moving, "Camera views of the current scene, captured at the same moment:")
    if test == "A":
        body = f"Question: {question_text}\n{A_ANSWER_LINE}"
    elif test == "B":
        body = vocabulary_block(objects) + "\n\n" + B_WRAPPER.format(instruction=instruction)
    elif test == "C":
        body = C_WRAPPER.format(instruction=instruction)
    else:
        raise ValueError(test)
    segs.append({"type": "text", "text": "\n\n" + body})
    return merge_text(segs)


def merge_text(segs: list[dict]) -> list[dict]:
    out: list[dict] = []
    for s in segs:
        if s["type"] == "text" and out and out[-1]["type"] == "text":
            out[-1] = {"type": "text", "text": out[-1]["text"] + s["text"]}
        else:
            out.append(dict(s))
    return out


def full_prompt_text(segs: list[dict]) -> str:
    """Canonical text rendering with image references (manifest field `full_prompt`)."""
    parts = []
    for s in segs:
        parts.append(s["text"] if s["type"] == "text" else f"<image:{s['image_id']}>")
    return "".join(parts)


def frozen_text_constants() -> dict:
    return {"wrapper_version": WRAPPER_VERSION, "preamble": PREAMBLE, "view_headers_start_pose": VIEW_HEADERS_START_POSE,
            "wrist_header_moving": WRIST_HEADER_MOVING, "a_answer_line": A_ANSWER_LINE, "b_wrapper": B_WRAPPER,
            "c_wrapper": C_WRAPPER, "s5_identity_note": S5_IDENTITY_NOTE, "relation_vocabulary": list(C.RELATION_VOCABULARY),
            "object_vocabulary_order": "sorted (alphabetical) catalog identifiers"}
