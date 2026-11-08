#!/usr/bin/env python3
"""Prepare this repository for double-anonymous review (e.g. the ESWC Research Track).

  anonymize.py check [--history] [--strict] [--root DIR]
      Report author-identifying terms in the files of a repository (tracked and
      untracked-but-not-ignored) and, with --history, in its Git history.
      Exit code 1 when a [replace] term remains outside protected paths.

  anonymize.py snapshot [--out DIR] [--ref REF] [--zip] [--no-git] [--no-notice]
                        [--author 'Name <email>'] [--exclude PATH ...] [--force]
      Export REF (default HEAD) into a fresh directory, rewrite the [replace]
      terms, recompute the base-catalogue hashes that cover a rewritten reviewer
      name, re-pin the workflow implementation hash that scripts and tests
      record, prepend a review notice to README.md, verify, optionally zip, and
      start a new single-commit Git history under an anonymous author. Push the
      result to a neutral repository or upload the zip to Zenodo / EasyChair.

Terms, flags and protected paths come from terms.txt next to this file.
Standard library only, Python 3.11+. Guide: docs/ANONYMOUS_SUBMISSION.md.
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_ROOT = HERE.parents[1]
DEFAULT_TERMS = HERE / 'terms.txt'
DEFAULT_AUTHOR = 'Anonymous Authors <anonymous@example.org>'
DEFAULT_REPLACEMENT = 'ANONYMIZED'
# Never part of a shared copy: they describe the authors' identity.
DEFAULT_EXCLUDES = ('scripts/anonymization', 'docs/ANONYMOUS_SUBMISSION.md')
CATALOGUE_DIR = 'requirement-reuse-service/config/base_profiles'
WORKFLOW_DIR = 'requirement-reuse-service/requirement_reuse_service/workflow'
SKIP_DIRS = {'.git', 'node_modules', '.venv', '__pycache__', '.pytest_cache', 'dist'}
COMMIT_MESSAGE = 'Anonymized snapshot for double-anonymous review'
NOTICE = (
    '> **Anonymized snapshot for double-anonymous review.** Names, affiliations,\n'
    '> account names and links that identify the authors have been replaced with\n'
    '> `ANONYMIZED` / `Anonymous Author`, and the commit history has been reduced to\n'
    '> a single anonymous commit. Attribution and the original history will be\n'
    '> restored in the camera-ready version.\n\n'
)

EMAIL = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+')
SESSION_LINK = re.compile(r'claude\.ai/code/session_[A-Za-z0-9]+')
GITHUB_OWNER = re.compile(r'github\.com/([A-Za-z0-9][A-Za-z0-9-]{0,38})(?=[/"\')\]>\s,.]|$)')
GITHUB_SITE_PATHS = {'about', 'advisories', 'apps', 'blog', 'enterprise', 'explore', 'features', 'join',
                     'login', 'marketplace', 'orgs', 'pricing', 'search', 'security', 'settings', 'site',
                     'sponsors', 'topics'}


@dataclass
class Terms:
    replace: dict[str, str]            # casefolded term -> replacement
    flag: list[str]
    protect: list[str]
    pattern: re.Pattern[str] | None = None
    flag_pattern: re.Pattern[str] | None = None

    @classmethod
    def load(cls, path: Path) -> 'Terms':
        replace: dict[str, str] = {}
        flag: list[str] = []
        protect: list[str] = []
        section = None
        for number, raw in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
            line = raw.strip()
            if not line or line.startswith('#'):
                continue
            if line in ('[replace]', '[flag]', '[protect]'):
                section = line[1:-1]
                continue
            if section is None:
                sys.exit(f'{path}:{number}: a term before the first [section]')
            if section == 'replace':
                term, _, replacement = (part.strip() for part in line.partition('=>'))
                replace[term.casefold()] = replacement or DEFAULT_REPLACEMENT
            elif section == 'flag':
                flag.append(line)
            else:
                protect.append(line)
        if not replace:
            sys.exit(f'{path}: no [replace] terms')
        terms = cls(replace, flag, protect)
        terms.pattern = _alternation(replace)
        terms.flag_pattern = _alternation(flag) if flag else None
        return terms

    def replacement(self, match: re.Match[str]) -> str:
        return self.replace[match.group(0).casefold()]

    def protected(self, relative: str) -> bool:
        return any(fnmatch.fnmatchcase(relative, glob) for glob in self.protect)


def _alternation(terms) -> re.Pattern[str]:
    ordered = sorted(terms, key=len, reverse=True)       # longest first: "Junda Huang" before "Junda"
    return re.compile('|'.join(re.escape(term) for term in ordered), re.IGNORECASE)


def list_files(root: Path) -> list[str]:
    """Relative POSIX paths: Git's view when ROOT is a work tree, else a walk."""
    if (root / '.git').exists():
        out = subprocess.run(['git', '-C', str(root), 'ls-files', '-z', '--cached', '--others', '--exclude-standard'],
                             capture_output=True, check=True).stdout
        return sorted({p for p in out.decode('utf-8', 'surrogateescape').split('\0') if p and (root / p).is_file()})
    found = []
    for directory, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for name in filenames:
            found.append((Path(directory) / name).relative_to(root).as_posix())
    return sorted(found)


