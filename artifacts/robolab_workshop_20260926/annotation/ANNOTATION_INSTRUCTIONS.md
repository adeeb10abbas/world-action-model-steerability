# Forecast annotation instructions (rubric v2)

Each packet `packets/<annotation_id>/` contains:

- `forecast.mkv`: the generated forecast at 15 fps (lossless). Only frames up to the last action the robot actually
  executed are included. The top pane is the wrist camera; the two bottom panes are the exterior cameras.
- `contact_sheet.png`: every fourth frame of the forecast, plus the last frame.
- `legend.png`: the real starting scene from the two exterior cameras. Yellow circles give object numbers. The cyan
  arrow points to the robot's left; the magenta arrow points away from the robot ("farther").

You are **not** told the instruction, the model, the goal or what really happened. Please do not try to find out.
Label only what the forecast shows. Fill one row per packet in `labels_template.csv` (keep your own copy; do not
look at the other annotator's file):

| Field | Allowed values |
|---|---|
| moving_object | legend number, `none`, `multiple`, `unknown` |
| direction | `left`, `right`, `closer_to_robot`, `farther_from_robot`, `up_only`, `none`, `unknown` — robot frame, use the legend arrows |
| visible_final_relation | `left_of`, `right_of`, `closer_to_robot_than`, `farther_from_robot_than`, `on_top_of`, `inside`, `stacked_in`, `none`, `ambiguous`, `unknown` — at the last frame |
| relation_object | legend number the relation refers to, `none`, `unknown` |
| possible_release | `yes`, `no`, `unknown` — gripper visibly opens and separates from the object |
| missing_object | `yes`, `no`, `unknown` — a legend object vanishes or becomes unrecognisable while not occluded |
| hallucinated_object | `yes`, `no`, `unknown` — a new object appears that is not in the legend |
| unknown_reason | `none`, `occluded`, `blurred_or_degenerate`, `no_motion_resolvable` |

RGB cannot show support forces or containment that is hidden from view. Use `ambiguous` or `unknown` rather than
guessing. When both annotators have finished, disagreements are adjudicated, and both original files are kept.
Then run:

    python -m experiments.robolab_workshop.annotation unblind --out $R/annotation \
        --labels annotator_a.csv annotator_b.csv [--adjudication adjudicated.csv] --dest $R/analysis/forecast_labels.jsonl
