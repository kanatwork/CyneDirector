"""
Smoke-check for SearchEngine query parsing, temporal return shapes,
boolean operators, and field-specific filters.

Run:  python3 -m tests.smoke_search   (from the project root)
"""
import os
import sys
import types
import unittest

# Add project root to path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Optional runtime stubs so this smoke-check can run without heavy ML deps.
def _install_import_stubs():
    try:
        import torch  # noqa: F401
    except Exception:
        torch_stub = types.ModuleType("torch")

        class _NoGrad:
            def __enter__(self):
                return None

            def __exit__(self, exc_type, exc, tb):
                return False

        torch_stub.no_grad = lambda: _NoGrad()
        sys.modules["torch"] = torch_stub

    try:
        import numpy  # noqa: F401
    except Exception:
        np_stub = types.ModuleType("numpy")

        class _LinAlg:
            @staticmethod
            def norm(_value):
                return 1.0

        np_stub.mean = lambda values, axis=0: values[0] if values else 0
        np_stub.linalg = _LinAlg()
        sys.modules["numpy"] = np_stub

    if "core.database" not in sys.modules:
        db_stub = types.ModuleType("core.database")

        class _Database:
            def __init__(self, *args, **kwargs):
                self.project_path = kwargs.get("project_path")

            def initialize(self, *args, **kwargs):
                pass

        db_stub.Database = _Database
        sys.modules["core.database"] = db_stub

    if "core.ai_models" not in sys.modules:
        ai_stub = types.ModuleType("core.ai_models")

        class _AIBackend:
            def __init__(self):
                self.clip_model = None
                self.clip_processor = None
                self.device = "cpu"

            def load_clip(self):
                pass

        ai_stub.AIBackend = _AIBackend
        sys.modules["core.ai_models"] = ai_stub

    if "core.face_db" not in sys.modules:
        face_stub = types.ModuleType("core.face_db")

        class _FaceDB:
            def __init__(self, *args, **kwargs):
                self.id_to_name = {}

            def get_name(self, _pid):
                return "Unknown"

        face_stub.FaceDB = _FaceDB
        sys.modules["core.face_db"] = face_stub


_install_import_stubs()


# ---------------------------------------------------------------------------
# Fake collaborators
# ---------------------------------------------------------------------------
class FakeCollection:
    def query(self, **kw):
        return {"ids": [[]], "metadatas": [[]], "distances": [[]]}
    def count(self):
        return 0
    def get(self, **kw):
        return {"ids": [], "metadatas": []}


class FakeDB:
    project_path = "."
    visuals = FakeCollection()
    transcripts = FakeCollection()
    temporal_sequences = FakeCollection()
    def get_video_metadata(self, path):
        return {}
    def initialize(self, *a, **kw):
        pass


class FakeAI:
    clip_model = None
    clip_processor = None
    device = "cpu"
    _instance = None
    def load_clip(self):
        pass


class FakeFaceDB:
    id_to_name = {}
    def get_name(self, pid):
        return "Unknown"


def _make_engine():
    """Build a SearchEngine without touching any real model or DB."""
    from core.search_engine import SearchEngine
    eng = SearchEngine.__new__(SearchEngine)
    eng.project_path = None
    eng.db = FakeDB()
    eng.ai = FakeAI()
    eng.face_db = None
    eng.cache = {}
    eng.query_embedding_cache = {}
    eng.result_cache = {}
    eng.result_cache_max_size = 50
    eng.result_cache_ttl = 300
    eng.result_cache_timestamps = {}
    return eng


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class TestParseQueryOperators(unittest.TestCase):
    def setUp(self):
        self.engine = _make_engine()

    def test_and_not(self):
        p = self.engine._parse_query_operators("person AND running NOT walking")
        self.assertIn("AND", p["operators"])
        self.assertIn("NOT", p["operators"])
        self.assertIn("person", p["terms"])
        self.assertIn("running", p["terms"])

    def test_score_gt(self):
        p = self.engine._parse_query_operators("score:>80 car OR truck")
        self.assertEqual(p["score_range"], (80.0, 100.0))
        self.assertIn("OR", p["operators"])

    def test_score_lt(self):
        p = self.engine._parse_query_operators("score:<50 dark")
        self.assertEqual(p["score_range"], (0.0, 50.0))

    def test_phrase(self):
        p = self.engine._parse_query_operators('"golden hour" sunset')
        self.assertIn("golden hour", p["phrases"])

    def test_duration_range(self):
        p = self.engine._parse_query_operators("duration:30-60 walking")
        self.assertEqual(p["duration_range"], (30.0, 60.0))

    def test_field_queries(self):
        p = self.engine._parse_query_operators("visual:match dialogue:hello")
        self.assertIn("visual", p["fields"])
        self.assertIn("dialogue", p["fields"])

    def test_quoted_field_value(self):
        p = self.engine._parse_query_operators('dialogue:"hello world"')
        self.assertEqual(p["fields"].get("dialogue"), "hello world")
        self.assertNotIn("dialogue:", p["terms"])

    def test_score_with_quoted_field(self):
        p = self.engine._parse_query_operators('score:>80 dialogue:"hello world"')
        self.assertEqual(p["score_range"], (80.0, 100.0))
        self.assertEqual(p["fields"].get("dialogue"), "hello world")

    def test_duration_with_quoted_field(self):
        p = self.engine._parse_query_operators('duration:30-60 visual:"golden hour"')
        self.assertEqual(p["duration_range"], (30.0, 60.0))
        self.assertEqual(p["fields"].get("visual"), "golden hour")


