import unittest
from unittest.mock import Mock, patch

from ai.enhance import process_single_item


class AiEnhanceTests(unittest.TestCase):
    @patch("ai.enhance.requests.post")
    def test_chinese_failure_fallback_remains_chinese(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"sensitive": False}
        chain = Mock()
        chain.invoke.side_effect = RuntimeError("model unavailable")
        paper = {"id": "1", "summary": "A harmless abstract."}

        result = process_single_item(chain, paper, "Chinese")

        self.assertIn("中文总结生成失败", result["AI"]["tldr"])
        self.assertIn("研究动机", result["AI"]["motivation"])


if __name__ == "__main__":
    unittest.main()
