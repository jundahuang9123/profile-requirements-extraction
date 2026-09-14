# Role-isolated RAG corpus

This directory contains one reproducible retrieval store for each role in the
`full_15` requirement-extraction panel. The role ids intentionally match
`config/agent_roles.yaml`.

The stores are analytical background, not requirement evidence. A retrieved
RAG passage may help an agent interpret terminology, find a standard, or form a
question. It must not be cited as proof that the source corpus requires a
profile feature. Only the workflow's declared source-corpus evidence units are
eligible as requirement evidence.

## Layout

```text
rag/
├── source_catalog.yaml             # reviewed bibliography and source policy
├── research/                       # role-selection and search-method notes
├── build_databases.py              # validation and SQLite FTS index builder
├── query_database.py               # bounded retrieval from one role store
└── agents/
    └── <role_id>/
        ├── manifest.yaml           # expertise, queries, and selected sources
        ├── knowledge/role_knowledge.md
        ├── raw/.gitkeep            # optional licensed source snapshots
        └── db/.gitkeep             # generated rag.sqlite3 lives here
```

Each database is physically separate. It contains only that role's curated
knowledge notes, bibliography annotations, and any explicitly added local raw
text for that role. There is no cross-role table or global retrieval index.

## Build and validate

From `requirement-reuse-service`:

```bash
python rag/build_databases.py --validate-only
python rag/build_databases.py
```

Build one store:

```bash
python rag/build_databases.py --role ifc_bim
```

Retrieve supplemental context from exactly one store:

```bash
python rag/query_database.py ifc_bim "IFC schema version and model view" --limit 5
```

The query helper opens the selected database read-only and returns source links,
chunk ids, scores, and the explicit `evidence_eligible: false` flag as JSON.

The builder uses Python's standard `sqlite3` FTS5 support and PyYAML, already a
service dependency. Generated databases are intentionally ignored by Git; the
manifests and knowledge notes are the reproducible source of truth.

## Adding material

1. Add or update a bibliographic record in `source_catalog.yaml`.
2. Reference its `id` from exactly the role manifests that need it.
3. Add a concise, attributed synthesis to the role's knowledge file.
4. Only place a full source snapshot under `raw/` when its licence permits
   local storage and use. Record its origin and version in the role manifest.
5. Rebuild the role database and review the reported source/chunk counts.

Do not silently download paywalled ISO standards, copyrighted books, or
publisher PDFs into the repository. Their official catalogue pages and
abstracts can be indexed as leads; licensed full text must be supplied by an
authorised user and remains local.

## Retrieval contract

Every manifest supplies role-specific queries and a bounded source list. The
database schema records `evidence_eligible = 0` for these chunks. The active
workflow's context boundary should continue to label retrieved role material as
supplemental and non-citable unless a matching verified evidence unit exists in
the declared study corpus.
