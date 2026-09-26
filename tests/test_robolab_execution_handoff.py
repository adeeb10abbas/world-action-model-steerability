"""CPU boundary checks for a planning inventory that must never imply a launch."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
loader = importlib.util.spec_from_file_location("handoff_builder", ROOT / "tools/build_robolab_execution_handoff.py")
module = importlib.util.module_from_spec(loader)
loader.loader.exec_module(module)


class HandoffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads((module.SPEC / "prompt_matrix.json").read_text())
        cls.config = (module.SPEC / "MODEL_CONFIGS.json").read_bytes()
        cls.rows, cls.blocks = module.enumerate_plan(cls.catalog, cls.config)

    def test_exact_native_whitespace_and_budget(self):
        row = next(r for r in self.rows if r["prompt_id"] == "S4-TOP-D")
        self.assertEqual(row["prompt"], "Place the mustard on the raisin box. ")
        self.assertEqual(len(self.rows), 1054)
        self.assertFalse(any(r["physical_state_bound"] for r in self.rows))

    def test_missing_form_is_rejected(self):
        catalog = copy.deepcopy(self.catalog)
        catalog["scenes"][0]["goals"][0]["prompts"].pop()
        with self.assertRaisesRegex(ValueError, "Missing or duplicated"):
            module.enumerate_plan(catalog, self.config)

    def test_unknown_snapshot_cannot_be_claimed_bound(self):
        rows = copy.deepcopy(self.rows)
        rows[0]["physical_state_bound"] = True
        with self.assertRaisesRegex(ValueError, "must not pretend"):
            module.validate(rows, self.blocks, self.catalog)

    def test_duplicate_dispatch_is_rejected(self):
        blocks = copy.deepcopy(self.blocks)
        blocks["blocks"].append(copy.deepcopy(blocks["blocks"][0]))
        with self.assertRaisesRegex(ValueError, "omit or duplicate"):
            module.validate(self.rows, blocks, self.catalog)

    def test_prompt_normalization_is_rejected(self):
        rows = copy.deepcopy(self.rows)
        row = next(r for r in rows if r["prompt_id"] == "S4-TOP-D")
        row["prompt"] = row["prompt"].strip()
        with self.assertRaisesRegex(ValueError, "Changed prompt"):
            module.validate(rows, self.blocks, self.catalog)


if __name__ == "__main__":
    unittest.main()
