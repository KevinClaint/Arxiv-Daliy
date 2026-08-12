#!/usr/bin/env python3
"""Assign versioned paper tags and migrate old tag IDs without reading PDFs."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Iterable


DEFAULT_CATALOG = Path(__file__).with_name("tag_catalog.json")
TAG_TEXT_FIELDS = ("title", "summary", "comment")
AI_TEXT_FIELDS = ("tldr", "motivation", "method", "result", "conclusion")


def load_catalog(path: Path = DEFAULT_CATALOG) -> dict[str, Any]:
    catalog = json.loads(path.read_text(encoding="utf-8"))
    validate_catalog(catalog)
    return catalog


def validate_catalog(catalog: dict[str, Any]) -> None:
    version = catalog.get("schema_version")
    tags = catalog.get("tags")
    migrations = catalog.get("migrations", [])
    if not isinstance(version, int) or version < 1:
        raise ValueError("schema_version must be a positive integer")
    if not isinstance(tags, list) or not 25 <= len(tags) <= 35:
        raise ValueError("tag catalog must contain roughly 30 tags (25-35)")

    ids = [tag.get("id") for tag in tags]
    labels = [tag.get("label") for tag in tags]
    if any(not isinstance(tag_id, str) or not tag_id for tag_id in ids):
        raise ValueError("every tag must have a non-empty id")
    if any(not isinstance(label, str) or not label for label in labels):
        raise ValueError("every tag must have a non-empty label")
    if len(ids) != len(set(ids)):
        raise ValueError("tag ids must be unique")
    if len(labels) != len(set(labels)):
        raise ValueError("tag labels must be unique")
    for tag in tags:
        terms = tag.get("terms")
        if not isinstance(terms, list) or not terms or any(
            not isinstance(term, str) or not term.strip() for term in terms
        ):
            raise ValueError(f"tag {tag['id']} must have non-empty terms")

    expected_from = 1
    for migration in migrations:
        from_version = migration.get("from_version")
        to_version = migration.get("to_version")
        replacements = migration.get("replace", {})
        if from_version != expected_from or to_version != from_version + 1:
            raise ValueError("tag migrations must form a continuous version chain")
        if not isinstance(replacements, dict):
            raise ValueError("migration replace must be an object")
        for old_id, new_ids in replacements.items():
            if not isinstance(old_id, str) or not isinstance(new_ids, list):
                raise ValueError("migration replacements must map an id to an id list")
            if not new_ids or any(not isinstance(new_id, str) for new_id in new_ids):
                raise ValueError(f"migration target for {old_id} must contain ids")
        expected_from = to_version
    if migrations and migrations[-1]["to_version"] != version:
        raise ValueError("migration chain must end at schema_version")
    if not migrations and version != 1:
        raise ValueError("schema versions above 1 require migrations")

    # Intermediate IDs may disappear later. Every declared replacement must
    # still resolve through the remaining chain to a current canonical ID.
    migration_by_version = {item["from_version"]: item for item in migrations}
    current_ids = set(ids)
    for migration in migrations:
        for old_id in migration["replace"]:
            resolved = [old_id]
            current_version = migration["from_version"]
            while current_version < version:
                step = migration_by_version[current_version]
                next_ids: list[str] = []
                for tag_id in resolved:
                    next_ids.extend(step["replace"].get(tag_id, [tag_id]))
                resolved = list(dict.fromkeys(next_ids))
                current_version = step["to_version"]
            if any(tag_id not in current_ids for tag_id in resolved):
                raise ValueError(f"migration for {old_id} does not reach current tags")


def paper_text(paper: dict[str, Any]) -> str:
    values = [paper.get(field, "") for field in TAG_TEXT_FIELDS]
    ai_data = paper.get("AI")
    if isinstance(ai_data, dict):
        values.extend(ai_data.get(field, "") for field in AI_TEXT_FIELDS)
    return " ".join(" ".join(str(value).casefold().split()) for value in values if value)


def assign_tags(paper: dict[str, Any], catalog: dict[str, Any]) -> list[str]:
    searchable = paper_text(paper)
    return [
        tag["id"]
        for tag in catalog["tags"]
        if any(" ".join(term.casefold().split()) in searchable for term in tag["terms"])
    ]


def migrate_tags(
    tags: Iterable[str], from_version: int, catalog: dict[str, Any]
) -> list[str]:
    current_tags = list(dict.fromkeys(tags))
    current_version = from_version
    if current_version > catalog["schema_version"]:
        raise ValueError(
            f"paper tag version {current_version} is newer than catalog version "
            f"{catalog['schema_version']}"
        )
    migrations = {item["from_version"]: item for item in catalog["migrations"]}
    while current_version < catalog["schema_version"]:
        migration = migrations.get(current_version)
        if migration is None:
            raise ValueError(f"missing tag migration from version {current_version}")
        replacements = migration["replace"]
        migrated: list[str] = []
        for tag_id in current_tags:
            migrated.extend(replacements.get(tag_id, [tag_id]))
        current_tags = list(dict.fromkeys(migrated))
        current_version = migration["to_version"]

    valid_ids = {tag["id"] for tag in catalog["tags"]}
    unknown = set(current_tags) - valid_ids
    if unknown:
        raise ValueError(f"unmapped old tag ids: {', '.join(sorted(unknown))}")
    return current_tags


def update_paper_tags(paper: dict[str, Any], catalog: dict[str, Any]) -> bool:
    old_tags = paper.get("tags")
    old_version = paper.get("tag_schema_version")
    if isinstance(old_tags, list) and isinstance(old_version, int):
        new_tags = migrate_tags(old_tags, old_version, catalog)
    else:
        # Initial backfill uses metadata and saved summaries only. No PDF or LLM call.
        new_tags = assign_tags(paper, catalog)

    changed = (
        old_tags != new_tags
        or old_version != catalog["schema_version"]
    )
    paper["tags"] = new_tags
    paper["tag_schema_version"] = catalog["schema_version"]
    return changed


def update_jsonl(path: Path, catalog: dict[str, Any]) -> tuple[int, int]:
    papers: list[dict[str, Any]] = []
    changed_papers = 0
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not raw_line.strip():
            continue
        try:
            paper = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
        changed_papers += int(update_paper_tags(paper, catalog))
        papers.append(paper)

    if changed_papers:
        content = "".join(
            json.dumps(paper, ensure_ascii=False) + "\n" for paper in papers
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as output:
                output.write(content)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary_name, path)
        finally:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)
    return len(papers), changed_papers


def iter_jsonl_files(paths: list[Path], data_dir: Path | None) -> list[Path]:
    files = list(paths)
    if data_dir:
        files.extend(data_dir.glob("*.jsonl"))
    return sorted(set(files))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*", type=Path, help="JSONL files to tag")
    parser.add_argument("--data-dir", type=Path, help="tag every JSONL file here")
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--github-output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    files = iter_jsonl_files(args.paths, args.data_dir)
    if not files:
        print(json.dumps({"files": 0, "papers": 0, "changed_papers": 0}))
        return 0

    catalog = load_catalog(args.catalog)
    paper_count = 0
    changed_papers = 0
    changed_files = 0
    for path in files:
        file_papers, file_changes = update_jsonl(path, catalog)
        paper_count += file_papers
        changed_papers += file_changes
        changed_files += int(file_changes > 0)

    report = {
        "files": len(files),
        "changed_files": changed_files,
        "papers": paper_count,
        "changed_papers": changed_papers,
        "schema_version": catalog["schema_version"],
    }
    print(json.dumps(report, ensure_ascii=False))
    if args.github_output:
        with args.github_output.open("a", encoding="utf-8") as output:
            output.write(f"tags_changed={'true' if changed_files else 'false'}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
