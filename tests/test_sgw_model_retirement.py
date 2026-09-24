"""Retired models must not reach runtime setup or new execution releases."""
import hashlib
import json

import pytest

from experiments.workshops.spatial_grounding_v1 import adapters, contract, runtime
from tools.prepare_cluster_handoff import prepare_partitions


def test_new_handoff_excludes_retired_model_and_keeps_complete_blocks():
    handoff = prepare_partitions()
    assert {p['model'] for p in handoff['partitions']} == {'N3', 'E3', 'F3'}
    assert handoff['total_cells'] == 1566
    assert handoff['total_matched_blocks'] == 261
    assert handoff['partition_count'] == 27
    assert handoff['stage_cell_counts'] == {'P': 54, 'D': 216, 'C': 1296}
    assert not handoff['learned_policy_launch_authorized']


def test_retired_model_rejected_before_runtime_setup():
    with pytest.raises(adapters.AdapterError, match='retired'):
        adapters.make_adapter('D1', cell_id='old', prompt='old', transport=lambda _: {})
    with pytest.raises(adapters.AdapterError, match='retired'):
        adapters.load_production_adapter('D1')
    with pytest.raises(adapters.AdapterError, match='retired'):
        runtime.create_runtime(model='D1', config=adapters.DREAMZERO_CONFIG)


@pytest.mark.parametrize('model', ['E3', 'F3'])
def test_new_models_do_not_fall_back_to_a_different_runtime(model):
    adapter = adapters.make_adapter(model, cell_id='new', prompt='unchanged', transport=lambda _: {})
    assert adapter.config['model'] == model
    assert adapter.config != adapters.NANO_CONFIG
    with pytest.raises(adapters.AdapterError, match='exact SGW-01 model identity'):
        runtime.create_runtime(model=model, config={})


def test_retired_queue_cannot_be_loaded_as_execution_release(tmp_path):
    prompt = 'Place the cube left of the bowl.'
    row = dict.fromkeys(('cell_id', 'block_id', 'layout_id', 'prompt_id',
                         'fixture_sha256', 'runtime_sha256', 'time_map_sha256'), 'test')
    row.update(model='D1', family='LAT', stage='P', release_id='old', status='RELEASED',
               prompt=prompt, prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),
               within_block_order=1)
    path = tmp_path / 'queue.jsonl'
    path.write_text(json.dumps(row) + '\n')
    with pytest.raises(contract.ContractError, match='model'):
        contract._load_cells(path, 'old')
