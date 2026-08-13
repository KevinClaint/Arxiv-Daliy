import json
import os
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from fetch_daily import (
    batched,
    build_daily_queries,
    canonical_id,
    collect_new_papers,
    build_parser,
    load_existing_ids,
    parse_categories,
)


class FetchDailyTests(unittest.TestCase):
    def test_normalizes_versions_and_parses_optional_categories(self):
        self.assertEqual(canonical_id("2401.00001v3"), "2401.00001")
        self.assertEqual(parse_categories(""), [])
        self.assertEqual(parse_categories("cs.CV, stat.ML"), ["cs.CV", "stat.ML"])

    def test_defaults_daily_fetch_to_all_computer_science_categories(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(build_parser().parse_args([]).categories, "cs")

    def test_batches_keywords_into_short_independent_queries(self):
        queries = build_daily_queries(
            [f"topic {index}" for index in range(17)],
            datetime(2026, 1, 1).date(),
            datetime(2026, 1, 8).date(),
            [],
            batch_size=8,
        )

        self.assertEqual(len(queries), 3)
        self.assertIn('all:"topic" AND all:"16"', queries[-1])
        self.assertTrue(all("submittedDate:" in query for query in queries))

    def test_rejects_an_invalid_batch_size(self):
        with self.assertRaisesRegex(ValueError, "positive"):
            batched(["topic"], 0)

    def test_loads_ids_from_all_saved_jsonl_files(self):
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory)
            (data_dir / "one.jsonl").write_text(
                json.dumps({"id": "2401.00001v2"}) + "\n", encoding="utf-8"
            )
            (data_dir / "two.jsonl").write_text(
                json.dumps({"id": "2401.00002"}) + "\n", encoding="utf-8"
            )

            self.assertEqual(
                load_existing_ids(data_dir), {"2401.00001", "2401.00002"}
            )

    def test_collects_only_new_papers_and_keeps_existing_data_contract(self):
        papers = [self._paper("2401.00001v3"), self._paper("2401.00002v1")]

        records = collect_new_papers(papers, {"2401.00001"}, limit=10)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["id"], "2401.00002v1")
        self.assertEqual(records[0]["categories"], ["cs.CV"])
        self.assertIn("summary", records[0])

    @staticmethod
    def _paper(paper_id):
        return SimpleNamespace(
            get_short_id=lambda: paper_id,
            authors=[SimpleNamespace(name="Author")],
            title="A paper",
            categories=["cs.CV"],
            comment=None,
            summary="An abstract",
            published=datetime(2026, 1, 1, tzinfo=timezone.utc),
            updated=datetime(2026, 1, 2, tzinfo=timezone.utc),
        )


if __name__ == "__main__":
    unittest.main()
