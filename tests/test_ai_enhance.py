import unittest
from unittest.mock import Mock

from ai.enhance import process_single_item


class AiEnhanceTests(unittest.TestCase):
    def test_chinese_failure_fallback_remains_chinese(self):
        chain = Mock()
        chain.invoke.side_effect = RuntimeError("model unavailable")
        paper = {
            "id": "1",
            "title": "An English title",
            "summary": "A harmless abstract.",
            "abs": "https://arxiv.org/abs/1234.56789",
        }

        result = process_single_item(chain, paper, "Chinese")

        self.assertIn("标题翻译失败", result["AI"]["title_zh"])
        self.assertIn("摘要翻译失败", result["AI"]["abstract_zh"])

    def test_translation_receives_title_abstract_and_arxiv_url(self):
        chain = Mock()
        chain.invoke.return_value.model_dump.return_value = {
            "title_zh": "中文标题",
            "abstract_zh": "中文摘要",
        }
        paper = {
            "id": "1",
            "title": "English title",
            "summary": "English abstract",
            "abs": "https://arxiv.org/abs/1234.56789",
        }

        result = process_single_item(chain, paper, "Chinese")

        chain.invoke.assert_called_once_with({
            "language": "Chinese",
            "title": "English title",
            "abstract": "English abstract",
            "url": "https://arxiv.org/abs/1234.56789",
        })
        self.assertEqual(result["AI"]["title_zh"], "中文标题")
        self.assertEqual(result["AI"]["abstract_zh"], "中文摘要")


if __name__ == "__main__":
    unittest.main()