def read_text(path: Path) -> str | None:
    """Text with the original bytes recoverable; None for binary files."""
    data = path.read_bytes()
    if b'\0' in data[:8192]:
        return None
    return data.decode('utf-8', 'surrogateescape')


# ----------------------------------------------------------------------------- check

@dataclass
class Report:
    root: Path
    files: int = 0
    binaries: int = 0
    replace_hits: dict[str, Counter] = field(default_factory=lambda: defaultdict(Counter))
    protected_hits: dict[str, Counter] = field(default_factory=lambda: defaultdict(Counter))
    flag_hits: dict[str, Counter] = field(default_factory=lambda: defaultdict(Counter))
    path_hits: list[tuple[str, str]] = field(default_factory=list)
    emails: dict[str, str] = field(default_factory=dict)          # address -> first file
    session_links: Counter = field(default_factory=Counter)
    owners: Counter = field(default_factory=Counter)
    identities: Counter = field(default_factory=Counter)
    commits: int = 0
    commits_with_terms: int = 0
    commits_with_links: int = 0

    def failing(self, strict: bool = False) -> bool:
        return bool(self.replace_hits or self.path_hits or (strict and (self.flag_hits or self.protected_hits)))


def scan(root: Path, terms: Terms, history: bool = False) -> Report:
    report = Report(root)
    for relative in list_files(root):
        if any(relative == skip or relative.startswith(skip + '/') for skip in DEFAULT_EXCLUDES):
            continue
        report.files += 1
        for match in terms.pattern.finditer(relative):
            report.path_hits.append((relative, match.group(0)))
        text = read_text(root / relative)
        if text is None:
            report.binaries += 1
            continue
        bucket = report.protected_hits if terms.protected(relative) else report.replace_hits
        for match in terms.pattern.finditer(text):
            bucket[match.group(0).casefold()][relative] += 1
        if terms.flag_pattern:
            for match in terms.flag_pattern.finditer(text):
                report.flag_hits[match.group(0).casefold()][relative] += 1
        for address in EMAIL.findall(text):
            report.emails.setdefault(address.lower(), relative)
        report.session_links[relative] += len(SESSION_LINK.findall(text))
        for owner in GITHUB_OWNER.findall(text):
            if owner.lower() not in GITHUB_SITE_PATHS:
                report.owners[owner] += 1
    if history and (root / '.git').exists():
        scan_history(root, terms, report)
    return report


def scan_history(root: Path, terms: Terms, report: Report) -> None:
    git = ['git', '-C', str(root), 'log', '--all']
    names = subprocess.run([*git, '--format=%an <%ae>%n%cn <%ce>'], capture_output=True, text=True, check=True).stdout
    report.identities.update(line for line in names.splitlines() if line.strip())
    bodies = subprocess.run([*git, '-z', '--format=%B'], capture_output=True, text=True, check=True).stdout
    for body in filter(None, bodies.split('\0')):
        report.commits += 1
        report.commits_with_terms += bool(terms.pattern.search(body) or (terms.flag_pattern and terms.flag_pattern.search(body)))
        report.commits_with_links += bool(SESSION_LINK.search(body) or re.search(r'^Claude-Session:', body, re.M))


