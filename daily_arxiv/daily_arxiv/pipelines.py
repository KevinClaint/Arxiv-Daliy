# Define your item pipelines here
#
# Don't forget to add your pipeline to the ITEM_PIPELINES setting
# See: https://docs.scrapy.org/en/latest/topics/item-pipeline.html


# useful for handling different item types with a single interface
import arxiv
import os
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
    searchable_text = " ".join(f"{title} {summary}".casefold().split())
    return any(" ".join(keyword.split()) in searchable_text for keyword in keywords)


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
