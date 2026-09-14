#!/usr/bin/env python3
"""Query one role-isolated RAG database and return supplemental context as JSON."""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from pathlib import Path


RAG_ROOT = Path(__file__).resolve().parent
ROLE_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")
TOKEN_RE = re.compile(r"[\w-]+", re.UNICODE)


def natural_language_fts_query(value: str) -> str:
    """Convert plain text to a safe broad FTS5 query."""
    tokens = list(dict.fromkeys(TOKEN_RE.findall(value.casefold())))
    if not tokens:
        raise ValueError("Query must contain at least one word or number")
    return " OR ".join(f'"{token}"' for token in tokens)


def query_role(role_id: str, query: str, limit: int) -> dict[str, object]:
    if not ROLE_ID_RE.fullmatch(role_id):
        raise ValueError(f"Invalid role id: {role_id!r}")
    database = RAG_ROOT / "agents" / role_id / "db" / "rag.sqlite3"
    if not database.is_file():
        raise FileNotFoundError(
            f"Database not built for {role_id}. Run: python rag/build_databases.py --role {role_id}"
        )

    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    metadata = dict(connection.execute("SELECT key, value FROM metadata"))
    rows = connection.execute(
        """
        SELECT c.id, c.source_id, c.heading, c.content, c.evidence_eligible,
               s.title AS source_title, s.url AS source_url,
               bm25(chunks_fts) AS score
          FROM chunks_fts
          JOIN chunks AS c ON c.id = chunks_fts.chunk_id
          LEFT JOIN sources AS s ON s.id = c.source_id
         WHERE chunks_fts MATCH ?
         ORDER BY score
         LIMIT ?
        """,
        (natural_language_fts_query(query), limit),
    ).fetchall()
    connection.close()

    return {
        "role_id": metadata["role_id"],
        "query": query,
        "evidence_policy": metadata["evidence_policy"],
        "hits": [
            {
                "chunk_id": row["id"],
                "source_id": row["source_id"],
                "source_title": row["source_title"],
                "source_url": row["source_url"],
                "heading": row["heading"],
                "content": row["content"],
                "score": row["score"],
                "evidence_eligible": bool(row["evidence_eligible"]),
            }
            for row in rows
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("role_id", help="Role id from config/agent_roles.yaml")
    parser.add_argument("query", help="Plain-language retrieval query")
    parser.add_argument("--limit", type=int, default=5, choices=range(1, 21))
    args = parser.parse_args()
    print(json.dumps(query_role(args.role_id, args.query, args.limit), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
