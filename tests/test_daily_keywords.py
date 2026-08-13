import tempfile
import unittest
from pathlib import Path

from daily_arxiv.daily_arxiv.pipelines import load_keywords, matches_keywords


class DailyKeywordTests(unittest.TestCase):
    def test_loads_casefolded_keywords(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "keywords.txt"
            path.write_text("# comment\n\nVideo World Model\n3D Scene\n", encoding="utf-8")

            self.assertEqual(load_keywords(path), ["video world model", "3d scene"])

    def test_matches_title_or_abstract_case_insensitively(self):
        keywords = ["video world model", "spatial reasoning"]

        self.assertTrue(matches_keywords("A VIDEO World Model", "", keywords))
        self.assertTrue(
            matches_keywords("Unrelated title", "A new spatial\nreasoning method", keywords)
        )
        self.assertFalse(matches_keywords("Language Models", "Text generation", keywords))

    def test_empty_keyword_list_keeps_all_papers(self):
        self.assertTrue(matches_keywords("Any paper", "Any abstract", []))

    def test_matches_hyphens_but_not_inflections_or_field_boundaries(self):
        self.assertTrue(matches_keywords("A world-model", "", ["world model"]))
        self.assertTrue(matches_keywords("Learning world models", "", ["world model"]))
        self.assertFalse(matches_keywords("World modeling", "", ["world model"]))
        self.assertFalse(matches_keywords("The world", "Models for control", ["world model"]))


if __name__ == "__main__":
    unittest.main()
