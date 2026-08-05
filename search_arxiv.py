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


# ======================== 用户配置区 ========================
# 日期格式为 "YYYY-MM-DD"；设为 None 表示不限制该方向的日期。
SEARCH_KEYWORDS = [
    "large language model",
    "vision language model",
]
# 多个关键词之间的关系："OR"（匹配任意一个）或 "AND"（必须全部匹配）。
KEYWORD_OPERATOR = "OR"
START_DATE: str | None = None
END_DATE: str | None = None

# arXiv 搜索领域（分类）设置：
# - ["cs"]：全部计算机科学领域。
# - ["cs.AI", "cs.CL", "cs.CV", "cs.LG"]：仅限人工智能、计算语言学、
#   计算机视觉和机器学习。
# - 其他常用代码：cs.RO（机器人）、cs.IR（信息检索）、cs.CR（安全）、
#   cs.HC（人机交互）、stat.ML（统计机器学习）、eess.IV（图像与视频处理）。
# - []：不限制搜索领域。
SEARCH_CATEGORIES = ["cs.AI", "cs.CL", "cs.CV", "cs.LG"]

# 检索字段："all"、"title"、"abstract" 或 "author"。
SEARCH_FIELD = "all"
# 多词匹配："phrase"（完整短语）、"all"（全部词）或 "any"（任意词）。
MATCH_MODE = "phrase"

# 最多导出的论文篇数；设为 None 表示导出全部匹配结果。
MAX_RESULTS: int | None = 100
OUTPUT_FILE = "arxiv_results.ris"
# "ris" 可导入 EndNote；也可设为 "csv"、"jsonl" 或 None（根据扩展名推断）。
OUTPUT_FORMAT: str | None = "ris"

# arXiv 请求设置。
PAGE_SIZE = 100
REQUEST_DELAY_SECONDS = 3.0
REQUEST_RETRIES = 3
PROGRESS_EVERY = 100  # 每处理多少篇显示一次进度；0 表示关闭。
# ============================================================


FIELD_PREFIXES = {
    "all": "all",
    "title": "ti",
    "abstract": "abs",
    "author": "au",
}

CS_CATEGORIES = (
    "cs.AI",
    "cs.AR",
    "cs.CC",
    "cs.CE",
    "cs.CG",
    "cs.CL",
    "cs.CR",
    "cs.CV",
    "cs.CY",
    "cs.DB",
    "cs.DC",
    "cs.DL",
    "cs.DM",
    "cs.DS",
    "cs.ET",
    "cs.FL",
    "cs.GL",
    "cs.GR",
    "cs.GT",
    "cs.HC",
    "cs.IR",
    "cs.IT",
    "cs.LG",
    "cs.LO",
    "cs.MA",
    "cs.MM",
    "cs.MS",
    "cs.NA",
    "cs.NE",
    "cs.NI",
    "cs.OH",
    "cs.OS",
    "cs.PF",
    "cs.PL",
    "cs.RO",
    "cs.SC",
    "cs.SD",
    "cs.SE",
    "cs.SI",
    "cs.SY",
)

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


def _category_query(categories: Iterable[str] | None) -> str | None:
    if not categories:
        return None

    expanded: list[str] = []
    for category in categories:
        category = category.strip()
        if category.lower() == "cs":
            expanded.extend(CS_CATEGORIES)
        elif re.fullmatch(r"[a-z][a-z0-9-]*\.[A-Za-z0-9-]+", category):
            expanded.append(category)
        else:
            raise ValueError(f"invalid arXiv category: {category!r}")

    unique_categories = list(dict.fromkeys(expanded))
    query = " OR ".join(f"cat:{category}" for category in unique_categories)
    return f"({query})" if len(unique_categories) > 1 else query


def build_query(
    keywords: str | Iterable[str],
    field: str = "all",
    match: str = "phrase",
    start_date: date | None = None,
    end_date: date | None = None,
    keyword_operator: str = "OR",
    categories: Iterable[str] | None = None,
) -> str:
    """Build an arXiv API query with an inclusive submission-date range."""
    raw_keywords = [keywords] if isinstance(keywords, str) else list(keywords)
    cleaned_keywords = [" ".join(keyword.split()) for keyword in raw_keywords]
    if not cleaned_keywords or any(not keyword for keyword in cleaned_keywords):
        raise ValueError("keywords must not be empty")
    if field not in FIELD_PREFIXES:
        raise ValueError(f"unsupported search field: {field}")
    if match not in {"phrase", "all", "any"}:
        raise ValueError(f"unsupported match mode: {match}")
    keyword_operator = keyword_operator.upper()
    if keyword_operator not in {"OR", "AND"}:
        raise ValueError(f"unsupported keyword operator: {keyword_operator}")
    if start_date and end_date and start_date > end_date:
        raise ValueError("start date must not be after end date")

    prefix = FIELD_PREFIXES[field]
    keyword_queries = []
    for keyword in cleaned_keywords:
        if match == "phrase":
            keyword_queries.append(f"{prefix}:{_quoted(keyword)}")
            continue

        terms = [f"{prefix}:{_quoted(term)}" for term in keyword.split()]
        term_operator = " AND " if match == "all" else " OR "
        keyword_queries.append(
            f"({term_operator.join(terms)})" if len(terms) > 1 else terms[0]
        )

    keyword_query = f" {keyword_operator} ".join(keyword_queries)
    if len(keyword_queries) > 1:
        keyword_query = f"({keyword_query})"

    category_query = _category_query(categories)
    if category_query:
        keyword_query = f"{keyword_query} AND {category_query}"

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


