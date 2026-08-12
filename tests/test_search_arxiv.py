import csv
import io
import json
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from search_arxiv import (
    END_DATE,
    MATCH_MODE,
    MAX_RESULTS,
    OUTPUT_FILE,
    OUTPUT_FORMAT,
    PAGE_SIZE,
    PROGRESS_EVERY,
    REQUEST_DELAY_SECONDS,
    REQUEST_RETRIES,
    RESUME_DOWNLOAD,
    KEYWORD_OPERATOR,
    SEARCH_KEYWORDS,
    SEARCH_CATEGORIES,
    SEARCH_FIELD,
    START_DATE,
    build_parser,
    build_query,
    infer_format,
    load_keywords,
    load_checkpoint,
    paper_to_record,
    read_exported_ids,
    resume_offset_from_checkpoint,
    save_checkpoint,
    write_results,
    _canonical_arxiv_id,
)


class SearchArxivTests(unittest.TestCase):
    def test_loads_keywords_while_ignoring_comments_and_blank_lines(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "keywords.txt"
            path.write_text(
                "# Topics\n\n video world model \nspatial reasoning\n",
                encoding="utf-8",
            )

            self.assertEqual(
                load_keywords(path), ["video world model", "spatial reasoning"]
            )

    def test_uses_file_configuration_when_arguments_are_omitted(self):
        parser = build_parser()
        args = parser.parse_args([])

        self.assertEqual(args.keywords, SEARCH_KEYWORDS)
        self.assertEqual(args.keyword_operator, KEYWORD_OPERATOR)
        self.assertEqual(args.categories, SEARCH_CATEGORIES)
        self.assertEqual(args.start_date, START_DATE)
        self.assertEqual(args.end_date, END_DATE)
        self.assertEqual(args.field, SEARCH_FIELD)
        self.assertEqual(args.match, MATCH_MODE)
        self.assertEqual(args.limit, MAX_RESULTS)
        self.assertEqual(args.output, OUTPUT_FILE)
        self.assertEqual(args.format, OUTPUT_FORMAT)
        self.assertEqual(args.page_size, PAGE_SIZE)
        self.assertEqual(args.delay, REQUEST_DELAY_SECONDS)
        self.assertEqual(args.retries, REQUEST_RETRIES)
        self.assertEqual(args.progress_every, PROGRESS_EVERY)
        self.assertEqual(args.resume, RESUME_DOWNLOAD)

    def test_command_line_arguments_override_file_configuration(self):
        parser = build_parser()

        self.assertEqual(
            parser.parse_args(["robotics", "machine learning"]).keywords,
            ["robotics", "machine learning"],
        )
        self.assertEqual(parser.parse_args(["--limit", "25"]).limit, 25)

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

    def test_combines_multiple_keywords(self):
        self.assertEqual(
            build_query(["large language model", "vision transformer"]),
            '(all:"large language model" OR all:"vision transformer")',
        )
        self.assertEqual(
            build_query(["robotics", "reinforcement learning"], keyword_operator="AND"),
            '(all:"robotics" AND all:"reinforcement learning")',
        )

    def test_limits_query_to_arxiv_categories(self):
        self.assertEqual(
            build_query("transformer", categories=["cs.AI", "cs.CV"]),
            'all:"transformer" AND (cat:cs.AI OR cat:cs.CV)',
        )

    def test_expands_cs_category_scope(self):
        query = build_query("transformer", categories=["cs"])

        self.assertIn("cat:cs.AI", query)
        self.assertIn("cat:cs.CV", query)
        self.assertIn("cat:cs.LG", query)
        self.assertIn("cat:cs.SY", query)

    def test_rejects_invalid_arxiv_category(self):
        with self.assertRaisesRegex(ValueError, "invalid arXiv category"):
            build_query("transformer", categories=["computer science"])

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

    @patch("search_arxiv.tqdm")
    def test_progress_tracks_real_count_without_a_fake_total(self, mock_tqdm):
        progress = mock_tqdm.return_value.__enter__.return_value

        count = write_results([self._paper()], io.StringIO(), "jsonl", 1)

        self.assertEqual(count, 1)
        self.assertNotIn("total", mock_tqdm.call_args.kwargs)
        progress.update.assert_called_once_with(1)
        progress.set_postfix_str.assert_called_once_with(
            "当前论文 2024-01-01", refresh=False
        )

    def test_writes_endnote_compatible_ris(self):
        output = io.StringIO(newline="")

        self.assertEqual(write_results([self._paper()], output, "ris", 0), 1)

        ris = output.getvalue()
        self.assertIn("TY  - JOUR\r\n", ris)
        self.assertIn("TI  - A useful paper\r\n", ris)
        self.assertIn("AU  - Alice Zhang\r\nAU  - Bob Li\r\n", ris)
        self.assertIn("DA  - 2024/01/01\r\n", ris)
        self.assertIn("AN  - arXiv:2401.00001v1\r\n", ris)
        self.assertIn("KW  - cs.AI\r\nKW  - cs.LG\r\n", ris)
        self.assertIn("UR  - https://arxiv.org/abs/2401.00001v1\r\n", ris)
        self.assertIn("L1  - https://arxiv.org/pdf/2401.00001v1\r\n", ris)
        self.assertTrue(ris.endswith("ER  - \r\n\r\n"))

    def test_reads_existing_ris_for_legacy_resume(self):
        output = io.StringIO(newline="")
        write_results([self._paper()], output, "ris", 0)

        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "papers.ris"
            output_path.write_text(output.getvalue(), encoding="utf-8", newline="")

            self.assertEqual(read_exported_ids(output_path, "ris"), ["2401.00001v1"])

    def test_rejects_incomplete_ris_resume_file(self):
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "papers.ris"
            output_path.write_text("TY  - JOUR\nAN  - arXiv:2401.00001v1\n")

            with self.assertRaisesRegex(ValueError, "不完整记录"):
                read_exported_ids(output_path, "ris")

    def test_resume_skips_an_existing_paper_version(self):
        output = io.StringIO()
        checkpoints = []

        new_count = write_results(
            [self._paper()],
            output,
            "jsonl",
            0,
            initial_count=1,
            initial_offset=1,
            existing_ids={_canonical_arxiv_id("2401.00001v2")},
            checkpoint_callback=lambda *values: checkpoints.append(values),
        )

        self.assertEqual(new_count, 0)
        self.assertEqual(output.getvalue(), "")
        self.assertEqual(checkpoints, [(2, 1, None)])

    def test_saves_checkpoint_atomically(self):
        checkpoint = {"version": 1, "next_offset": 400}
        with tempfile.TemporaryDirectory() as directory:
            checkpoint_path = Path(directory) / "papers.checkpoint.json"

            save_checkpoint(checkpoint_path, checkpoint)

            self.assertEqual(load_checkpoint(checkpoint_path), checkpoint)
            self.assertFalse(Path(f"{checkpoint_path}.tmp").exists())

    def test_rejects_checkpoint_from_a_different_query(self):
        checkpoint = {
            "signature": "old-query",
            "next_offset": 400,
            "written_count": 400,
        }

        with self.assertRaisesRegex(ValueError, "查询条件"):
            resume_offset_from_checkpoint(checkpoint, "new-query", 400)

    def test_reconciles_record_written_just_before_a_crash(self):
        checkpoint = {
            "signature": "same-query",
            "next_offset": 399,
            "written_count": 399,
        }

        self.assertEqual(
            resume_offset_from_checkpoint(checkpoint, "same-query", 400), 400
        )

    def test_infers_output_format(self):
        self.assertEqual(infer_format("papers.ris", None), "ris")
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
