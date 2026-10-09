# GeoDCAT-AP

Freeze the initial **v1.0, 2015-12-23** specification. Its requirements concern alignment
and profile architecture as well as metadata content. The original licensed specification
is kept in `reference-requirements/`; its sections 1.1, 4.1 and 4.2 support **seven scoped
curator reference constraints**.

Raw documents include original public INSPIRE Directive/metadata/interoperability texts,
INSPIRE metadata technical guidelines **v1.3 (2013)**, and W3C DCAT (2014). These provide a
partial standards-derived corpus. The available DCAT-AP 1.1 PDF has later 2017 metadata
and is provenance-only. Exact earlier alignment drafts and working-group experiences are
not fully recovered. No preconsolidation corpus is available.

**No ISO standard text is included.** ISO 19115:2003, 19119:2005 and ISO/TS 19139:2007 have
citation records and copyright limitations. Public EC/INSPIRE implementation guidance is
included under its own public/reuse notice; it is not represented as a copy of, or an
alternative licence for, the ISO standards. ISO-derived coverage remains partial.

The reference separates architectural alignment constraints from domain-content
requirements. Recoverability must be reviewed against the staged raw documents: a
project-specific architectural choice is not necessarily inferable from a legal standard.
Mobility includes GeoDCAT 1.0.1 as a documented prior-extension input. That release
shares alignment criteria with this target; Geo is not independent held-out data if
mobility has been used for training or iterative tuning. Freeze before both evaluations
and disclose this source overlap. Keep Geo held out if its geospatial/standards evidence closely resembles the target PhD
application; do not tune on its answer table while calling it a held-out domain.

See [manifest](provenance/manifest.json), [gaps](provenance/GAPS.md),
[methodology](../BENCHMARK-METHODOLOGY.md), and [runtime allowlists](../runtime-inputs.json).