def _write_ris_record(record: dict[str, Any], output: TextIO) -> None:
    """Write one paper as an EndNote-compatible RIS record."""
    published = datetime.fromisoformat(record["published"])
    fields: list[tuple[str, str | None]] = [
        ("TY", "JOUR"),
        ("TI", record["title"]),
    ]
    fields.extend(("AU", author) for author in record["authors"])
    fields.extend(
        [
            ("PY", str(published.year)),
            ("DA", published.strftime("%Y/%m/%d")),
            ("AB", record["summary"]),
            ("T2", record["journal_ref"] or "arXiv"),
            ("M3", "Preprint"),
            ("AN", f'arXiv:{record["id"]}'),
        ]
    )
    fields.extend(("KW", category) for category in record["categories"])
    fields.extend(
        [
            ("DO", record["doi"]),
            ("UR", record["abstract_url"]),
            ("L1", record["pdf_url"]),
            ("N1", record["comment"]),
        ]
    )

    for tag, value in fields:
        if value:
            output.write(f"{tag}  - {value}\r\n")
    output.write("ER  - \r\n\r\n")


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
        if output_format == "ris":
            _write_ris_record(record, output)
        elif csv_writer:
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
    if output_path != "-":
        suffix = Path(output_path).suffix.lower()
        if suffix == ".ris":
            return "ris"
        if suffix == ".csv":
            return "csv"
    return "jsonl"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="按首次提交时间从旧到新检索 arXiv 论文，并导出完整元数据。"
    )
    parser.add_argument(
        "keywords",
        nargs="*",
        default=SEARCH_KEYWORDS,
        help="要检索的一个或多个关键词；包含空格的短语需要放在引号内",
    )
    parser.add_argument(
        "--keyword-operator",
        type=str.upper,
        choices=("OR", "AND"),
        default=KEYWORD_OPERATOR,
        help=f"多个关键词的组合方式（文件顶部配置：{KEYWORD_OPERATOR}）",
    )
    parser.add_argument(
        "--categories",
        nargs="+",
        default=SEARCH_CATEGORIES,
        help="arXiv 分类范围，例如 cs、cs.AI、cs.CV；默认读取文件顶部配置",
    )
    parser.add_argument(
        "--start-date",
        type=parse_date,
        default=START_DATE,
        help="起始日期（含），格式 YYYY-MM-DD；默认读取文件顶部配置",
    )
    parser.add_argument(
        "--end-date",
        type=parse_date,
        default=END_DATE,
        help="结束日期（含），格式 YYYY-MM-DD；默认读取文件顶部配置",
    )
    parser.add_argument(
        "--field",
        choices=FIELD_PREFIXES,
        default=SEARCH_FIELD,
        help=f"检索字段（文件顶部配置：{SEARCH_FIELD}）",
    )
    parser.add_argument(
        "--match",
        choices=("phrase", "all", "any"),
        default=MATCH_MODE,
        help=f"多词匹配方式：完整短语、全部词、任意词（文件顶部配置：{MATCH_MODE}）",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=OUTPUT_FILE,
        help=f"输出文件（文件顶部配置：{OUTPUT_FILE}）；- 表示标准输出",
    )
    parser.add_argument(
        "--format",
        choices=("ris", "jsonl", "csv"),
        default=OUTPUT_FORMAT,
        help="输出格式；默认根据扩展名推断，RIS 可直接导入 EndNote",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=MAX_RESULTS,
        help=f"最多导出多少篇（文件顶部配置：{MAX_RESULTS}；None 表示全部）",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=PAGE_SIZE,
        help=f"每页数量（文件顶部配置：{PAGE_SIZE}）",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=REQUEST_DELAY_SECONDS,
        help=f"分页请求间隔秒数（文件顶部配置：{REQUEST_DELAY_SECONDS}）",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=REQUEST_RETRIES,
        help=f"请求失败重试次数（文件顶部配置：{REQUEST_RETRIES}）",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=PROGRESS_EVERY,
        help=f"每写入多少篇报告一次进度（文件顶部配置：{PROGRESS_EVERY}；0 表示关闭）",
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
            args.keywords,
            field=args.field,
            match=args.match,
            start_date=args.start_date,
            end_date=args.end_date,
            keyword_operator=args.keyword_operator,
            categories=args.categories,
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
