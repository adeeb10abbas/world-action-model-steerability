"""Clean prospective DIST geometry with every object directly on the table.

No pedestal is authored. ``supports`` contains only the existing dynamic
visible plate disc because the scene writer uses that list for new bodies.
Both target contact IDs are rubiks_cube__table. The runner must derive target
z from its fresh measurement of table top plus cube center-to-bottom height.

Keep actual table-supported asset center heights. With bowl/plate at equal x,
y_b=y0+s*a and y_p=y0-s*a, neutrality is solved analytically as
y_c=y0+((z_c-z_b)^2-(z_c-z_p)^2)/(4*s*a). This equates squared 3D distances;
using the XY midpoint alone would ignore the anchors' unequal center heights.
The two goal positions are 16 cm lateral moves from this neutral cube center.

These are authored inputs, not native physical qualification. The robot,
cameras, calibrated controller, static prompts and scientific scorer are
unchanged. All selected rows still require both goals across three resets.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import math
import random
from typing import Any, Mapping

from .lat_workspace_capture import _rotate_wxyz
from .prospective_family_scene import _banana_root_on_table, _disc, _root_for_center


CAMPAIGN = 'SGW-FLAT-DIST-20260924'


def _validate_workspace(objects: Mapping[str, Any]) -> None:
    for name in ('rubiks_cube', 'bowl', 'banana', 'table'):
        obj = objects[name]
        for key, length in (('root_position_env_local_xyz_m', 3), ('root_quaternion_world_wxyz', 4),
                            ('geometric_center_env_local_xyz_m', 3), ('geometric_center_offset_root_local_xyz_m', 3),
                            ('bbox_env_local_min_xyz_m', 3), ('bbox_env_local_max_xyz_m', 3)):
            vector = obj[key]
            if len(vector) != length or not all(math.isfinite(value) for value in vector):
                raise ValueError(f'{name} requires finite measured {key}')
        if any(lo >= hi for lo, hi in zip(obj['bbox_env_local_min_xyz_m'], obj['bbox_env_local_max_xyz_m'])):
            raise ValueError(f'{name} has invalid measured bounds')


def _translated_bounds(obj: Mapping[str, Any], root: list[float]) -> dict[str, list[float]]:
    delta = [root[i] - obj['root_position_env_local_xyz_m'][i] for i in range(3)]
    return {label: [obj[f'bbox_env_local_{label}_xyz_m'][i] + delta[i] for i in range(3)]
            for label in ('min', 'max')}


def _xy_gap(first: Mapping[str, Any], second: Mapping[str, Any]) -> float:
    return math.hypot(*[max(first['min'][i] - second['max'][i], second['min'][i] - first['max'][i], 0.)
                        for i in (0, 1)])


def design(side: str, dx: float, dy: float, workspace: Mapping[str, Any]) -> dict[str, Any]:
    """Return one flat-table row compatible with the clean scene writer."""
    if side not in ('left', 'right'):
        raise ValueError('DIST bowl side must be left or right')
    if not all(math.isfinite(value) and abs(value) <= .04 for value in (dx, dy)):
        raise ValueError('Translations must be finite and within 40 mm per axis')
    objects = workspace['objects']
    _validate_workspace(objects)
    top = objects['table']['bbox_env_local_max_xyz_m'][2]
    sign = 1 if side == 'left' else -1
    midpoint_y, half_separation = -.10 + dy, .20
    cube_z = top + objects['rubiks_cube']['geometric_center_env_local_xyz_m'][2] - objects['rubiks_cube']['bbox_env_local_min_xyz_m'][2]
    bowl_z = top + objects['bowl']['geometric_center_env_local_xyz_m'][2] - objects['bowl']['bbox_env_local_min_xyz_m'][2]
    plate_z = top + .006
    correction = ((cube_z - bowl_z) ** 2 - (cube_z - plate_z) ** 2) / (4 * sign * half_separation)
    cube = [.46 + dx, midpoint_y + correction, cube_z]
    bowl = [.68 + dx, midpoint_y + sign * half_separation, bowl_z]
    plate = [.68 + dx, midpoint_y - sign * half_separation, plate_z]
    targets = {str(goal): [cube[0], cube[1] + goal * sign * .16, cube_z] for goal in (1, -1)}
    roots = {name: _root_for_center(objects[name], center)
             for name, center in (('rubiks_cube', cube), ('bowl', bowl))}
    roots['banana'] = _banana_root_on_table(workspace)
    orientations = {name: list(objects[name]['root_quaternion_world_wxyz']) for name in roots}
    offset = _rotate_wxyz(orientations['banana'], objects['banana']['geometric_center_offset_root_local_xyz_m'])
    banana = [roots['banana'][i] + offset[i] for i in range(3)]
    bounds = {name: _translated_bounds(objects[name], root) for name, root in roots.items()}
    bounds['plate'] = {'min': [plate[0] - .11, plate[1] - .11, top],
                       'max': [plate[0] + .11, plate[1] + .11, top + .012]}
    goal_bounds = [_translated_bounds(objects['rubiks_cube'], _root_for_center(objects['rubiks_cube'], target))
                   for target in targets.values()]
    corridor = {'min': [min(b['min'][i] for b in goal_bounds) for i in range(3)],
                'max': [max(b['max'][i] for b in goal_bounds) for i in range(3)]}
    table = objects['table']
    for name, box in [*bounds.items(), ('cube transfer corridor', corridor)]:
        if abs(box['min'][2] - top) > 1e-8:
            raise ValueError(f'{name} does not contact the measured table plane')
        if any(box['min'][i] < table['bbox_env_local_min_xyz_m'][i]
               or box['max'][i] > table['bbox_env_local_max_xyz_m'][i] for i in (0, 1)):
            raise ValueError(f'{name} leaves the measured table bounds')
    for first, second in itertools.combinations(bounds, 2):
        if _xy_gap(bounds[first], bounds[second]) < .02:
            raise ValueError(f'Authored {first}/{second} clearance is below 20 mm')
    for name in ('bowl', 'plate', 'banana'):
        if _xy_gap(corridor, bounds[name]) < .02:
            raise ValueError(f'Authored transfer clearance from {name} is below 20 mm')
    for goal, target in targets.items():
        if int(goal) * (math.dist(target, plate) - math.dist(target, bowl)) < .03:
            raise ValueError('Authored goal lacks the 30 mm Euclidean margin')
    identity = hashlib.sha256(json.dumps([side, dx, dy], separators=(',', ':')).encode()).hexdigest()[:12]
    return {
        'design_id': f'{CAMPAIGN}-{identity}', 'family': 'DIST', 'side': side,
        'variant': 'flat-table-v1', 'support_mode': 'flat-table', 'visual_style': 'clean-studio-v1',
        'translation_xy_m': [dx, dy], 'status': 'authored_unqualified', 'model_requests': 0,
        'centers': {'rubiks_cube': cube, 'bowl': bowl, 'plate': plate, 'banana': banana},
        'roots': roots, 'orientations': orientations, 'targets': targets,
        'supports': [_disc('plate', tuple(plate), radius_m=.11, thickness_m=.012,
                           color=(.94, .94, .90), rigid=True)],
        'object_names': ['rubiks_cube', 'bowl', 'banana', 'table', 'plate'],
        'scored_object_names': ['rubiks_cube', 'bowl', 'plate'], 'anchor_object_names': ['bowl', 'plate'],
        # The pre-action guard handles the table separately. Its additional
        # support list must not include the table beneath the parked banana.
        'support_names': ['table'], 'geometry_guard_support_ids': [],
        'goal_support_names': {'near_bowl': 'table', 'near_plate': 'table'},
        'authored_bounds': bounds, 'transfer_bounds': corridor,
        'neutral_geometry': {'table_top_z_m': top, 'anchor_midpoint_y_m': midpoint_y,
                             'cube_y_correction_m': correction, 'relation_m': math.dist(cube, plate) - math.dist(cube, bowl)},
        'source_provenance': {'measured_workspace_receipt_sha256': workspace.get('receipt_sha256'),
                              'plate_implementation': 'prospective_family_scene._disc',
                              'qualification_inheritance': False},
        'plate_category_caveat': 'Existing simplified off-white disc; policy-sized recognition still requires visual review.',
        'qualification_requirements': {'initial_neutral_tolerance_m': .005, 'relation_margin_m': .03,
                                       'reference_motion_limit_m': .005, 'action_cap': 450,
                                       'goal_signs': [1, -1], 'reset_indices': [0, 1, 2],
                                       'released_supported_stable_cube': True},
    }


def campaign(workspace: Mapping[str, Any], seed: int = 20260923, count: int = 100) -> list[dict[str, Any]]:
    """Finite distinct pool; a 29-row prefix has 15 pilot-side and 14 other rows."""
    if not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= 100:
        raise ValueError('A flat DIST campaign has 1..100 candidate slots')
    grid = [(x / 1000, y / 1000) for x in range(-40, 41, 10) for y in range(-40, 41, 10)]
    random.Random(seed).shuffle(grid)
    rows = []
    for index in range(count):
        row = design(('left', 'right')[(seed + index) % 2], *grid[index // 2], workspace)
        row.update(design_id=f'{CAMPAIGN}-{index:03d}', seed=seed, ordinal=index)
        rows.append(row)
    return rows
