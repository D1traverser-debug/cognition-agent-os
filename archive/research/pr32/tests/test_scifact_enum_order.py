"""Evidence-classification order perturbation: local causal unit controls.

The output grammar may change presentation order, but it must never
change the submitted claim, evidence, grant or scoring ground truth.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch


class LabelOrderStudyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path=Path(__file__).resolve().parents[1]/"scripts"/"measure_scifact_enum_order.py"
        spec=importlib.util.spec_from_file_location("claim_label_order_study",path)
        cls.module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def test_local_comparison_smoke_without_provider(self):
        self.module.smoke()

    def test_only_enum_order_changes_in_actual_call_payload(self):
        from cognition_agent_os import local_model
        seen=[]
        def fake(method,endpoint,payload,timeout):
            seen.append(payload)
            return {"done":True, "response":'{"label":"CONTRADICT"}'}
        with patch.object(local_model,"_request",side_effect=fake):
            for order in ("support_first","contradict_first"):
                self.assertEqual(self.module.infer_claim("SAME EXACT PROMPT",order)["prediction"],
                                 "CONTRADICT")
        self.assertEqual(len(seen),2)
        a,b=seen
        self.assertEqual(a["model"],b["model"])
        self.assertEqual(a["prompt"],b["prompt"])
        self.assertEqual(a["options"],b["options"])
        self.assertEqual(a["stream"],b["stream"])
        self.assertEqual(a["keep_alive"],b["keep_alive"])
        self.assertEqual(a["format"]["properties"]["label"]["enum"],
                         ["SUPPORT","CONTRADICT","INSUFFICIENT"])
        self.assertEqual(b["format"]["properties"]["label"]["enum"],
                         ["CONTRADICT","SUPPORT","INSUFFICIENT"])
        copied=dict(a)
        copied["format"]=b["format"]
        self.assertEqual(copied,b)

    def test_gold_cannot_disappear_when_schema_order_flips(self):
        m=self.module
        records=[]
        for index in range(12):
            for label in ("SUPPORT","CONTRADICT"):
                for condition in m.CONDITIONS:
                    for order in m.ORDERS:
                        # Build asymmetrical outputs that prove paired swap
                        # accounting does not silently overwrite original gold.
                        predicted=("INSUFFICIENT" if condition=="no_evidence"
                                   else label if order=="contradict_first"
                                   else "SUPPORT")
                        records.append({"claim_id":label+str(index),
                            "condition":condition,"order":order,
                            "external_gold":label,"prediction":predicted,
                            "latency_s":.02})
        scores=m.score(records)
        f=scores["within_claim_order_effect"]["full_abstract"]
        self.assertEqual(f["changed_prediction"],12)
        self.assertEqual(f["only_contradict_first_correct"],12)
        self.assertEqual(f["only_support_first_correct"],0)
        self.assertEqual(scores["by_order_condition"]["support_first/full_abstract"]["correct"],12)
        self.assertEqual(scores["by_order_condition"]["contradict_first/full_abstract"]["correct"],24)

    def test_label_schema_unapproved_choice_rejected(self):
        with self.assertRaises(ValueError):
            self.module.ordered_schema("MODEL_CHOOSES_ANYTHING")


if __name__=="__main__":
    unittest.main()
