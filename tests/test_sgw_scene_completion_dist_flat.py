"""Flat DIST is a 3D distance task with every body resting on the table."""
import copy
import importlib
import itertools
import json
import math
from collections import Counter
from pathlib import Path

import pytest

from experiments.workshops.spatial_grounding_v1.lat_workspace_capture import _rotate_wxyz


def api():
    spec = importlib.util.find_spec('experiments.workshops.spatial_grounding_v1.scene_completion_dist_flat')
    assert spec is not None, 'The flat-table DIST geometry generator is missing'
    return importlib.import_module(spec.name)


@pytest.fixture
def workspace():
    return json.loads(Path('artifacts/workshops/spatial_grounding_v1/infrastructure/a40-20260922z-workspace.json').read_text())


@pytest.mark.parametrize('side', ['left', 'right'])
def test_cube_bowl_and_plate_contact_table_without_any_pedestal(workspace, side):
    row = api().design(side, 0, 0, workspace)
    top = workspace['objects']['table']['bbox_env_local_max_xyz_m'][2]
    assert row['support_mode'] == 'flat-table'
    assert [spec['name'] for spec in row['supports']] == ['plate']
    assert row['object_names'] == ['rubiks_cube', 'bowl', 'banana', 'table', 'plate']
    assert row['goal_support_names'] == {'near_bowl': 'table', 'near_plate': 'table'}
    assert row['support_names'] == ['table']
    assert row['geometry_guard_support_ids'] == [], 'The reset guard already checks the table separately'
    for name in ('rubiks_cube', 'bowl', 'banana'):
        measured = workspace['objects'][name]
        bottom = row['roots'][name][2] + measured['bbox_env_local_min_xyz_m'][2] - measured['root_position_env_local_xyz_m'][2]
        assert bottom == pytest.approx(top, abs=1e-10)
        offset = _rotate_wxyz(row['orientations'][name], measured['geometric_center_offset_root_local_xyz_m'])
        assert [row['roots'][name][i] + offset[i] for i in range(3)] == pytest.approx(row['centers'][name], abs=1e-10)
    plate = row['supports'][0]
    assert plate['shape'] == 'cylinder' and plate['rigid_body'] and not plate.get('kinematic_body', False)
    assert plate['radius_m'] == .11
    assert plate['center_m'][2] - plate['thickness_m'] / 2 == pytest.approx(top)
    assert len({round(row['centers'][name][2], 6) for name in ('rubiks_cube', 'bowl', 'plate')}) == 3


@pytest.mark.parametrize('side', ['left', 'right'])
def test_neutrality_uses_true_3d_distances_and_short_lateral_goals(workspace, side):
    row = api().design(side, .02, -.01, workspace)
    cube, bowl, plate = [row['centers'][name] for name in ('rubiks_cube', 'bowl', 'plate')]
    assert abs(math.dist(cube, plate) - math.dist(cube, bowl)) < 1e-12
    assert (bowl[1] > plate[1]) == (side == 'left')
    assert abs(cube[1] - (bowl[1] + plate[1]) / 2) > .0001
    for sign, target in row['targets'].items():
        assert target[0] == cube[0] and target[2] == cube[2]
        assert math.dist(cube, target) == pytest.approx(.16)
        assert int(sign) * (math.dist(target, plate) - math.dist(target, bowl)) >= .03
        assert math.dist(target, [0, 0, 0]) < .65
    assert row['status'] == 'authored_unqualified' and row['model_requests'] == 0


@pytest.mark.parametrize('side,expected_y', [('left', -.100595), ('right', -.099405)])
def test_neutral_solve_changes_with_measured_asset_center_heights(workspace, side, expected_y):
    value = copy.deepcopy(workspace)
    # Hand-derived table-relative center heights: cube .030, bowl .040,
    # plate .006. Squared z-distance difference is .0001 - .000576.
    for name, half_height in (('rubiks_cube', .03), ('bowl', .04)):
        obj = value['objects'][name]
        center_z = obj['geometric_center_env_local_xyz_m'][2]
        obj['bbox_env_local_min_xyz_m'][2] = center_z - half_height
    row = api().design(side, 0, 0, value)
    assert row['centers']['rubiks_cube'][1] == pytest.approx(expected_y, abs=1e-12)


def test_campaign_is_distinct_balanced_and_clear_on_measured_table(workspace):
    module = api()
    for seed in (20260923, 20260924):
        rows = module.campaign(workspace, seed=seed, count=100)
        assert rows == module.campaign(workspace, seed=seed, count=100)
        prefix = rows[:29]
        assert Counter(row['side'] for row in prefix) == {('left', 'right')[seed % 2]: 15, ('right', 'left')[seed % 2]: 14}
        for first, second in itertools.combinations(prefix, 2):
            assert max(math.dist(first['centers'][n], second['centers'][n]) for n in ('rubiks_cube', 'bowl', 'plate')) > .006
        table = workspace['objects']['table']
        for row in rows:
            for bounds in row['authored_bounds'].values():
                assert bounds['min'][2] == pytest.approx(table['bbox_env_local_max_xyz_m'][2], abs=1e-10)
                assert all(table['bbox_env_local_min_xyz_m'][i] <= bounds['min'][i] < bounds['max'][i] <= table['bbox_env_local_max_xyz_m'][i] for i in (0, 1))
            for name in ('bowl', 'plate', 'banana'):
                a, b = row['transfer_bounds'], row['authored_bounds'][name]
                gap = math.hypot(*[max(a['min'][i] - b['max'][i], b['min'][i] - a['max'][i], 0) for i in (0, 1)])
                assert gap >= .02


@pytest.mark.parametrize('side,dx,dy', [('none', 0, 0), ('left', .041, 0), ('right', 0, float('nan'))])
def test_invalid_inputs_are_rejected(workspace, side, dx, dy):
    with pytest.raises(ValueError):
        api().design(side, dx, dy, workspace)


def test_out_of_table_asset_and_nonfinite_measurement_are_rejected(workspace):
    value = copy.deepcopy(workspace)
    value['objects']['table']['bbox_env_local_max_xyz_m'][0] = .70
    with pytest.raises(ValueError, match='table'):
        api().design('left', 0, 0, value)
    value = copy.deepcopy(workspace)
    value['objects']['bowl']['bbox_env_local_min_xyz_m'][2] = float('nan')
    with pytest.raises(ValueError, match='finite'):
        api().design('left', 0, 0, value)


def test_campaign_cannot_exceed_declared_candidate_cap(workspace):
    for count in (0, 101, True):
        with pytest.raises(ValueError):
            api().campaign(workspace, count=count)
