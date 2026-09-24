"""Bounded camera diagnostics on an existing materialized layout; no policy client.

Uses the production joint-position task and camera preset directly. This does
not create a release, validate a model runtime, or rerun physical goal trials.
One process per layout; two resets and three hold-position steps only.
"""
from __future__ import annotations
import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import subprocess
import traceback


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--materialized', type=Path, required=True)
    parser.add_argument('--layout', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--study-root', type=Path, required=True)
    from isaaclab.app import AppLauncher
    from robolab.eval.runner import add_common_eval_args
    add_common_eval_args(parser)
    AppLauncher.add_app_launcher_args(parser)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    binding = json.loads((args.materialized / 'environment-binding.json').read_text())
    matches = [r for r in binding['cells'].values() if r['layout_id'] == args.layout]
    record = matches[0]
    from experiments.workshops.spatial_grounding_v1.fixtures import FixtureCandidate
    from experiments.workshops.spatial_grounding_v1.recorder import atomic_json
    candidate_path = Path(record['candidate_path'])
    assert sha(candidate_path) == record['candidate_file_sha256']
    candidate = FixtureCandidate.from_json(json.loads(candidate_path.read_text()))
    cell = next(json.loads(line) for line in (args.materialized / 'bound-cells.jsonl').read_text().splitlines()
                if json.loads(line)['layout_id'] == args.layout)
    payload = json.dumps({'candidate': candidate.task_payload(), 'prompt': cell['prompt']}, sort_keys=True, allow_nan=False)
    os.environ['SGW01_JOINTPOS_CELL_JSON'] = payload
    os.environ['SGW01_JOINTPOS_CELL_SHA256'] = hashlib.sha256(payload.encode()).hexdigest()
    receipt = {'schema': 'sgw-camera-capture-v1', 'layout_id': args.layout,
               'candidate_sha256': sha(candidate_path), 'candidate_id': candidate.candidate_id,
               'source_commit': subprocess.check_output(['git', '-C', str(args.study_root), 'rev-parse', 'HEAD'], text=True).strip(),
               'script_sha256': sha(__file__), 'model_requests': 0, 'learned_policy_episodes': 0,
               'physical_qualification_trials': 0, 'hold_steps': 3, 'resets': 2,
               'purpose': 'camera diagnostics only; not a study release', 'snapshots': []}
    atomic_json(args.output / 'started.json', receipt)
    args.enable_cameras = True
    app = AppLauncher(args).app
    env = None
    try:
        import numpy as np
        import torch
        from PIL import Image
        import robolab.constants
        from robolab.constants import set_output_dir
        from robolab.core.environments.runtime import create_env
        from robolab.core.environments.config import parse_env_cfg
        from robolab.core.world.world_state import get_world
        from robolab.registrations.droid.auto_env_registrations_jointpos import auto_register_droid_envs
        from robolab.registrations.droid.camera_presets import WRIST_LEFT_RIGHT_HEAD
        from experiments.workshops.spatial_grounding_v1.robolab_jointpos_environment import configure_clean_appearance, JointPositionEnvironment
        from experiments.workshops.spatial_grounding_v1.policy_observations import CAMERAS
        robolab.constants.ENABLE_SUBTASK_PROGRESS_CHECKING = False
        robolab.constants.RECORD_IMAGE_DATA = False
        robolab.constants.VERBOSE = False
        set_output_dir(str(args.output / 'native'))
        auto_register_droid_envs(task=[str(args.study_root / 'experiments/workshops/spatial_grounding_v1/sgw_jointpos_task.py')], cameras=WRIST_LEFT_RIGHT_HEAD)
        cfg = parse_env_cfg('SGWJointPositionTask', device=args.device, seed=record['scene_seed'], num_envs=1)
        configure_clean_appearance(cfg, candidate)
        from experiments.workshops.spatial_grounding_v1.camera_configuration import configure_study_cameras, camera_configuration_identity
        configure_study_cameras(cfg, candidate)
        receipt['camera_configuration'] = camera_configuration_identity()
        env, _ = create_env(cfg, device=args.device, seed=record['scene_seed'], num_envs=1,
                            instruction_type='default', policy='camera_diagnostic_no_model', renderer='realtime', rendering_mode='balanced')
        wrapper = JointPositionEnvironment(env, candidate=candidate, cell_id='camera-check:'+args.layout, evidence_root=args.output / 'reset-evidence')
        to_np = lambda value: value.detach().cpu().numpy() if hasattr(value, 'detach') else np.asarray(value)

        def capture(label):
            obs = wrapper.policy_observation()
            folder = args.output / label
            folder.mkdir()
            images = obs['image_obs']
            cameras = {}
            for name in CAMERAS:
                camera = env.scene[name]
                data = camera.data
                rgb = images[name][0]
                sensor_rgb = to_np(data.output['rgb'])[0, :, :, :3]
                assert np.array_equal(sensor_rgb, rgb), name+' observation/sensor mismatch'
                assert rgb.shape == (720, 1280, 3) and rgb.dtype == np.uint8 and np.ptp(rgb)
                Image.fromarray(rgb).save(folder / (name+'.png'))
                cameras[name] = {
                    'K': to_np(data.intrinsic_matrices[0]).tolist(),
                    'position_world_m': to_np(data.pos_w[0]).tolist(),
                    'quaternion_world_wxyz': to_np(data.quat_w_world[0]).tolist(),
                    'quaternion_ros_wxyz': to_np(data.quat_w_ros[0]).tolist(),
                    'quaternion_opengl_wxyz': to_np(data.quat_w_opengl[0]).tolist(),
                    'frame': int(to_np(camera.frame)[0]),
                    'sensor_timestamp_s': float(to_np(camera._timestamp)[0]),
                    'image_sha256': sha(folder / (name+'.png')),
                    'observation_equals_sensor_rgb': True,
                    'shape': list(rgb.shape), 'prim_path': camera.cfg.prim_path,
                }
            world = get_world(env)
            origin = to_np(env.scene.env_origins[0])
            objects = {}
            for name in candidate.metadata['native_scene']['object_names']:
                if name in ('table', 'banana'):
                    continue
                corners, center = world.get_bbox(name, env_id=0)
                objects[name] = {'center_world_m': (to_np(center)+origin).tolist(),
                                 'bbox_world_m': (np.array([to_np(v) for v in corners])+origin).tolist()}
            robot = env.scene['robot'].data
            index = list(robot.body_names).index('base_link')
            result = {'label': label, 'camera': cameras, 'objects': objects,
                      'world_origin_m': origin.tolist(), 'control_step_dt_s': float(env.step_dt),
                      'simulation_time_s': float(env.sim.current_time),
                      'gripper_base': {'position_world_m': to_np(robot.body_pos_w[0,index]).tolist(),
                                       'quaternion_wxyz': to_np(robot.body_quat_w[0,index]).tolist()}}
            atomic_json(folder / 'capture.json', result)
            np.savez_compressed(folder / 'observation.npz', **{**images, **obs['proprio_obs']})
            receipt['snapshots'].append(result)
            return obs

        reset = wrapper.reset()
        receipt['first_reset'] = dict(reset.receipt)
        obs = capture('reset-1')
        hold = np.concatenate([obs['proprio_obs']['arm_joint_pos'][0], obs['proprio_obs']['gripper_pos'][0]])
        for step in range(1, 4):
            wrapper.step(hold)
            capture(f'hold-{step}')
        reset = wrapper.reset()
        receipt['second_reset'] = dict(reset.receipt)
        capture('reset-2')
        receipt['status'] = 'captured'
        atomic_json(args.output / 'receipt.json', receipt)
        print(json.dumps({'layout': args.layout, 'status': receipt['status']}), flush=True)
    except BaseException:
        receipt['status'] = 'failed'
        receipt['error'] = traceback.format_exc()
        atomic_json(args.output / 'failure.json', receipt)
        raise
    finally:
        if env is not None:
            env.close()
        app.close()


if __name__ == '__main__':
    main()
