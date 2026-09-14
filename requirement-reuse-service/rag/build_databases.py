#!/usr/bin/env python3
"""Validate role RAG manifests and build one isolated SQLite FTS store per role."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import yaml


RAG_ROOT = Path(__file__).resolve().parent
SERVICE_ROOT = RAG_ROOT.parent
AGENT_ROOT = RAG_ROOT / "agents"
CATALOG_PATH = RAG_ROOT / "source_catalog.yaml"
ROLE_CONFIG_PATH = SERVICE_ROOT / "config" / "agent_roles.yaml"
TEXT_SUFFIXES = {".md", ".txt", ".ttl", ".json", ".jsonld", ".yaml", ".yml", ".csv"}
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)


class RagConfigurationError(ValueError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RagConfigurationError(f"Unable to read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RagConfigurationError(f"Expected a YAML mapping in {path}")
    return value


def load_configuration() -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]], list[str]]:
    catalog_data = load_yaml(CATALOG_PATH)
    sources = catalog_data.get("sources") or []
    if not isinstance(sources, list):
        raise RagConfigurationError("source_catalog.yaml sources must be a list")
    source_map: dict[str, dict[str, Any]] = {}
    for source in sources:
        if not isinstance(source, dict) or not source.get("id"):
            raise RagConfigurationError("Every source catalogue entry must be a mapping with an id")
        if source["id"] in source_map:
            raise RagConfigurationError(f"Duplicate source id: {source['id']}")
        for required in ("title", "url", "publisher", "year", "source_type", "summary"):
            if required not in source:
                raise RagConfigurationError(f"Source {source['id']} is missing {required}")
        source_map[source["id"]] = source

    role_config = load_yaml(ROLE_CONFIG_PATH)
    full_15 = ((role_config.get("presets") or {}).get("full_15") or {}).get("role_ids") or []
    role_by_id = {
        role["id"]: role
        for role in role_config.get("roles") or []
        if isinstance(role, dict) and role.get("id")
    }

    manifests: list[dict[str, Any]] = []
    for manifest_path in sorted(AGENT_ROOT.glob("*/manifest.yaml")):
        manifest = load_yaml(manifest_path)
        manifest["_path"] = manifest_path
        manifests.append(manifest)

    errors: list[str] = []
    manifest_ids = [item.get("role_id") for item in manifests]
    if len(manifest_ids) != len(set(manifest_ids)):
        errors.append("RAG manifest role ids must be unique")
    if set(manifest_ids) != set(full_15):
        errors.append(
            "RAG manifests must match full_15 exactly; "
            f"missing={sorted(set(full_15) - set(manifest_ids))}, "
            f"extra={sorted(set(manifest_ids) - set(full_15))}"
        )

    for manifest in manifests:
        role_id = manifest.get("role_id")
        manifest_path = manifest["_path"]
        role = role_by_id.get(role_id)
        if role is None:
            errors.append(f"{manifest_path}: unknown role_id {role_id!r}")
            continue
        if manifest_path.parent.name != role_id:
            errors.append(f"{manifest_path}: directory must match role_id {role_id}")
        if manifest.get("phase") != role.get("phase"):
            errors.append(f"{manifest_path}: phase does not match agent_roles.yaml")
        selected_sources = manifest.get("source_ids") or []
        if len(selected_sources) < 6:
            errors.append(f"{manifest_path}: at least six curated sources are required")
        unknown = sorted(set(selected_sources) - set(source_map))
        if unknown:
            errors.append(f"{manifest_path}: unknown source ids: {', '.join(unknown)}")
        if len(selected_sources) != len(set(selected_sources)):
            errors.append(f"{manifest_path}: source ids must be unique")
        queries = manifest.get("retrieval_queries") or []
        if len(queries) < 4:
            errors.append(f"{manifest_path}: at least four retrieval queries are required")
        for relative in manifest.get("knowledge_files") or []:
            if not (manifest_path.parent / relative).is_file():
                errors.append(f"{manifest_path}: missing knowledge file {relative}")

    if errors:
        raise RagConfigurationError("\n".join(errors))
    return source_map, manifests, full_15


def split_markdown(text: str) -> Iterable[tuple[str, str]]:
    matches = list(HEADING_RE.finditer(text))
    if not matches:
        for paragraph in re.split(r"\n\s*\n+", text):
            paragraph = paragraph.strip()
            if paragraph:
                yield "Document", paragraph
        return
    preface = text[: matches[0].start()].strip()
    if preface:
        yield "Preface", preface
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        heading = match.group(2).strip()
        body = text[match.end() : end].strip()
        if body:
            for paragraph in re.split(r"\n\s*\n+", body):
                paragraph = paragraph.strip()
                if paragraph:
                    yield heading, paragraph


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def source_chunk(source: dict[str, Any]) -> str:
    topics = ", ".join(source.get("topics") or [])
    return (
        f"Title: {source['title']}\nPublisher: {source['publisher']}\nYear: {source['year']}\n"
        f"Type: {source['source_type']}\nURL: {source['url']}\nTopics: {topics}\n"
        f"Curator summary: {source['summary']}\n"
        f"Ingestion policy: {source.get('ingest_policy', 'link_and_synthesis_only')}\n"
        f"Licence note: {source.get('license_note', 'Check source terms before storing full text.')}"
    )


def initialise_database(
    manifest: dict[str, Any],
    source_map: dict[str, dict[str, Any]],
    include_raw: bool,
) -> tuple[int, int]:
    role_dir: Path = manifest["_path"].parent
    database_path = role_dir / manifest.get("database", "db/rag.sqlite3")
    database_path.parent.mkdir(parents=True, exist_ok=True)
    database_path.unlink(missing_ok=True)
    connection = sqlite3.connect(database_path)
    connection.executescript(
        """
        PRAGMA journal_mode=WAL;
        CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE sources (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            url TEXT NOT NULL,
            publisher TEXT NOT NULL,
            year TEXT NOT NULL,
            source_type TEXT NOT NULL,
            authority TEXT NOT NULL,
            ingest_policy TEXT NOT NULL,
            license_note TEXT NOT NULL
        );
        CREATE TABLE chunks (
            id TEXT PRIMARY KEY,
            source_id TEXT NOT NULL,
            ordinal INTEGER NOT NULL,
            heading TEXT NOT NULL,
            content TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            evidence_eligible INTEGER NOT NULL CHECK (evidence_eligible IN (0, 1))
        );
        CREATE VIRTUAL TABLE chunks_fts USING fts5(
            chunk_id UNINDEXED,
            source_id UNINDEXED,
            heading,
            content,
            tokenize='unicode61'
        );
        """
    )
    metadata = {
        "schema_version": "role-rag-sqlite-v1",
        "role_id": manifest["role_id"],
        "label": manifest["label"],
        "phase": manifest["phase"],
        "built_at": datetime.now(timezone.utc).isoformat(),
        "evidence_policy": "supplemental_only",
    }
    connection.executemany("INSERT INTO metadata(key, value) VALUES (?, ?)", metadata.items())

    selected_sources = [source_map[source_id] for source_id in manifest["source_ids"]]
    for source in selected_sources:
        connection.execute(
            "INSERT INTO sources VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                source["id"], source["title"], source["url"], source["publisher"],
                str(source["year"]), source["source_type"], source.get("authority", "reviewed"),
                source.get("ingest_policy", "link_and_synthesis_only"),
                source.get("license_note", "Check source terms before storing full text."),
            ),
        )

    chunks: list[tuple[str, str, int, str, str, str, int]] = []
    ordinal = 0
    for source in selected_sources:
        ordinal += 1
        content = source_chunk(source)
        chunks.append((
            sha256_text(f"{manifest['role_id']}|catalog|{source['id']}")[:24],
            source["id"], ordinal, "Curated source record", content, sha256_text(content), 0,
        ))

    for relative in manifest.get("knowledge_files") or []:
        path = role_dir / relative
        for heading, content in split_markdown(path.read_text(encoding="utf-8")):
            ordinal += 1
            source_id = f"local:{relative}"
            chunks.append((
                sha256_text(f"{manifest['role_id']}|{relative}|{ordinal}|{content}")[:24],
                source_id, ordinal, heading, content, sha256_text(content), 0,
            ))

    if include_raw:
        raw_dir = role_dir / manifest.get("raw_directory", "raw")
        for path in sorted(item for item in raw_dir.rglob("*") if item.is_file() and item.suffix in TEXT_SUFFIXES):
            if path.name == ".gitkeep":
                continue
            relative = path.relative_to(role_dir).as_posix()
            for heading, content in split_markdown(path.read_text(encoding="utf-8")):
                ordinal += 1
                source_id = f"raw:{relative}"
                chunks.append((
                    sha256_text(f"{manifest['role_id']}|{relative}|{ordinal}|{content}")[:24],
                    source_id, ordinal, heading, content, sha256_text(content), 0,
                ))

    connection.executemany("INSERT INTO chunks VALUES (?, ?, ?, ?, ?, ?, ?)", chunks)
    connection.executemany(
        "INSERT INTO chunks_fts(chunk_id, source_id, heading, content) VALUES (?, ?, ?, ?)",
        ((chunk[0], chunk[1], chunk[3], chunk[4]) for chunk in chunks),
    )
    connection.commit()
    connection.close()
    return len(selected_sources), len(chunks)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role", help="Build only this role id")
    parser.add_argument("--validate-only", action="store_true", help="Validate without creating databases")
    parser.add_argument("--include-raw", action="store_true", help="Also index licensed text files under raw/")
    parser.add_argument("--json", action="store_true", help="Print a machine-readable report")
    args = parser.parse_args()

    source_map, manifests, full_15 = load_configuration()
    if args.role:
        manifests = [item for item in manifests if item["role_id"] == args.role]
        if not manifests:
            raise RagConfigurationError(f"Unknown full_15 role: {args.role}")

    report: dict[str, Any] = {
        "status": "valid" if args.validate_only else "built",
        "catalog_sources": len(source_map),
        "full_15_roles": len(full_15),
        "roles": {},
    }
    if not args.validate_only:
        for manifest in manifests:
            source_count, chunk_count = initialise_database(manifest, source_map, args.include_raw)
            report["roles"][manifest["role_id"]] = {
                "sources": source_count,
                "chunks": chunk_count,
                "database": str(manifest["_path"].parent / manifest.get("database", "db/rag.sqlite3")),
            }

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"RAG configuration {report['status']}: {len(manifests)} role(s), {len(source_map)} sources")
        for role_id, details in report["roles"].items():
            print(f"- {role_id}: {details['sources']} sources, {details['chunks']} chunks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
