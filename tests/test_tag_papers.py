import json
import tempfile
import unittest
from pathlib import Path

from tag_papers import (
    assign_tags,
    load_catalog,
    migrate_tags,
    update_jsonl,
    update_paper_tags,
    validate_catalog,
)


class TagPaperTests(unittest.TestCase):
    def test_default_catalog_has_30_unique_representative_tags(self):
        catalog = load_catalog()

        self.assertEqual(len(catalog["tags"]), 30)
        self.assertEqual(len({tag["id"] for tag in catalog["tags"]}), 30)
        self.assertEqual(len({tag["label"] for tag in catalog["tags"]}), 30)

    def test_assigns_tags_from_saved_metadata_and_chinese_summary_fields(self):
        catalog = load_catalog()
        paper = {
            "title": "A Physics-Aware Video World Model",
            "summary": "We study spatial reasoning for robot learning.",
            "AI": {"tldr": "一个面向具身智能的世界模拟器"},
            "pdf": "must-not-be-opened.pdf",
        }

        tags = assign_tags(paper, catalog)

        self.assertIn("world-models", tags)
        self.assertIn("physical-ai", tags)
        self.assertIn("spatial-reasoning", tags)
        self.assertIn("robotics", tags)

    def test_migrates_one_old_tag_to_two_new_tags(self):
        catalog = self._migration_catalog()

        self.assertEqual(
            migrate_tags(["old-video"], 1, catalog),
            ["video-generation", "world-models"],
        )

    def test_migrates_across_multiple_versions_with_an_intermediate_id(self):
        catalog = self._migration_catalog(version=3)

        self.assertEqual(
            migrate_tags(["legacy-video"], 1, catalog),
            ["video-generation", "world-models"],
        )

    def test_rejects_data_newer_than_catalog(self):
        with self.assertRaisesRegex(ValueError, "newer than catalog"):
            migrate_tags(["video-generation"], 2, load_catalog())

    def test_initial_backfill_and_migration_are_idempotent(self):
        catalog = load_catalog()
        paper = {"title": "Video diffusion model", "summary": ""}

        self.assertTrue(update_paper_tags(paper, catalog))
        self.assertFalse(update_paper_tags(paper, catalog))
        self.assertEqual(paper["tag_schema_version"], 1)
        self.assertIn("video-diffusion", paper["tags"])

    def test_updates_jsonl_without_accessing_a_pdf(self):
        catalog = load_catalog()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "papers.jsonl"
            paper = {
                "id": "1234.56789",
                "title": "Spatial Reasoning Benchmark",
                "summary": "",
                "pdf": str(Path(directory) / "does-not-exist.pdf"),
            }
            path.write_text(json.dumps(paper) + "\n", encoding="utf-8")

            self.assertEqual(update_jsonl(path, catalog), (1, 1))
            self.assertEqual(update_jsonl(path, catalog), (1, 0))
            updated = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(
                updated["tags"], ["spatial-reasoning", "benchmarks"]
            )

    @staticmethod
    def _migration_catalog(version=2):
        base_tags = [
            {"id": f"tag-{index}", "label": f"标签{index}", "terms": [f"term {index}"]}
            for index in range(28)
        ]
        tags = [
            {"id": "video-generation", "label": "视频生成", "terms": ["video generation"]},
            {"id": "world-models", "label": "世界模型", "terms": ["world model"]},
            *base_tags,
        ]
        if version == 2:
            catalog = {
                "schema_version": 2,
                "tags": tags,
                "migrations": [
                    {
                        "from_version": 1,
                        "to_version": 2,
                        "replace": {
                            "old-video": ["video-generation", "world-models"]
                        },
                    }
                ],
            }
        else:
            catalog = {
                "schema_version": 3,
                "tags": tags,
                "migrations": [
                    {
                        "from_version": 1,
                        "to_version": 2,
                        "replace": {"legacy-video": ["old-video"]},
                    },
                    {
                        "from_version": 2,
                        "to_version": 3,
                        "replace": {
                            "old-video": ["video-generation", "world-models"]
                        },
                    },
                ],
            }
        validate_catalog(catalog)
        return catalog


if __name__ == "__main__":
    unittest.main()
