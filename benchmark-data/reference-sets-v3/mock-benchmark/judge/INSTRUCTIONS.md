# Matching protocol for reviewers

You are an independent reviewer in a requirements benchmark. You compare **reference atoms**
(requirements taken from a published document) with **candidate needs** (statements written
by an extraction system) and label how each need relates to each atom.

You do not know which system or version produced the needs, and you must not try to find out.
Read only the two files named in your task and this file. Do not open anything else under
`/home/claude` (in particular nothing under `/home/claude/mock/private`, `/home/claude/merge`,
`/home/claude/profile-requirements-extraction`, or another reviewer's output).

## Files

- Atoms: `atom_id`, `statement` (the requirement), `source_passage` (the passage the atom comes
  from, for context only), `source_wording_of_obligation` (the source's own obligation wording,
  an internal code), `status_in_source`.
- Needs: `need_id`, `statement`.

## Task

For every atom, read the **whole** needs list and record every need that relates to the atom,
with one label describing the **need relative to the atom**:

| Label | Meaning |
|---|---|
| `equivalent` | The need asks for the same thing as the atom: the same information item or capability, about the same kind of resource (dataset, distribution, catalogue, catalogue record, agent, observation, slice …), with the same scope and conditions. |
| `narrower` | The need covers only a part, a special case or a sub-item of what the atom asks for. |
| `broader` | The need includes what the atom asks for but also asks for more: it lists several items of which the atom's is one, or states a more general need that subsumes the atom. |
| `partial` | The need and the atom overlap, but neither contains the other: same information item for a different resource, a different scope, condition or purpose, or some aspects shared and others added. |
| `conflicts` | The need contradicts the atom. |

Everything else is **unrelated**: do not list it.

Rules:

1. Compare meaning, not words. A shared word or vocabulary term (e.g. both mention
   "identifier" or `dct:identifier`) is not a relation by itself.
2. Phrasing frames do not matter. "Users can know/find X", "Publishers can state X" and an atom
   "Describe/Identify/State X" are the same requirement when X is the same. Close synonyms count
   when the context makes them the same thing (e.g. creator and author of a dataset).
3. An actor counts only when the atom names a specific actor or audience (e.g. software agents,
   potential data consumers) and the need names a different one.
4. An obligation the need does not state does not break equivalence. An obligation the need
   states that contradicts the atom's (optional vs. required) makes it at most `partial`.
5. A purpose or condition in the atom ("so that datasets can be filtered by them", "when data are
   published more than once a day") is part of its scope: a need without it is at most
   `broader` or `partial`, unless the purpose is only an explanation that does not change what is
   required.
6. Decide each pair on its own. Several needs can be equivalent to one atom (near-duplicates):
   list each. One need can relate to several atoms.
7. Many atoms will have no related need. That is expected; do not stretch a label to fill one.

Examples (invented domain, not from the files):

- Atom "State the opening hours of a library."
  - "Users can know when a library is open." → `equivalent`
  - "Users can know the opening hours of a library on public holidays." → `narrower`
  - "Users can know the address, opening hours and phone number of a library." → `broader`
  - "Users can know the opening hours of a library's café." → `partial` (different resource)
  - "Users can know the address of a library." → unrelated (not listed)

## Output

Write JSON to the output path in your task:

```json
{"case": "<case>", "judge": "<letter>", "atoms": [
  {"atom_id": "X-1.1", "matches": [
    {"need_id": "N123", "label": "equivalent", "rationale": "one short sentence"}
  ]}
]}
```

Include every atom, with an empty `matches` list when no need relates. Check that the file
parses as JSON, that every atom appears once, and that every `need_id` exists in the needs file.