def _print_hits(title: str, hits: dict[str, Counter], examples: int = 4) -> None:
    print(title)
    for term, files in sorted(hits.items(), key=lambda item: -sum(item[1].values())):
        print(f'  {term:<34} {sum(files.values()):>5} hits in {len(files)} file(s)')
        for relative, count in files.most_common(examples):
            print(f'      {relative} ({count})')
        if len(files) > examples:
            print(f'      ... and {len(files) - examples} more file(s)')


def print_report(report: Report, strict: bool) -> None:
    print(f'Anonymization check of {report.root}: {report.files} files scanned, {report.binaries} binary files skipped\n')
    if report.replace_hits:
        _print_hits('REPLACE terms still present (rewritten by `snapshot`; must be gone from anything shared):', report.replace_hits)
    else:
        print('REPLACE terms: none found outside protected paths.')
    if report.path_hits:
        print('REPLACE terms in file or directory names:')
        for relative, term in report.path_hits:
            print(f'  {relative}  ({term})')
    if report.protected_hits:
        _print_hits('\nREPLACE terms inside protected paths (not rewritten; judge by hand, usually third-party text):', report.protected_hits)
    if report.flag_hits:
        _print_hits('\nFLAG terms (never rewritten; judge by hand):', report.flag_hits, examples=2)
    print('\nPatterns:')
    emails = sorted(report.emails)
    print(f'  e-mail addresses: {len(emails)} distinct' + (f', e.g. {emails[0]} in {report.emails[emails[0]]}' if emails else ''))
    links = +report.session_links
    print(f'  claude.ai session links: {sum(links.values())} in {len(links)} file(s)')
    owners = ', '.join(f'{owner} ({count})' for owner, count in report.owners.most_common(12))
    print(f'  GitHub owners referenced: {owners or "none"}')
    if report.commits:
        print('\nGit history (not part of a `snapshot`, which starts a fresh history):')
        for identity, count in report.identities.most_common():
            print(f'  {identity}  ({count} author/committer entries)')
        print(f'  {report.commits} commits; {report.commits_with_terms} mention a term; '
              f'{report.commits_with_links} carry session links or trailers')
    verdict = 'FAIL' if report.failing(strict) else 'PASS'
    notes = []
    if report.protected_hits:
        notes.append('hits in protected paths')
    if report.flag_hits:
        notes.append('flag terms to judge')
    print(f'\nResult: {verdict}' + (f' (with {" and ".join(notes)})' if notes and verdict == 'PASS' else ''))


def cmd_check(args: argparse.Namespace) -> int:
    terms = Terms.load(args.terms)
    report = scan(args.root, terms, history=args.history)
    print_report(report, args.strict)
    return 1 if report.failing(args.strict) else 0


# -------------------------------------------------------------------------- snapshot

def rewrite_tree(out: Path, terms: Terms) -> tuple[int, int]:
    replacements = changed = 0
    for relative in list_files(out):
        if terms.protected(relative):
            continue
        path = out / relative
        text = read_text(path)
        if text is None:
            continue
        new, count = terms.pattern.subn(terms.replacement, text)
        if count:
            path.write_bytes(new.encode('utf-8', 'surrogateescape'))
            replacements += count
            changed += 1
    return replacements, changed


def rename_paths(out: Path, terms: Terms) -> list[str]:
    candidates = [p for p in out.rglob('*') if terms.pattern.search(p.name)
                  and not terms.protected(p.relative_to(out).as_posix())]
    renamed = []
    for path in sorted(candidates, key=lambda p: len(p.parts), reverse=True):   # deepest first
        target = path.with_name(terms.pattern.sub(terms.replacement, path.name))
        path.rename(target)
        renamed.append(f'{path.relative_to(out).as_posix()} -> {target.name}')
    return renamed


