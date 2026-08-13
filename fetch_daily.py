#!/usr/bin/env python3
"""Fetch recent arXiv computer science papers using the shared keyword list."""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

from search_arxiv import build_query, load_keywords


ROOT = Path(__file__).resolve().parent
DEFAULT_KEYWORDS = ROOT / "keywords.txt"
DEFAULT_DATA_DIR = ROOT / "data"


def canonical_id(arxiv_id: str) -> str:
    return re.sub(r"v\d+$", "", arxiv_id.strip())


def load_existing_ids(data_dir: Path, excluded_path: Path | None = None) -> set[str]:
    ids: set[str] = set()
    for path in data_dir.glob("*.jsonl"):
        if excluded_path and path.resolve() == excluded_path.resolve():
            continue
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            if not raw_line.strip():
                continue
            try:
                paper = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            if paper.get("id"):
                ids.add(canonical_id(str(paper["id"])))
    return ids


def parse_categories(value: str | None) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()] if value else []


def paper_to_daily_record(paper: Any) -> dict[str, Any]:
    paper_id = paper.get_short_id()
    return {
        "id": paper_id,
        "pdf": f"https://arxiv.org/pdf/{paper_id}",
        "abs": f"https://arxiv.org/abs/{paper_id}",
        "authors": [author.name for author in paper.authors],
        "title": " ".join(paper.title.split()),
        "categories": list(paper.categories),
        "comment": paper.comment,
        "summary": " ".join(paper.summary.split()),
        "published": paper.published.isoformat() if paper.published else None,
        "updated": paper.updated.isoformat() if paper.updated else None,
    }


def collect_new_papers(
    papers: Iterable[Any], existing_ids: set[str], limit: int
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen = set(existing_ids)
    for paper in papers:
        paper_id = canonical_id(paper.get_short_id())
        if paper_id in seen:
            continue
        seen.add(paper_id)
        records.append(paper_to_daily_record(paper))
        if len(records) >= limit:
            break
    return records


def batched(values: Sequence[str], size: int) -> list[list[str]]:
    if size < 1:
        raise ValueError("batch size must be positive")
    return [list(values[index : index + size]) for index in range(0, len(values), size)]


def build_daily_queries(
    keywords: Sequence[str],
    start_date: date,
    end_date: date,
    categories: Sequence[str],
    batch_size: int,
) -> list[str]:
    return [
        build_query(
            keyword_batch,
            field="all",
            match="all",
            start_date=start_date,
            end_date=end_date,
            keyword_operator="OR",
            categories=categories,
        )
        for keyword_batch in batched(keywords, batch_size)
    ]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--keywords", type=Path, default=DEFAULT_KEYWORDS)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--run-date", type=date.fromisoformat)
    parser.add_argument("--lookback-days", type=int, default=7)
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--categories", default=os.environ.get("CATEGORIES") or "cs")
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--delay", type=float, default=3.0)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--keyword-batch-size", type=int, default=8)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.lookback_days < 1 or args.limit < 1 or args.keyword_batch_size < 1:
        raise SystemExit("lookback, limit, and keyword batch size must be positive")

    run_date = args.run_date or datetime.now(timezone.utc).date()
    output = args.output or args.data_dir / f"{run_date.isoformat()}.jsonl"
    args.data_dir.mkdir(parents=True, exist_ok=True)
    keywords = load_keywords(args.keywords)
    categories = parse_categories(args.categories)
    queries = build_daily_queries(
        keywords,
        run_date - timedelta(days=args.lookback_days),
        run_date,
        categories,
        args.keyword_batch_size,
    )

    import arxiv

    client = arxiv.Client(
        page_size=args.page_size,
        delay_seconds=args.delay,
        num_retries=args.retries,
    )
    existing_ids = load_existing_ids(args.data_dir, excluded_path=output)
    candidates: list[Any] = []
    for query in queries:
        search = arxiv.Search(
            query=query,
            max_results=args.limit,
            sort_by=arxiv.SortCriterion.SubmittedDate,
            sort_order=arxiv.SortOrder.Descending,
        )
        candidates.extend(client.results(search))
    candidates.sort(
        key=lambda paper: paper.published or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    records = collect_new_papers(candidates, existing_ids, args.limit)
    output.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "date": run_date.isoformat(),
                "query_batches": len(queries),
                "max_query_length": max(map(len, queries)),
                "categories": categories,
                "existing_ids": len(existing_ids),
                "new_papers": len(records),
                "output": str(output),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
