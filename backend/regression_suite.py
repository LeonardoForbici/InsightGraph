"""
Regression suite for InsightGraph core CAST-local capabilities.

Focus:
- CALLS -> CALLS_RESOLVED accuracy
- Interface / inheritance call resolution
- CK metric coherence (LCOM)
- Call resolution diagnostics
- Local RAG index persistence
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import main as ig_main


class CoreRegressionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._orig_nodes = list(ig_main.memory_nodes)
        self._orig_edges = list(ig_main.memory_edges)
        self._orig_rag_index = list(ig_main.rag_index)
        self._orig_rag_meta = dict(getattr(ig_main, "rag_index_metadata", {}))
        self._orig_rag_file = ig_main.RAG_INDEX_FILE

    def tearDown(self) -> None:
        ig_main.memory_nodes = self._orig_nodes
        ig_main.memory_edges = self._orig_edges
        ig_main.rag_index = self._orig_rag_index
        ig_main.rag_index_metadata = self._orig_rag_meta
        ig_main.RAG_INDEX_FILE = self._orig_rag_file

    def test_resolve_calls_with_owner_hint(self) -> None:
        entities = {
            "nodes": [
                {"label": "TS_Function", "namespace_key": "p:a.ts:UserService.findById", "name": "findById", "file": "a.ts", "project": "p", "parent_class": "UserService"},
                {"label": "TS_Function", "namespace_key": "p:a.ts:UserController.getUser", "name": "getUser", "file": "a.ts", "project": "p", "parent_class": "UserController"},
            ],
            "relationships": [
                {
                    "from": "p:a.ts:UserController.getUser",
                    "to": "p:a.ts:UserService.findById",
                    "type": "CALLS",
                    "target_method_hint": "findById",
                    "target_owner_hint": "UserService",
                }
            ],
        }
        ig_main._resolve_internal_calls(entities, max_hops=3)
        resolved = [
            r for r in entities["relationships"]
            if r.get("type") == "CALLS_RESOLVED"
        ]
        self.assertEqual(len(resolved), 1)
        self.assertEqual(resolved[0]["to"], "p:a.ts:UserService.findById")

    def test_java_interface_resolution(self) -> None:
        entities = {
            "nodes": [
                {"label": "Java_Class", "namespace_key": "p:A.java:UserRepositoryImpl", "name": "UserRepositoryImpl", "file": "A.java", "project": "p", "implements_interfaces": ["UserRepository"]},
                {"label": "Java_Method", "namespace_key": "p:A.java:UserRepositoryImpl.findByEmail", "name": "findByEmail", "file": "A.java", "project": "p", "parent_class": "UserRepositoryImpl"},
                {"label": "Java_Method", "namespace_key": "p:B.java:AuthService.auth", "name": "auth", "file": "B.java", "project": "p", "parent_class": "AuthService"},
            ],
            "relationships": [
                {
                    "from": "p:B.java:AuthService.auth",
                    "to": "p:B.java:findByEmail",
                    "type": "CALLS",
                    "target_method_hint": "findByEmail",
                    "target_owner_hint": "UserRepository",
                }
            ],
        }
        ig_main._resolve_internal_calls(entities, max_hops=3)
        resolved = [r for r in entities["relationships"] if r.get("type") == "CALLS_RESOLVED"]
        self.assertEqual(len(resolved), 1)
        self.assertEqual(resolved[0]["to"], "p:A.java:UserRepositoryImpl.findByEmail")

    def test_java_inheritance_resolution(self) -> None:
        entities = {
            "nodes": [
                {"label": "Java_Class", "namespace_key": "p:A.java:BaseService", "name": "BaseService", "file": "A.java", "project": "p"},
                {"label": "Java_Class", "namespace_key": "p:B.java:ChildService", "name": "ChildService", "file": "B.java", "project": "p", "extends_class": "BaseService"},
                {"label": "Java_Method", "namespace_key": "p:B.java:ChildService.execute", "name": "execute", "file": "B.java", "project": "p", "parent_class": "ChildService"},
                {"label": "Java_Method", "namespace_key": "p:C.java:Caller.run", "name": "run", "file": "C.java", "project": "p", "parent_class": "Caller"},
            ],
            "relationships": [
                {
                    "from": "p:C.java:Caller.run",
                    "to": "p:C.java:execute",
                    "type": "CALLS",
                    "target_method_hint": "execute",
                    "target_owner_hint": "BaseService",
                }
            ],
        }
        ig_main._resolve_internal_calls(entities, max_hops=3)
        resolved = [r for r in entities["relationships"] if r.get("type") == "CALLS_RESOLVED"]
        self.assertEqual(len(resolved), 1)
        self.assertEqual(resolved[0]["to"], "p:B.java:ChildService.execute")

    def test_ck_lcom_field_sharing(self) -> None:
        entities = {
            "nodes": [
                {"label": "Java_Class", "namespace_key": "p:File.java:OrderService", "name": "OrderService", "file": "File.java", "project": "p"},
                {"label": "Java_Method", "namespace_key": "p:File.java:OrderService.m1", "name": "m1", "file": "File.java", "project": "p", "field_refs": ["repo"]},
                {"label": "Java_Method", "namespace_key": "p:File.java:OrderService.m2", "name": "m2", "file": "File.java", "project": "p", "field_refs": ["repo"]},
                {"label": "Java_Method", "namespace_key": "p:File.java:OrderService.m3", "name": "m3", "file": "File.java", "project": "p", "field_refs": ["cache"]},
            ],
            "relationships": [
                {"from": "p:File.java:OrderService", "to": "p:File.java:OrderService.m1", "type": "HAS_METHOD"},
                {"from": "p:File.java:OrderService", "to": "p:File.java:OrderService.m2", "type": "HAS_METHOD"},
                {"from": "p:File.java:OrderService", "to": "p:File.java:OrderService.m3", "type": "HAS_METHOD"},
            ],
        }
        ig_main._apply_ck_metrics(entities)
        cls = entities["nodes"][0]
        self.assertEqual(cls["wmc"], 3)
        self.assertGreaterEqual(cls["lcom"], 0.3)
        self.assertLessEqual(cls["lcom"], 0.34)

    def test_call_resolution_summary(self) -> None:
        ig_main.memory_nodes = [
            {"namespace_key": "p:a:Caller.run", "name": "run", "project": "p", "file": "a"},
            {"namespace_key": "p:a:Svc.ok", "name": "ok", "project": "p", "file": "a"},
            {"namespace_key": "p:a:Svc.fail", "name": "fail", "project": "p", "file": "a"},
        ]
        ig_main.memory_edges = [
            {"source": "p:a:Caller.run", "target": "p:a:Svc.ok", "type": "CALLS", "target_method_hint": "ok"},
            {"source": "p:a:Caller.run", "target": "p:a:Svc.fail", "type": "CALLS", "target_method_hint": "fail"},
            {"source": "p:a:Caller.run", "target": "p:a:Svc.ok", "type": "CALLS_RESOLVED", "confidence_score": 90},
        ]
        summary = ig_main._compute_call_resolution_summary(project="p", top_n=5)
        self.assertEqual(summary["total_calls"], 2)
        self.assertEqual(summary["resolved_calls"], 1)
        self.assertEqual(summary["unresolved_calls"], 1)
        self.assertGreaterEqual(summary["resolution_rate"], 49.0)
        self.assertLessEqual(summary["resolution_rate"], 51.0)

    def test_rag_persistence_cycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ig_main.RAG_INDEX_FILE = Path(tmp) / "rag_index_test.json"
            ig_main.memory_nodes = [{"namespace_key": "p:a:X", "name": "X", "labels": ["TS_Function"]}]
            ig_main.memory_edges = []
            ig_main.rag_index = [{"key": "p:a:X", "blob": "x blob", "embedding": [0.1, 0.2]}]

            ig_main._save_rag_index()
            ig_main.rag_index = []
            loaded = ig_main._load_rag_index()
            self.assertEqual(loaded, 1)
            self.assertEqual(len(ig_main.rag_index), 1)
            self.assertFalse(ig_main._is_rag_index_stale())


def run_regression_suite(verbosity: int = 1) -> dict:
    """Run regression suite and return summarized result."""
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(CoreRegressionTests)
    result = unittest.TextTestRunner(verbosity=verbosity).run(suite)
    return {
        "ran": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "skipped": len(result.skipped),
        "successful": result.wasSuccessful(),
    }


if __name__ == "__main__":
    outcome = run_regression_suite(verbosity=2)
    if not outcome["successful"]:
        raise SystemExit(1)