class TestTemporalReturnShape(unittest.TestCase):
    def setUp(self):
        self.engine = _make_engine()

    def test_none_vector_returns_dict(self):
        result = self.engine._search_temporal_sequence(None, "walk", "run")
        self.assertIsInstance(result, dict)

    def test_empty_db_returns_dict(self):
        result = self.engine._search_temporal_sequence([0.0] * 768, "walk", "run")
        self.assertIsInstance(result, dict)

    def test_items_iterable(self):
        result = self.engine._search_temporal_sequence([0.0] * 768, "walk", "run")
        # This is how the caller uses the return value
        for match_type, results_list in result.items():
            self.assertIsInstance(results_list, list)

    def test_temporal_results_integrate_with_search_shape(self):
        self.engine._get_query_embedding = lambda _q: [0.0] * 4
        self.engine._collect_results_by_type = lambda *args, **kwargs: {}
        self.engine._search_temporal_sequence = lambda *args, **kwargs: {
            "TEMPORAL SEQUENCE": [{
                "path": "a.mp4",
                "match_type": "TEMPORAL SEQUENCE",
                "context": "Sequence: walk then run",
                "score": 90,
                "timestamp": 10
            }]
        }

        result = self.engine.search("walk then run", use_expansion=False, use_cache=False)
        self.assertIsInstance(result, dict)
        self.assertIn("results", result)
        self.assertGreaterEqual(result["total"], 1)
        self.assertEqual(result["results"][0]["match_type"], "TEMPORAL SEQUENCE")


class TestApplyQueryFilters(unittest.TestCase):
    def setUp(self):
        self.engine = _make_engine()
        self.sample = [
            {"path": "a.mp4", "match_type": "VISUAL (AI)", "score": 90, "context": "sunset scene"},
            {"path": "b.mp4", "match_type": "DIALOGUE", "score": 40, "context": 'Says: "hello world"'},
            {"path": "c.mp4", "match_type": "TAG", "score": 60, "context": "Tagged: nature"},
        ]

    def test_score_range(self):
        pq = {"score_range": (50.0, 100.0), "fields": {}, "phrases": []}
        filtered = self.engine._apply_query_filters(self.sample, pq)
        self.assertEqual(len(filtered), 2)
        self.assertTrue(all(r["score"] >= 50 for r in filtered))

    def test_field_visual(self):
        pq = {"score_range": None, "fields": {"visual": "match"}, "phrases": []}
        filtered = self.engine._apply_query_filters(self.sample, pq)
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["match_type"], "VISUAL (AI)")

    def test_field_dialogue(self):
        pq = {"score_range": None, "fields": {"dialogue": "hello"}, "phrases": []}
        filtered = self.engine._apply_query_filters(self.sample, pq)
        self.assertEqual(len(filtered), 1)
        self.assertIn("DIALOGUE", filtered[0]["match_type"])

    def test_phrase_filter(self):
        pq = {"score_range": None, "fields": {}, "phrases": ["hello world"]}
        filtered = self.engine._apply_query_filters(self.sample, pq)
        self.assertEqual(len(filtered), 1)


class TestSearchPaginatedShape(unittest.TestCase):
    def setUp(self):
        self.engine = _make_engine()

    def test_empty_search(self):
        result = self.engine.search("nonexistent query", use_expansion=False, use_cache=False)
        self.assertIsInstance(result, dict)
        self.assertIn("results", result)
        self.assertIn("total", result)
        self.assertIn("page", result)
        self.assertIn("total_pages", result)
        self.assertIsInstance(result["results"], list)


class TestExpandQuery(unittest.TestCase):
    def setUp(self):
        self.engine = _make_engine()

    def test_includes_original(self):
        expanded = self.engine._expand_query("person running in park")
        self.assertIn("person running in park", expanded)

    def test_produces_variations(self):
        expanded = self.engine._expand_query("person running in park")
        self.assertGreater(len(expanded), 1)

    def test_capped_at_5(self):
        expanded = self.engine._expand_query("person running in park")
        self.assertLessEqual(len(expanded), 5)


class TestDecomposeQuery(unittest.TestCase):
    def setUp(self):
        self.engine = _make_engine()

    def test_splits_on_in(self):
        parts = self.engine._decompose_query("person running in park")
        self.assertGreater(len(parts), 1)

    def test_simple_noop(self):
        parts = self.engine._decompose_query("cat")
        self.assertEqual(parts, ["cat"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