def catalogue_digest(body: dict) -> str:
    """Mirrors workflow/storage.py digest() and scripts/build_base_needs.py catalogue_hash()."""
    canonical = json.dumps({k: v for k, v in body.items() if k != 'catalogue_hash'},
                           sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def rehash_catalogues(out: Path) -> list[str]:
    """A rewritten reviewer name changes the review file and the catalogue; re-pin both hashes."""
    changed = []
    for needs in sorted((out / CATALOGUE_DIR).glob('*.needs.json')):
        body = json.loads(needs.read_text(encoding='utf-8'))
        review = body.get('review')
        review_file = needs.with_name(needs.name.removesuffix('.needs.json') + '.needs-review.json')
        if isinstance(review, dict) and review.get('review_file_sha256') and review_file.exists():
            review['review_file_sha256'] = hashlib.sha256(review_file.read_bytes()).hexdigest()
        digest = catalogue_digest(body)
        if digest != body.get('catalogue_hash'):
            body['catalogue_hash'] = digest
            needs.write_text(json.dumps(body, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
            changed.append(needs.relative_to(out).as_posix())
    return changed


def implementation_identity(out: Path) -> str | None:
    """Mirrors workflow/engine.py implementation_identity(): a hash over the workflow modules."""
    folder = out / WORKFLOW_DIR
    if not folder.is_dir():
        return None
    files = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in folder.glob('*.py')}
    canonical = json.dumps(files, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def repin_identity(out: Path, terms: Terms, old: str | None, new: str | None) -> int:
    """Rewritten comments change the workflow's implementation hash, which scripts/closed_book.py,
    scripts/cb_base_labels.py, their tests and the docs record; re-pin the recorded prefix."""
    if not old or not new or old == new:
        return 0
    changed = 0
    for relative in list_files(out):
        if terms.protected(relative):
            continue
        path = out / relative
        text = read_text(path)
        if text is None or old[:16] not in text:
            continue
        path.write_bytes(text.replace(old, new).replace(old[:16], new[:16]).encode('utf-8', 'surrogateescape'))
        changed += 1
    return changed


def init_git(out: Path, author: str) -> None:
    match = re.fullmatch(r'\s*(.+?)\s*<([^>]+)>\s*', author)
    if not match:
        sys.exit(f'--author must look like "Name <email>", got {author!r}')
    name, email = match.groups()
    env = {**os.environ, 'GIT_AUTHOR_NAME': name, 'GIT_AUTHOR_EMAIL': email,
           'GIT_COMMITTER_NAME': name, 'GIT_COMMITTER_EMAIL': email}
    git = ['git', '-C', str(out), '-c', 'commit.gpgsign=false', '-c', f'user.name={name}', '-c', f'user.email={email}']
    subprocess.run([*git, 'init', '-q', '-b', 'main'], check=True, env=env)
    subprocess.run([*git, 'add', '-A'], check=True, env=env)
    subprocess.run([*git, 'commit', '-q', '-m', COMMIT_MESSAGE], check=True, env=env)


def cmd_snapshot(args: argparse.Namespace) -> int:
    root, terms = args.root, Terms.load(args.terms)
    out = Path(args.out).resolve() if args.out else root.parent / f'{root.name}-anonymous'
    if out == root or root in out.parents:
        sys.exit('the snapshot must be created outside the repository')
    if out.exists() and any(out.iterdir()):
        if not args.force:
            sys.exit(f'{out} exists and is not empty; pass --force to replace it')
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / 'export.tar'
        subprocess.run(['git', '-C', str(root), 'archive', '--format=tar', '-o', str(archive), args.ref], check=True)
        with tarfile.open(archive) as tar:
            try:
                tar.extractall(out, filter='data')
            except TypeError:                       # Python < 3.12 without the filter argument
                tar.extractall(out)
    for relative in (*DEFAULT_EXCLUDES, *args.exclude):
        target = out / relative
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()

    identity_before = implementation_identity(out)
    replacements, changed = rewrite_tree(out, terms)
    renamed = rename_paths(out, terms)
    rehashed = rehash_catalogues(out)
    repinned = repin_identity(out, terms, identity_before, implementation_identity(out))
    readme = out / 'README.md'
    if not args.no_notice and readme.exists():
        readme.write_text(NOTICE + readme.read_text(encoding='utf-8'), encoding='utf-8')

    report = scan(out, terms)
    if report.failing():
        print_report(report, strict=False)
        print(f'\nSnapshot at {out} still contains replace terms; fix terms.txt and rerun.', file=sys.stderr)
        return 2
    zipped = shutil.make_archive(str(out), 'zip', root_dir=out) if args.zip else None
    if not args.no_git:
        init_git(out, args.author)

    print(f'Snapshot ready: {out}')
    print(f'  {report.files} files; {replacements} replacements in {changed} files; {len(renamed)} paths renamed; '
          f'{len(rehashed)} catalogue(s) re-hashed{": " + ", ".join(rehashed) if rehashed else ""}')
    if repinned:
        print(f'  workflow implementation hash re-pinned in {repinned} files (comments changed)')
    for line in renamed:
        print(f'  renamed {line}')
    if zipped:
        print(f'  zip for Zenodo / EasyChair: {zipped}')
    if report.flag_hits or report.protected_hits:
        print('  flag terms or protected-path hits remain; see `anonymize.py check --root ' + str(out) + '`')
    print('\nNext steps (details in docs/ANONYMOUS_SUBMISSION.md):')
    print('  1. Create an EMPTY repository with a neutral name under a neutral owner, e.g.')
    print('       gh repo create <neutral-org>/<neutral-name> --public   (or --private, see the guide)')
    print(f'  2. cd {out} && git remote add origin git@github.com:<neutral-org>/<neutral-name>.git && git push -u origin main')
    print('  3. On https://anonymous.4open.science add that repository, paste the [replace] and [flag] terms')
    print('     from scripts/anonymization/terms.txt, set the expiration after the notification date, and')
    print('     open the generated link in a private browser window before putting it in the paper.')
    return 0


def main(argv: list[str] | None = None) -> int:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument('--root', type=lambda p: Path(p).resolve(), default=DEFAULT_ROOT,
                        help='repository or snapshot directory to read (default: this repository)')
    common.add_argument('--terms', type=Path, default=DEFAULT_TERMS, help='terms file (default: terms.txt next to this script)')
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest='command', required=True)
    check = commands.add_parser('check', parents=[common], help='report identifying terms')
    check.add_argument('--history', action='store_true', help='also report Git author identities and commit messages')
    check.add_argument('--strict', action='store_true', help='fail on flag terms and protected-path hits too')
    check.set_defaults(run=cmd_check)
    snapshot = commands.add_parser('snapshot', parents=[common], help='build an anonymized copy with a fresh history')
    snapshot.add_argument('--out', help='target directory (default: ../<repo>-anonymous)')
    snapshot.add_argument('--ref', default='HEAD', help='commit, branch or tag to export (default: HEAD)')
    snapshot.add_argument('--author', default=DEFAULT_AUTHOR, help=f'author of the single commit (default: {DEFAULT_AUTHOR})')
    snapshot.add_argument('--exclude', action='append', default=[], metavar='PATH', help='additional path to leave out (repeatable)')
    snapshot.add_argument('--zip', action='store_true', help='also write <out>.zip (without .git) for Zenodo or EasyChair')
    snapshot.add_argument('--no-git', action='store_true', help='do not create the single-commit Git history')
    snapshot.add_argument('--no-notice', action='store_true', help='do not prepend the review notice to README.md')
    snapshot.add_argument('--force', action='store_true', help='replace a non-empty target directory')
    snapshot.set_defaults(run=cmd_snapshot)
    args = parser.parse_args(argv)
    if not args.terms.exists():
        sys.exit(f'terms file not found: {args.terms}')
    return args.run(args)


if __name__ == '__main__':
    sys.exit(main())
