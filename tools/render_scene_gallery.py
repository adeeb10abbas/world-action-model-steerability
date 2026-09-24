"""Make a readable gallery from actual clean-scene simulator captures."""
from datetime import datetime, timezone
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'artifacts/workshops/spatial_grounding_v1/workstation_receipts_20260924'
EXAMPLES = (
    ('Left / right: robot-right approach', 'prototype-06-a'),
    ('Left / right: robot-left approach', 'SGW-COMPLETION-PROTOTYPES-20260924/SGW-COMPLETE-20260924-LAT-LEFT-000'),
    ('Higher / lower: upper support on the left', 'prototype-04-a'),
    ('Higher / lower: upper support on the right', 'prototype-05-a'),
    ('Closer / farther, flat table: bowl on the left', 'SGW-FLAT-DIST-PROTOTYPES-20260924-HEADLESS-A2/SGW-FLAT-DIST-LEFT-000'),
    ('Closer / farther, flat table: bowl on the right', 'SGW-FLAT-DIST-PROTOTYPES-20260924-HEADLESS-A2/SGW-FLAT-DIST-RIGHT-000'),
)


def main():
    lines = ['# Clean scene examples', '',
        'Actual simulator captures for the WAM steerability study. These show the '
        'initial scenes; the qualification status below comes from physical trial receipts. '
        'A passing example is not a claim that the full 87-layout set is complete.', '',
        'All scenes retain both shoulder cameras and the wrist camera. '
        'The images below are initial captures, not continuous recordings.', '',
        f"Updated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}.", '']
    for title, relative in EXAMPLES:
        folder = BASE / relative
        lines += [f'## {title}', '']
        receipt = folder / 'verification.json'
        if receipt.exists():
            result = json.loads(receipt.read_text())
            lines += [f"**Scripted trials: {result['passed_checks']}/6 passed.** "
                      'Both goals, three resets each.', '']
        else:
            lines += ['**Physical checks in progress.**', '']
        for camera, label in (('over_shoulder_left_camera', 'Left shoulder'),
                              ('over_shoulder_right_camera', 'Right shoulder'),
                              ('wrist_cam', 'Wrist')):
            image = folder / (camera + '.png')
            if image.is_file():
                path = '../' + image.relative_to(ROOT).as_posix()
                if camera == 'over_shoulder_left_camera':
                    lines += [f'![{title}: {label}]({path})', '']
                else:
                    lines += [f'[{label} camera]({path})', '']
    destination = ROOT / 'docs/CLEAN_SCENES.md'
    destination.write_text('\n'.join(lines).rstrip() + '\n')
    print(destination)


if __name__ == '__main__':
    main()
