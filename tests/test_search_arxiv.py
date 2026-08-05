import csv
import io
import json
import unittest
from datetime import date, datetime, timezone
from types import SimpleNamespace

from search_arxiv import build_query, infer_format, paper_to_record, write_results


class SearchArxivTests(unittest.TestCase):
    def test_builds_inclusive_date_query(self):
        query = build_query(
            "large language model",
            start_date=date(2020, 1, 2),
            end_date=date(2021, 3, 4),
        )

        self.assertEqual(
            query,
            'all:"large language model" AND '
            "submittedDate:[202001020000 TO 202103042359]",
        )

    def test_builds_all_words_title_query(self):
        self.assertEqual(
            build_query("vision transformer", field="title", match="all"),
            '(ti:"vision" AND ti:"transformer")',
        )

    def test_rejects_reversed_date_range(self):
        with self.assertRaisesRegex(ValueError, "start date"):
            build_query(
                "robotics",
                start_date=date(2024, 2, 1),
                end_date=date(2024, 1, 1),
            )

    def test_serializes_paper_metadata(self):
        paper = self._paper()

        record = paper_to_record(paper)

        self.assertEqual(record["id"], "2401.00001v1")
        self.assertEqual(record["authors"], ["Alice Zhang", "Bob Li"])
        self.assertEqual(record["title"], "A useful paper")
        self.assertEqual(record["abstract_url"], "https://arxiv.org/abs/2401.00001v1")
        self.assertEqual(record["pdf_url"], "https://arxiv.org/pdf/2401.00001v1")
        self.assertEqual(record["primary_category"], "cs.AI")

    def test_writes_jsonl_and_csv(self):
        json_output = io.StringIO()
        csv_output = io.StringIO()

        self.assertEqual(write_results([self._paper()], json_output, "jsonl", 0), 1)
        self.assertEqual(write_results([self._paper()], csv_output, "csv", 0), 1)

        self.assertEqual(json.loads(json_output.getvalue())["title"], "A useful paper")
        csv_row = next(csv.DictReader(io.StringIO(csv_output.getvalue())))
        self.assertEqual(csv_row["authors"], "Alice Zhang; Bob Li")

    def test_infers_output_format(self):
        self.assertEqual(infer_format("papers.csv", None), "csv")
        self.assertEqual(infer_format("papers.jsonl", None), "jsonl")
        self.assertEqual(infer_format("papers.csv", "jsonl"), "jsonl")

    @staticmethod
    def _paper():
        return SimpleNamespace(
            get_short_id=lambda: "2401.00001v1",
            title="A useful\n paper",
            authors=[SimpleNamespace(name="Alice Zhang"), SimpleNamespace(name="Bob Li")],
            summary="First line.\nSecond line.",
            published=datetime(2024, 1, 1, tzinfo=timezone.utc),
            updated=datetime(2024, 1, 2, tzinfo=timezone.utc),
            entry_id="http://arxiv.org/abs/2401.00001v1",
            pdf_url="http://arxiv.org/pdf/2401.00001v1",
            primary_category="cs.AI",
            categories=["cs.AI", "cs.LG"],
            comment="10 pages",
            journal_ref=None,
            doi=None,
            links=[
                SimpleNamespace(
                    href="http://arxiv.org/abs/2401.00001v1",
                    title=None,
                    rel="alternate",
                    content_type=None,
                )
            ],
        )


if __name__ == "__main__":
    unittest.main()
