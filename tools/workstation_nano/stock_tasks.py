"""Prospective stock RoboLab task selection for the second Nano pilot."""

from common import CHECKPOINT, COSMOS_COMMIT, REVISION, ROBOLAB_COMMIT, SEED, SERVER_CONFIG

# Native task names, native default instructions, native episode limits.
TASKS = {
    "RubiksCubeInFrontOfBowlTask": ("Put the rubiks cube in front of the bowl", 30),
    "RubiksCubeBehindBowlTask": ("Put the rubiks cube behind the bowl", 30),
    "ButterAboveRaisinTask": ("Pick up the butter box and place it on top of the raisin box", 40),
    "MustardAboveRaisinTask": ("Place the mustard on the raisin box. ", 40),
    "MustardInLeftBinTask": ("Put the mustard in the left bin", 30),
    "MustardInRightBinTask": ("Put the mustard in the right bin", 30),
    "BowlStackingLeftOnRightTask": ("Stack the left bowl on the right bowl", 20),
    "BowlStackingRightOnLeftTask": ("Stack the right bowl on the left bowl", 20),
    "WhiteMugInCenterOfTableTask": ("Put the white mug in the center of the table.", 30),
}


def plan():
    cells = [{"task": task, "prompt": prompt, "native_horizon_seconds": seconds,
              "maximum_control_steps": seconds * 15,
              "maximum_requests": (seconds * 15 + 31) // 32}
             for task, (prompt, seconds) in TASKS.items()]
    return {
        "study": "stock-nano-spatial-task-pilot-20260926",
        "scope": "One episode per stock task, selected before outcomes; not a success-rate estimate.",
        "tasks": cells, "environment_seed": SEED, "policy_seed": SEED,
        "maximum_control_steps": sum(cell["maximum_control_steps"] for cell in cells),
        "maximum_requests": sum(cell["maximum_requests"] for cell in cells),
        "termination": "Unmodified native success and timeout conditions; early success enabled.",
        "cameras": "Original WRIST_LEFT_RIGHT_HEAD; policy receives wrist, left and right.",
        "server_config": SERVER_CONFIG, "checkpoint": CHECKPOINT,
        "checkpoint_revision": REVISION, "cosmos_commit": COSMOS_COMMIT,
        "robolab_commit": ROBOLAB_COMMIT,
        "comparison": "Same Nano configuration as the earlier wording pilot; native scenes and horizons differ.",
        "forecast_scoring": "Raw futures retained; camera and physical-time correspondence remain unqualified.",
    }
