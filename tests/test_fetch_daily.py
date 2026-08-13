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
    find_matching_keywords,
    phrase_variants,
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
        self.assertIn('(ti:"topic 16" OR abs:"topic 16")', queries[-1])
        self.assertTrue(all("submittedDate:" in query for query in queries))

    def test_daily_queries_search_complete_phrases_in_title_or_abstract(self):
        query = build_daily_queries(
            ["world model", "spatial reasoning"],
            datetime(2026, 1, 1).date(),
            datetime(2026, 1, 8).date(),
            ["cs"],
            batch_size=8,
        )[0]

        self.assertIn('(ti:"world model" OR abs:"world model")', query)
        self.assertIn('(ti:"world models" OR abs:"world models")', query)
        self.assertNotIn('all:"world"', query)

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

        records = collect_new_papers(
            papers, {"2401.00001"}, limit=10, keywords=["world model"]
        )

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["id"], "2401.00002v1")
        self.assertEqual(records[0]["categories"], ["cs.CV"])
        self.assertEqual(records[0]["matched_keywords"], ["world model"])
        self.assertIn("summary", records[0])

    def test_post_filters_scattered_words_and_normalizes_hyphens(self):
        exact = self._paper(
            "2401.00003v1", title="Learning a world-model for control"
        )
        scattered = self._paper(
            "2401.00004v1",
            title="A video model",
            summary="Understanding the physical world",
        )

        self.assertEqual(find_matching_keywords(exact, ["world model"]), ["world model"])
        self.assertEqual(find_matching_keywords(scattered, ["video world model"]), [])
        self.assertEqual(
            [record["id"] for record in collect_new_papers(
                [exact, scattered], set(), 10, ["world model"]
            )],
            ["2401.00003v1"],
        )

    def test_post_filter_uses_word_boundaries_and_separate_fields(self):
        inflection = self._paper(
            "2401.00005v1", title="Real-world modeling for robotics"
        )
        split_fields = self._paper(
            "2401.00006v1", title="Understanding the world", summary="Models for control"
        )

        self.assertEqual(find_matching_keywords(inflection, ["world model"]), [])
        self.assertEqual(find_matching_keywords(split_fields, ["world model"]), [])

    def test_post_filter_accepts_a_regular_plural_but_not_an_inflection(self):
        plural = self._paper("2401.00007v1", title="Learning world models")
        inflection = self._paper("2401.00008v1", title="Learning world modeling")

        self.assertEqual(phrase_variants("world model"), ("world model", "world models"))
        self.assertEqual(find_matching_keywords(plural, ["world model"]), ["world model"])
        self.assertEqual(find_matching_keywords(inflection, ["world model"]), [])

    @staticmethod
    def _paper(paper_id, title="A world model paper", summary="An abstract"):
        return SimpleNamespace(
            get_short_id=lambda: paper_id,
            authors=[SimpleNamespace(name="Author")],
            title=title,
            categories=["cs.CV"],
            comment=None,
            summary=summary,
            published=datetime(2026, 1, 1, tzinfo=timezone.utc),
            updated=datetime(2026, 1, 2, tzinfo=timezone.utc),
        )


if __name__ == "__main__":
    unittest.main()
