# Define your item pipelines here
#
# Don't forget to add your pipeline to the ITEM_PIPELINES setting
# See: https://docs.scrapy.org/en/latest/topics/item-pipeline.html


# useful for handling different item types with a single interface
import arxiv
import os
import re
from pathlib import Path

from scrapy.exceptions import DropItem


def load_keywords(path: Path) -> list[str]:
    """Load the repository's shared keyword list."""
    if not path.exists():
        return []
    return [
        line.casefold()
        for raw_line in path.read_text(encoding="utf-8").splitlines()
        if (line := raw_line.strip()) and not line.startswith("#")
    ]


def matches_keywords(title: str, summary: str, keywords: list[str]) -> bool:
    """Return whether any configured phrase occurs in the title or abstract."""
    if not keywords:
        return True

    def normalize(value: str) -> str:
        return " ".join(re.sub(r"[^\w]+", " ", value.casefold()).split())

    normalized_title = f" {normalize(title)} "
    normalized_summary = f" {normalize(summary)} "
    for keyword in keywords:
        normalized_keyword = normalize(keyword)
        variants = [normalized_keyword]
        words = normalized_keyword.split()
        if words and words[-1] in {"model", "scene", "simulator"}:
            variants.append(" ".join([*words[:-1], f"{words[-1]}s"]))
        if any(
            f" {variant} " in normalized_title or f" {variant} " in normalized_summary
            for variant in variants
        ):
            return True
    return False


class DailyArxivPipeline:
    def __init__(self):
        self.page_size = 100
        self.client = arxiv.Client(self.page_size)
        default_keywords_file = Path(__file__).resolve().parents[2] / "keywords.txt"
        keywords_file = Path(os.environ.get("KEYWORDS_FILE", default_keywords_file))
        self.keywords = load_keywords(keywords_file)

    def process_item(self, item: dict, spider):
        item["pdf"] = f"https://arxiv.org/pdf/{item['id']}"
        item["abs"] = f"https://arxiv.org/abs/{item['id']}"
        search = arxiv.Search(
            id_list=[item["id"]],
        )
        paper = next(self.client.results(search))
        item["authors"] = [a.name for a in paper.authors]
        item["title"] = paper.title
        item["categories"] = paper.categories
        item["comment"] = paper.comment
        item["summary"] = paper.summary
        if not matches_keywords(paper.title, paper.summary, self.keywords):
            raise DropItem(f"Paper {item['id']} does not match configured keywords")
        return item
