#!/usr/bin/env python3
"""Search arXiv by keyword and export papers from oldest to newest."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from contextlib import nullcontext
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, TextIO


FIELD_PREFIXES = {
    "all": "all",
    "title": "ti",
    "abstract": "abs",
    "author": "au",
}

CSV_FIELDS = [
    "id",
    "title",
    "authors",
    "summary",
    "published",
    "updated",
    "abstract_url",
    "pdf_url",
    "primary_category",
    "categories",
    "comment",
    "journal_ref",
    "doi",
    "links",
]


def parse_date(value: str) -> date:
    """Parse an ISO calendar date for argparse."""
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"invalid date {value!r}; expected YYYY-MM-DD"
        ) from exc


def _quoted(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def build_query(
    keyword: str,
    field: str = "all",
    match: str = "phrase",
    start_date: date | None = None,
    end_date: date | None = None,
) -> str:
    """Build an arXiv API query with an inclusive submission-date range."""
    keyword = " ".join(keyword.split())
    if not keyword:
        raise ValueError("keyword must not be empty")
    if field not in FIELD_PREFIXES:
        raise ValueError(f"unsupported search field: {field}")
    if match not in {"phrase", "all", "any"}:
        raise ValueError(f"unsupported match mode: {match}")
    if start_date and end_date and start_date > end_date:
        raise ValueError("start date must not be after end date")

    prefix = FIELD_PREFIXES[field]
    if match == "phrase":
        keyword_query = f"{prefix}:{_quoted(keyword)}"
    else:
        terms = [f"{prefix}:{_quoted(term)}" for term in keyword.split()]
        operator = " AND " if match == "all" else " OR "
        keyword_query = f"({operator.join(terms)})" if len(terms) > 1 else terms[0]

    if not start_date and not end_date:
        return keyword_query

    lower = start_date.strftime("%Y%m%d0000") if start_date else "000101010000"
    upper = end_date.strftime("%Y%m%d2359") if end_date else "999912312359"
    return f"{keyword_query} AND submittedDate:[{lower} TO {upper}]"


def _isoformat(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def _clean_text(value: str | None) -> str | None:
    return re.sub(r"\s+", " ", value).strip() if value else None


def paper_to_record(paper: Any) -> dict[str, Any]:
    """Convert an arxiv.Result object into a JSON-serializable record."""
    links = [
        {
            "href": getattr(link, "href", None),
            "title": getattr(link, "title", None),
            "rel": getattr(link, "rel", None),
            "content_type": getattr(link, "content_type", None),
        }
        for link in getattr(paper, "links", [])
    ]
    links = [{key: value for key, value in link.items() if value} for link in links]

    return {
        "id": paper.get_short_id(),
        "title": _clean_text(paper.title),
        "authors": [author.name for author in paper.authors],
        "summary": _clean_text(paper.summary),
        "published": _isoformat(paper.published),
        "updated": _isoformat(paper.updated),
        "abstract_url": paper.entry_id.replace("http://", "https://", 1),
        "pdf_url": (
            paper.pdf_url.replace("http://", "https://", 1)
            if paper.pdf_url
            else None
        ),
        "primary_category": paper.primary_category,
        "categories": list(paper.categories),
        "comment": _clean_text(paper.comment),
        "journal_ref": _clean_text(paper.journal_ref),
        "doi": paper.doi,
        "links": links,
    }


def _csv_record(record: dict[str, Any]) -> dict[str, Any]:
    row = record.copy()
    row["authors"] = "; ".join(record["authors"])
    row["categories"] = "; ".join(record["categories"])
    row["links"] = json.dumps(record["links"], ensure_ascii=False)
    return row


def write_results(
    papers: Iterable[Any],
    output: TextIO,
    output_format: str,
    progress_every: int = 100,
) -> int:
    """Stream results to output and return the number of written papers."""
    csv_writer = None
    if output_format == "csv":
        csv_writer = csv.DictWriter(output, fieldnames=CSV_FIELDS)
        csv_writer.writeheader()

    count = 0
    for paper in papers:
        record = paper_to_record(paper)
        if csv_writer:
            csv_writer.writerow(_csv_record(record))
        else:
            output.write(json.dumps(record, ensure_ascii=False) + "\n")
        output.flush()
        count += 1
        if progress_every and count % progress_every == 0:
            print(f"已写入 {count} 篇论文...", file=sys.stderr)
    return count


def infer_format(output_path: str, explicit_format: str | None) -> str:
    if explicit_format:
        return explicit_format
    if output_path != "-" and Path(output_path).suffix.lower() == ".csv":
        return "csv"
    return "jsonl"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="按首次提交时间从旧到新检索 arXiv 论文，并导出完整元数据。"
    )
    parser.add_argument("keyword", help="要检索的关键词或短语")
    parser.add_argument(
        "--start-date", type=parse_date, help="起始日期（含），格式 YYYY-MM-DD"
    )
    parser.add_argument(
        "--end-date", type=parse_date, help="结束日期（含），格式 YYYY-MM-DD"
    )
    parser.add_argument(
        "--field",
        choices=FIELD_PREFIXES,
        default="all",
        help="检索字段（默认：all）",
    )
    parser.add_argument(
        "--match",
        choices=("phrase", "all", "any"),
        default="phrase",
        help="多词匹配方式：完整短语、全部词、任意词（默认：phrase）",
    )
    parser.add_argument(
        "-o", "--output", default="arxiv_results.jsonl", help="输出文件；- 表示标准输出"
    )
    parser.add_argument(
        "--format", choices=("jsonl", "csv"), help="输出格式；默认根据扩展名推断"
    )
    parser.add_argument(
        "--limit", type=int, help="最多返回多少篇；不设置时自动翻页直到检索完"
    )
    parser.add_argument("--page-size", type=int, default=100, help="每页数量（默认：100）")
    parser.add_argument(
        "--delay", type=float, default=3.0, help="分页请求间隔秒数（默认：3.0）"
    )
    parser.add_argument("--retries", type=int, default=3, help="请求失败重试次数（默认：3）")
    parser.add_argument(
        "--progress-every",
        type=int,
        default=100,
        help="每写入多少篇报告一次进度；0 表示关闭（默认：100）",
    )
    return parser


def validate_args(args: argparse.Namespace) -> None:
    if args.start_date and args.end_date and args.start_date > args.end_date:
        raise ValueError("--start-date 不能晚于 --end-date")
    if args.limit is not None and args.limit < 1:
        raise ValueError("--limit 必须大于 0")
    if not 1 <= args.page_size <= 2000:
        raise ValueError("--page-size 必须在 1 到 2000 之间")
    if args.delay < 0:
        raise ValueError("--delay 不能小于 0")
    if args.retries < 0:
        raise ValueError("--retries 不能小于 0")
    if args.progress_every < 0:
        raise ValueError("--progress-every 不能小于 0")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        validate_args(args)
        query = build_query(
            args.keyword, args.field, args.match, args.start_date, args.end_date
        )
    except ValueError as exc:
        parser.error(str(exc))

    if sys.version_info < (3, 12):
        print("本脚本需要 Python 3.12 或更高版本。建议使用 `uv run python`。", file=sys.stderr)
        return 2

    try:
        import arxiv
    except ImportError:
        print(
            "缺少 arxiv 依赖。请先运行 `uv sync --frozen`，或执行 "
            "`python -m pip install arxiv`。",
            file=sys.stderr,
        )
        return 2

    search_options: dict[str, Any] = {
        "query": query,
        "sort_by": arxiv.SortCriterion.SubmittedDate,
        "sort_order": arxiv.SortOrder.Ascending,
    }
    if args.limit is not None:
        search_options["max_results"] = args.limit

    search = arxiv.Search(**search_options)
    client = arxiv.Client(
        page_size=args.page_size,
        delay_seconds=args.delay,
        num_retries=args.retries,
    )
    output_format = infer_format(args.output, args.format)
    output_context = nullcontext(sys.stdout)
    try:
        if args.output != "-":
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_context = output_path.open("w", encoding="utf-8", newline="")
    except OSError as exc:
        print(f"无法创建输出文件：{exc}", file=sys.stderr)
        return 1

    print(f"arXiv 查询：{query}", file=sys.stderr)
    try:
        with output_context as output:
            count = write_results(
                client.results(search), output, output_format, args.progress_every
            )
    except (OSError, arxiv.ArxivError) as exc:
        print(f"检索失败：{exc}", file=sys.stderr)
        return 1

    destination = "标准输出" if args.output == "-" else args.output
    print(f"完成：共 {count} 篇，已写入 {destination}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
