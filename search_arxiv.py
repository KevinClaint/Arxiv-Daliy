#!/usr/bin/env python3
"""Search arXiv by keyword and export papers from oldest to newest."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from contextlib import nullcontext
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Iterable, TextIO

from tqdm import tqdm


def load_keywords(path: Path) -> list[str]:
    """Load non-empty, non-comment keyword lines from a text file."""
    return [
        line
        for raw_line in path.read_text(encoding="utf-8").splitlines()
        if (line := raw_line.strip()) and not line.startswith("#")
    ]


# ======================== 用户配置区 ========================
# 每日抓取与历史检索共用 keywords.txt；每行填写一个关键词或短语。
KEYWORDS_FILE = Path(__file__).with_name("keywords.txt")
SEARCH_KEYWORDS = load_keywords(KEYWORDS_FILE)
# 日期格式为 "YYYY-MM-DD"；设为 None 表示不限制该方向的日期。
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
MAX_RESULTS: int | None = 10000
OUTPUT_FILE = "arxiv_results.ris"
# "ris" 可导入 EndNote；也可设为 "csv"、"jsonl" 或 None（根据扩展名推断）。
OUTPUT_FORMAT: str | None = "ris"

# arXiv 请求设置。
PAGE_SIZE = 200
REQUEST_DELAY_SECONDS = 5.0
REQUEST_RETRIES = 2
PROGRESS_EVERY = 1  # 每处理多少篇更新一次当前论文日期；0 表示关闭进度显示。
RESUME_DOWNLOAD = True  # 中断后从输出文件和检查点继续，不清空已有结果。
# ============================================================


FIELD_PREFIXES = {
    "all": "all",
    "title": "ti",
    "abstract": "abs",
    "author": "au",
    "title_abstract": None,
}

# arXiv 计算机科学领域的全部 cs.* 子分类。
# 当 SEARCH_CATEGORIES 或 --categories 中包含 "cs" 时，程序会将其展开为
# 下列具体分类以构造查询；普通使用者通常不需要修改这个内部列表。
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

CHECKPOINT_VERSION = 1


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

    def field_query(value: str) -> str:
        if field == "title_abstract":
            return f'(ti:{_quoted(value)} OR abs:{_quoted(value)})'
        return f"{prefix}:{_quoted(value)}"

    keyword_queries = []
    for keyword in cleaned_keywords:
        if match == "phrase":
            keyword_queries.append(field_query(keyword))
            continue

        terms = [field_query(term) for term in keyword.split()]
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

    lines = [f"{tag}  - {value}\r\n" for tag, value in fields if value]
    output.write("".join(lines) + "ER  - \r\n\r\n")


def _canonical_arxiv_id(arxiv_id: str) -> str:
    return re.sub(r"v\d+$", "", arxiv_id.strip())


def read_exported_ids(output_path: Path, output_format: str) -> list[str]:
    """Read complete records from an existing export for safe resumption."""
    if not output_path.exists() or output_path.stat().st_size == 0:
        return []

    if output_format == "ris":
        text = output_path.read_text(encoding="utf-8")
        record_pattern = re.compile(r"(?ms)^TY  - .*?^ER  -[ \t]*\n")
        records = list(record_pattern.finditer(text))
        remainder_start = records[-1].end() if records else 0
        if text[remainder_start:].strip():
            raise ValueError("RIS 输出末尾存在不完整记录，无法安全续传")

        ids = []
        for record in records:
            id_match = re.search(
                r"(?m)^AN  - arXiv:(.+?)[ \t]*$", record.group(0)
            )
            if not id_match:
                raise ValueError("RIS 输出中存在缺少 arXiv ID 的记录")
            ids.append(id_match.group(1).strip())
        return ids

    if output_format == "jsonl":
        ids = []
        with output_path.open("r", encoding="utf-8") as output:
            for line_number, line in enumerate(output, start=1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                    ids.append(str(record["id"]))
                except (json.JSONDecodeError, KeyError) as exc:
                    raise ValueError(
                        f"JSONL 第 {line_number} 行不完整，无法安全续传"
                    ) from exc
        return ids

    if output_format == "csv":
        with output_path.open("r", encoding="utf-8", newline="") as output:
            reader = csv.DictReader(output)
            if reader.fieldnames and "id" not in reader.fieldnames:
                raise ValueError("CSV 输出缺少 id 列，无法安全续传")
            return [row["id"] for row in reader if row.get("id")]

    raise ValueError(f"不支持从 {output_format!r} 格式续传")


def _checkpoint_path(output_path: Path) -> Path:
    return Path(f"{output_path}.checkpoint.json")


def _query_signature(query: str, output_format: str) -> str:
    value = json.dumps(
        {"query": query, "format": output_format},
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def load_checkpoint(checkpoint_path: Path) -> dict[str, Any] | None:
    if not checkpoint_path.exists():
        return None
    try:
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"检查点文件损坏：{checkpoint_path}") from exc
    if checkpoint.get("version") != CHECKPOINT_VERSION:
        raise ValueError("检查点版本不受支持")
    return checkpoint


def resume_offset_from_checkpoint(
    checkpoint: dict[str, Any], signature: str, exported_count: int
) -> int:
    """Validate a checkpoint and reconcile a record written before a crash."""
    if checkpoint.get("signature") != signature:
        raise ValueError(
            "查询条件与已有检查点不一致。请换一个输出文件，或确认后使用 "
            "--no-resume 覆盖旧结果"
        )
    checkpoint_written = int(checkpoint.get("written_count", 0))
    if checkpoint_written > exported_count:
        raise ValueError("输出文件少于检查点记录，无法确定安全恢复位置")
    return int(checkpoint.get("next_offset", 0)) + exported_count - checkpoint_written


def save_checkpoint(checkpoint_path: Path, checkpoint: dict[str, Any]) -> None:
    temporary_path = Path(f"{checkpoint_path}.tmp")
    temporary_path.write_text(
        json.dumps(checkpoint, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(checkpoint_path)


def write_results(
    papers: Iterable[Any],
    output: TextIO,
    output_format: str,
    progress_every: int = 1,
    *,
    initial_count: int = 0,
    initial_offset: int = 0,
    existing_ids: set[str] | None = None,
    checkpoint_callback: Callable[[int, int, str | None], None] | None = None,
) -> int:
    """Stream results and return the number of newly written papers."""
    csv_writer = None
    if output_format == "csv":
        csv_writer = csv.DictWriter(output, fieldnames=CSV_FIELDS)
        if initial_count == 0:
            csv_writer.writeheader()

    new_count = 0
    processed_offset = initial_offset
    seen_ids = existing_ids if existing_ids is not None else set()
    # arXiv 客户端不公开查询总数。这里不设置虚假的 total，而是展示真实的
    # 已写入篇数、耗时、速度和当前论文日期。
    with tqdm(
        desc="检索并写入",
        unit="篇",
        dynamic_ncols=True,
        mininterval=0.2,
        smoothing=0.1,
        disable=progress_every == 0,
        file=sys.stderr,
        initial=initial_count,
    ) as progress:
        for paper in papers:
            record = paper_to_record(paper)
            processed_offset += 1
            canonical_id = _canonical_arxiv_id(record["id"])
            if canonical_id in seen_ids:
                if checkpoint_callback:
                    checkpoint_callback(
                        processed_offset, initial_count + new_count, None
                    )
                continue

            if output_format == "ris":
                _write_ris_record(record, output)
            elif csv_writer:
                csv_writer.writerow(_csv_record(record))
            else:
                output.write(json.dumps(record, ensure_ascii=False) + "\n")
            output.flush()
            seen_ids.add(canonical_id)
            new_count += 1
            progress.update(1)
            total_count = initial_count + new_count
            if checkpoint_callback:
                checkpoint_callback(processed_offset, total_count, record["id"])
            if progress_every and total_count % progress_every == 0:
                paper_date = (record["published"] or "未知日期")[:10]
                progress.set_postfix_str(f"当前论文 {paper_date}", refresh=False)
    return new_count


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
        help=(
            "每写入多少篇更新一次当前论文日期；篇数和耗时会实时显示"
            f"（文件顶部配置：{PROGRESS_EVERY}；0 表示关闭）"
        ),
    )
    parser.add_argument(
        "--resume",
        action=argparse.BooleanOptionalAction,
        default=RESUME_DOWNLOAD,
        help=(
            "从已有输出和检查点续传（默认开启）；--no-resume 会覆盖已有输出"
        ),
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
    output_path: Path | None = None
    checkpoint_path: Path | None = None
    checkpoint: dict[str, Any] | None = None
    existing_ids: list[str] = []
    resume_offset = 0
    resume_enabled = args.resume and args.output != "-"
    signature = _query_signature(query, output_format)

    if args.output == "-" and args.resume:
        print("标准输出不支持断点续传，本次将从头检索。", file=sys.stderr)

    try:
        if args.output != "-":
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            checkpoint_path = _checkpoint_path(output_path)

            if resume_enabled:
                existing_ids = read_exported_ids(output_path, output_format)
                saved_checkpoint = load_checkpoint(checkpoint_path)
                if saved_checkpoint:
                    resume_offset = resume_offset_from_checkpoint(
                        saved_checkpoint, signature, len(existing_ids)
                    )
                    if saved_checkpoint.get("completed"):
                        print(
                            f"已有输出已完成：{len(existing_ids)} 篇，文件为 {args.output}",
                            file=sys.stderr,
                        )
                        return 0
                else:
                    resume_offset = len(existing_ids)

                output_mode = "a"
            else:
                output_mode = "w"

            checkpoint = {
                "version": CHECKPOINT_VERSION,
                "signature": signature,
                "query": query,
                "output_format": output_format,
                "next_offset": resume_offset,
                "written_count": len(existing_ids),
                "last_id": existing_ids[-1] if existing_ids else None,
                "completed": False,
            }
            save_checkpoint(checkpoint_path, checkpoint)
            if (
                resume_enabled
                and args.limit is not None
                and resume_offset >= args.limit
            ):
                print(
                    f"已有 {len(existing_ids)} 篇，已达到 --limit={args.limit}；"
                    "如需继续，请调大 MAX_RESULTS 或 --limit。",
                    file=sys.stderr,
                )
                return 0
            output_context = output_path.open(
                output_mode, encoding="utf-8", newline=""
            )
    except (OSError, ValueError) as exc:
        print(f"无法准备输出文件：{exc}", file=sys.stderr)
        return 1

    print(f"arXiv 查询：{query}", file=sys.stderr)
    if resume_enabled and resume_offset:
        print(
            f"检测到 {len(existing_ids)} 篇已有论文，将从偏移 {resume_offset} 继续。",
            file=sys.stderr,
        )
    print(
        "正在连接 arXiv；首次请求和后续翻页期间可能需要等待，请观察进度耗时。",
        file=sys.stderr,
    )

    latest_offset = resume_offset

    def update_checkpoint(
        next_offset: int, written_count: int, last_id: str | None
    ) -> None:
        nonlocal latest_offset
        latest_offset = next_offset
        if checkpoint is None or checkpoint_path is None:
            return
        checkpoint["next_offset"] = next_offset
        checkpoint["written_count"] = written_count
        if last_id:
            checkpoint["last_id"] = last_id
        save_checkpoint(checkpoint_path, checkpoint)

    try:
        with output_context as output:
            new_count = write_results(
                client.results(search, offset=resume_offset),
                output,
                output_format,
                args.progress_every,
                initial_count=len(existing_ids),
                initial_offset=resume_offset,
                existing_ids={_canonical_arxiv_id(item) for item in existing_ids},
                checkpoint_callback=update_checkpoint,
            )
    except KeyboardInterrupt:
        print(
            f"\n已中断，检查点保存在 {checkpoint_path}；下次运行会自动继续。",
            file=sys.stderr,
        )
        return 130
    except (OSError, arxiv.ArxivError) as exc:
        print(
            f"检索暂停：{exc}\n已保留现有结果和检查点，下次运行会自动继续。",
            file=sys.stderr,
        )
        return 1

    count = len(existing_ids) + new_count
    limit_reached = args.limit is not None and latest_offset >= args.limit
    if checkpoint is not None and checkpoint_path is not None:
        checkpoint["completed"] = not limit_reached
        checkpoint["completion_reason"] = (
            "limit_reached" if limit_reached else "query_exhausted"
        )
        save_checkpoint(checkpoint_path, checkpoint)

    destination = "标准输出" if args.output == "-" else args.output
    if limit_reached:
        print(
            f"已达到结果上限：共 {count} 篇，已写入 {destination}；"
            "调大 --limit 后可继续。",
            file=sys.stderr,
        )
    else:
        print(f"完成：共 {count} 篇，已写入 {destination}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
