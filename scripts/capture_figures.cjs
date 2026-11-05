#!/usr/bin/env node
// Screenshots of the workbench for the RQ1 paper: one saved run, captured read-only with Playwright.
//
// Serve the UI and the API on a COPY of the store that holds the run, with the model provider disabled
// (opening pages then never starts a model call), and build the UI first (cd frontend && npm run build):
//   RRS_LLM_PROVIDER=disabled RQ1_WORKFLOW_STORE=/path/to/copy.sqlite3 \
//     python -m uvicorn requirement_reuse_service.main:app --app-dir requirement-reuse-service --port 8011
// Then:
//   node scripts/capture_figures.cjs --run <run_id> [--base http://127.0.0.1:8011]
//     [--out benchmark-data/figures/screenshots] [--only S06,S10] [--widths 600,1000]
//   node scripts/capture_figures.cjs --run <run_id> --sheet      # contact-sheet.pdf from manifest.json
// Web addresses in a shot's visible text are listed per shot (url_hosts) for review.
// Needs the playwright package (tested with 1.56.1) and its Chromium.
//
// Nothing is clicked that saves anything: the clicks below only open the evidence inspector, a need's review
// page and a saved result, all of which read. Every shot is an element screenshot; header, footer and provider
// settings are hidden by injected CSS before capture.
const { chromium } = require('playwright');
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const arg = (name, fallback) => { const i = process.argv.indexOf(`--${name}`); return i > 0 ? process.argv[i + 1] : fallback; };
const BASE = arg('base', 'http://127.0.0.1:8011');
const RUN = arg('run');
const OUT = path.resolve(arg('out', 'benchmark-data/figures/screenshots'));
const ONLY = arg('only') ? new Set(arg('only').split(',')) : null;
const WIDTHS = arg('widths', '600,1000').split(',').map(Number);
const DPR = 2;
const PAPER_WIDTH = 600;          // single-column layout of the stylesheet; tags print at >= 6 pt at 12.2 cm
const STRIP_MAX = 220;            // CSS px: a main-text strip of about 4.5 cm at 12.2 cm wide
const APPENDIX_MAX = 830;         // CSS px: an appendix figure of at most 17 cm
const FULL_PAGE_MAX = 6000;       // CSS px kept of a stage's full page in record/
if (!RUN) { console.error('usage: node scripts/capture_figures.cjs --run <run_id> [--base URL] [--out DIR]'); process.exit(2); }

// Policies of the freeze of 30 Oct 2026 (commit aefc12a); the run must carry exactly these.
const FROZEN = { grouping: 'rq1-need-semantic-grouping-v3', need_statement: 'rq1-need-statement-v5', profile_scope: 'rq1-profile-scope-v9',
  proposal_support: 'rq1-proposal-support-v2', discussion: 'rq1-fa-dialogue-v14' };

const HIDDEN = ['header.rq1-header', 'footer.rq1-status', 'details.provider-settings', 'details.workflow-step-models'];
const CSS = `${HIDDEN.join(', ')} { display: none !important; }
*::-webkit-scrollbar { display: none; } * { scrollbar-width: none; }
:focus { outline: none !important; } * { animation: none !important; transition: none !important; caret-color: transparent !important; }`;

// Visible text that must not appear in any shot (double-blind review): names, handles, paths, hosts, keys.
const FORBIDDEN = [/junda/i, /huang/i, /sebastian/i, /github/i, /\/home\//, /\/users\//i, /\/root\//, /\/tmp\//, /\.sqlite3?\b/i, /kiconnect/i,
  /\.nrw\b/i, /api[_ -]?key/i, /\bbearer\b/i, /\bsk-[a-z0-9]{8}/i, /localhost/i, /127\.0\.0\.1/, /[\w.+-]+@[\w-]+\.[\w.]+/];

const sha256 = file => crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
const api = async route => { const r = await fetch(`${BASE}/api/rq1/v2${route}`); if (!r.ok) throw new Error(`${route}: ${r.status}`); return r.json(); };
const route = stage => `${BASE}/#/workflow/${RUN}/${stage}`;

// Count the page's requests in flight: a click that loads a trace or a saved result is settled only when the
// network has been quiet for half a second (waitForLoadState returns at once after the first load).
function track(page) {
  let inflight = 0, last = Date.now();
  page.on('request', () => { inflight++; last = Date.now(); });
  const done = () => { inflight = Math.max(0, inflight - 1); last = Date.now(); };
  page.on('requestfinished', done); page.on('requestfailed', done);
  page.quiet = async (ms = 500, timeout = 120000) => {
    for (const start = Date.now(); Date.now() - start < timeout; await page.waitForTimeout(100)) if (!inflight && Date.now() - last >= ms) return;
    throw new Error('the network never went quiet');
  };
}

async function settle(page) {
  await page.quiet();
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(250);
}

async function open(page, stage) {
  if (!page.quiet) track(page);
  await page.goto(route(stage), { waitUntil: 'networkidle' });
  await page.addStyleTag({ content: CSS });
  await settle(page);
}

// Close every <details> on the page, then open those whose own summary matches one of the patterns
// (outer first, so a nested one is visible when it opens). Returns the summaries opened.
async function setDetails(page, patterns = []) {
  return page.evaluate(sources => {
    const res = sources.map(s => new RegExp(s));
    const opened = [];
    for (const d of document.querySelectorAll('details')) {
      const summary = (d.querySelector(':scope > summary')?.textContent ?? '').trim();
      d.open = res.some(re => re.test(summary));
      if (d.open) opened.push(summary);
    }
    return opened;
  }, patterns.map(p => (p instanceof RegExp ? p.source : `^${p.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}`)));
}

// Facts about what a capture shows: size, smallest text and its print size, anything forbidden in its text.
async function inspect(locator) {
  return locator.evaluate((el, forbidden) => {
    const box = el.getBoundingClientRect();
    let minPx = Infinity;
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    for (let n = walker.nextNode(); n; n = walker.nextNode()) {
      if (!n.textContent.trim()) continue;
      const parent = n.parentElement; const style = getComputedStyle(parent);
      if (style.display === 'none' || style.visibility === 'hidden' || !parent.getClientRects().length) continue;
      minPx = Math.min(minPx, parseFloat(style.fontSize));
    }
    const text = el.innerText;
    const hits = forbidden.map(s => new RegExp(s, 'i')).filter(re => re.test(text)).map(re => re.source);
    const hosts = [...new Set((text.match(/\bhttps?:\/\/[^\s"'<>)\]]+/g) ?? []).map(u => { try { return new URL(u).hostname; } catch { return u; } }))];
    return { width: Math.round(box.width), height: Math.round(box.height), min_font_px: minPx === Infinity ? null : minPx, forbidden: hits, hosts };
  }, FORBIDDEN.map(re => re.source));
}

// Split an element into crops of at most `max` CSS px, cutting only above a block: the element is broken down
// into its descendants of at most `max` px (a taller one with children is broken down further), and the blocks
// are packed top to bottom. A block taller than `max` without children stays one crop. Returns page clips.
async function chunks(locator, max) {
  return locator.evaluate((el, max) => {
    const shown = node => getComputedStyle(node).display !== 'none' && node.getBoundingClientRect().height > 0;
    const blocks = [];
    const visit = node => {
      const kids = [...node.children].filter(shown);
      if (node !== el && (node.getBoundingClientRect().height <= max || !kids.length)) blocks.push(node);
      else kids.forEach(visit);
    };
    visit(el);
    const box = el.getBoundingClientRect();
    const cuts = [box.top];
    let fitted = box.top;           // bottom of the last block that fits in the current crop
    for (const block of blocks) {
      const b = block.getBoundingClientRect();
      const start = cuts[cuts.length - 1];
      if (b.bottom - start > max && fitted > start + 1) cuts.push(fitted);
      fitted = Math.max(fitted, b.bottom);
    }
    cuts.push(box.bottom);
    return cuts.slice(0, -1).map((y, i) => ({ x: box.left + scrollX, y: y + scrollY, width: box.width, height: cuts[i + 1] - y }));
  }, max);
}

// The shot list (Sect. 4 of the capture specification). `target` returns the element to capture; `open` lists
// the <details> to open; `act` runs reading-only clicks; `split` adds strip or appendix crops at 600 px.
function shots(ids) {
  const need = (page, text) => page.locator('.workflow-candidates > article').filter({ hasText: text }).first();
  const panel = (page, heading) => page.locator('section.workflow-panel').filter({ has: page.locator(':scope > h2', { hasText: heading }) }).first();
  return [
    { id: 'S01a', stage: 'acquisition', slug: 'base-profile', open: ['Pinned base-profile file'], destination: 'supplement',
      target: page => page.locator('section.workflow-panel').filter({ hasText: 'Starting from' }).first(),
      shows: 'The pinned base profile of the run (DCAT-AP 1.1), its checksum and the reviewed base catalogue.' },
    { id: 'S01b', stage: 'acquisition', slug: 'frozen-sources', destination: 'supplement', target: page => panel(page, 'Frozen input sources'),
      shows: 'The frozen corpus of the run: its two source documents, and its (empty) scope and competency questions.' },
    { id: 'S02', stage: 'decomposition', slug: 'evidence-unit', destination: 'supplement', chosen_ids: { unit: ids.unit }, viewportHeight: 2400,
      act: async page => { await page.getByRole('button', { name: new RegExp(`^${ids.unit.slice(0, 18)}`) }).click(); await settle(page); },
      open: ['Address and structural context'], target: page => page.locator('.workflow-evidence-overlay > section.workflow-panel'),
      shows: 'One evidence unit in the evidence inspector: its kind, source resolution, text, and its address (selector offsets and structural context).' },
    { id: 'S03', stage: 'role_selection', slug: 'stakeholders', destination: 'supplement, appendix candidate', split: APPENDIX_MAX,
      target: page => panel(page, '3a · Stakeholders and role selection'),
      shows: 'The stakeholder roles: those discovered with their basis, the relevance decision, the selected panel and the manifest hash.' },
    { id: 'S04a', stage: 'elicitation', slug: 'extraction-routing', destination: 'main-text strip (a), supplement', split: STRIP_MAX,
      target: page => panel(page, 'Extraction results'),
      shows: 'Extraction by role: each selected role and the shared source extractor, its status, proposals and evidence units processed.' },
    { id: 'S04b', stage: 'consolidation', slug: 'proposals-of-a-need', destination: 'main-text strip (a), supplement', chosen_ids: { need: ids.groupNeed },
      open: [/^Supporting candidates/, /^Member citations/],
      target: page => need(page, ids.groupNeedText).locator('details').filter({ has: page.locator(':scope > summary', { hasText: 'Supporting candidates' }) }).first(),
      shows: 'The two proposals grouped into one need: each statement, the role that proposed it, its source check and its cited quotations.' },
    { id: 'S04c', stage: 'consolidation', slug: 'proposal-set-aside', destination: 'main-text strip (a), supplement', chosen_ids: { proposal: ids.rejectedProposal },
      open: [/^Not supported by quote/],
      target: page => panel(page, 'Set aside · available for review').locator('details').filter({ has: page.locator(':scope > summary', { hasText: 'Not supported by quote' }) }).first(),
      shows: 'A proposal set aside because its quotation does not support it (rejected, judged again and confirmed), with the reason and the restore control.' },
    { id: 'S05', stage: 'adjudication', slug: 'source-check', destination: 'supplement', chosen_ids: { need: ids.traceNeed }, viewportHeight: 1400,
      act: async page => {
        await need(page, ids.traceNeedText).getByRole('button', { name: 'Inspect and review' }).click(); await page.locator('.need-trace h3').waitFor(); await settle(page);
        await setDetails(page, [/^Full chain/, /^Semantic and quality assessment/]);
        await page.locator('.need-trace a.trace-link', { hasText: 'Original-source checks' }).first().click(); await settle(page);
      }, keepDetails: true, target: page => page.locator('aside.result-drawer'),
      shows: 'The saved original-source check of one record: each cited quotation located in its evidence unit, with status and offsets.' },
    { id: 'S06', stage: 'consolidation', slug: 'grouped-need', destination: 'main-text strip (b), supplement', chosen_ids: { need: ids.groupNeed }, split: STRIP_MAX,
      target: page => need(page, ids.groupNeedText),
      shows: 'One grouped need: statement, support, base label, both scope results (catalogue record named; find/access task), dataset applicability, use-case links, rank and flags.' },
    { id: 'S06-open', stage: 'consolidation', slug: 'grouped-need-open', destination: 'supplement', chosen_ids: { need: ids.groupNeed },
      open: [/^Dataset applicability/, /^Supporting candidates/, /^Matching base needs/, /^Use cases/],
      target: page => need(page, ids.groupNeedText),
      shows: 'The same need with its members, dataset applicability, use cases and matching base needs open.' },
    { id: 'S07', stage: 'consolidation', slug: 'set-aside-needs', destination: 'supplement, appendix candidate', split: APPENDIX_MAX,
      open: [/·\s*[1-9]\d*$/], target: page => panel(page, 'Set aside · available for review'),
      shows: 'Set-aside needs and proposals grouped by reason, each with its rationale and the control to restore it for review.' },
    { id: 'S08', stage: 'base_review', slug: 'base-review-need', destination: 'supplement', chosen_ids: { need: ids.baseNeed },
      open: [/^Base reviewer:/, /^Matching base needs/, /^Base comparison audit/],
      target: page => need(page, ids.baseNeedText),
      shows: 'A need labelled covered by the base: the matched base entries, the base reviewer verdict and its confirming check.' },
    { id: 'S08b', stage: 'base_review', slug: 'base-reviewer', destination: 'supplement', open: [/disagreements need human review$/],
      target: page => panel(page, 'Base reviewer (procedural, not a stakeholder)'),
      shows: 'The procedural base reviewer: its counts per phase and the disagreements left as questions for a person.' },
    { id: 'S09', stage: 'consolidation', slug: 'coverage', destination: 'supplement', split: APPENDIX_MAX,
      open: [/^Stage counts and unresolved checks/],
      hide: { css: ':scope > ol', what: 'the list of the compact representatives (76 needs, each with a review button)' },
      target: page => panel(page, 'Dataset kinds and compact requirements'),
      shows: 'Coverage of the run: evidence units checked and the number of dataset kinds, the counts of each needs stage (grouped, retained, set aside, unresolved), and the size of the compact selection.' },
    { id: 'S09b', stage: 'consolidation', slug: 'dataset-kind', destination: 'supplement', chosen_ids: { dataset_kind: 'qb:DataSet' },
      open: [/^Dataset kinds and their sources/],
      target: page => panel(page, 'Dataset kinds and compact requirements').locator('article').filter({ has: page.locator(':scope > h3', { hasText: /^qb:DataSet$/ }) }).first(),
      shows: 'One of the 48 source-linked dataset kinds (qb:DataSet) with its three source quotations and their rationales.' },
    { id: 'S10', stage: 'deliberation', slug: 'discussion-case', destination: 'main-text strip (c), supplement', chosen_ids: { case: ids.caseId },
      target: page => page.locator('article.workflow-case').nth(ids.caseIndex),
      strips: [
        { name: 'mediator outcome', get: t => t.locator('section').filter({ has: t.page().locator(':scope > h4', { hasText: 'Mediator outcome' }) }),
          shows: 'The mediator outcome of the case: the need set aside with its reason and rationale, the experience it relies on, and the question for a person.' },
        { name: 'position with an excluded claim', get: t => t.locator('blockquote').filter({ hasText: 'excluded it' }),
          shows: 'One stakeholder position whose experience claim the mediator excluded, with the reason.' },
        { name: 'position with an admitted claim', get: t => t.locator('blockquote').filter({ hasText: 'admitted it' }),
          shows: 'One stakeholder position whose experience claim the mediator admitted, with the reason.' },
        { name: 'mediator action', get: t => t.locator('section').filter({ has: t.page().locator(':scope > h4', { hasText: 'Mediator outcome' }) }).locator(':scope > article').first(),
          shows: 'The mediator action on the need alone: set aside, with the set-aside reason and its rationale.' }],
      shows: 'One discussion case: its need and participants, the mediator outcome with its reason, the human-review question, and each stakeholder position with experience claims admitted or excluded.' },
    { id: 'S10-appendix', stage: 'deliberation', slug: 'discussion-case-audit', destination: 'appendix, supplement', chosen_ids: { case: ids.caseId }, split: APPENDIX_MAX,
      open: [/^Concern dispositions and complete mediation audit/], target: page => page.locator('article.workflow-case').nth(ids.caseIndex),
      shows: 'The same case with the complete mediation audit (concern dispositions) open.' },
    { id: 'S11', stage: 'adjudication', slug: 'human-review', destination: 'appendix, supplement', chosen_ids: { need: ids.traceNeed }, split: APPENDIX_MAX,
      act: async page => { await need(page, ids.traceNeedText).getByRole('button', { name: 'Inspect and review' }).click(); await page.locator('.need-trace h3').waitFor(); await settle(page); },
      open: [/^Full chain/, /^Semantic and quality assessment/],
      target: page => panel(page, '8 · Inspect and adjudicate'),
      shows: 'Human review of a need with a disputed judgment: statement and tags, where the need comes from (sources, origin, decisions with reasons, discussion, chain complete), cited evidence, the assessment and the decision buttons; no decision recorded.' },
    { id: 'S12a', stage: 'deliberation', slug: 'needs-steps-policies', destination: 'supplement', open: ['Saved needs policies'],
      target: page => panel(page, 'Needs processing progress'),
      shows: 'The ordered needs steps with their counts, and the saved policy version of each step.' },
    { id: 'S12b', stage: 'deliberation', slug: 'history-metrics', destination: 'supplement', open: ['Saved history & metrics'],
      target: page => page.locator('details.workflow-panel').filter({ has: page.locator(':scope > summary', { hasText: 'Saved history & metrics' }) }).first(),
      shows: 'The saved metrics of the run (model calls, durations and counts per step).' },
    { id: 'S12c', stage: 'deliberation', slug: 'run-trace', destination: 'supplement', target: page => panel(page, 'Run trace · deliberation'),
      shows: 'The run trace of the discussion step: the complete trace download and the need picker that follows a need back to its sources.' },
    { id: 'S13', stage: 'baseline', slug: 'validated-baseline', destination: 'supplement', target: page => panel(page, 'Validated baseline'),
      shows: 'The validated-baseline page: nothing published on this test run (no human decisions).' },
  ];
}

async function main() {
  const run = await api(`/runs/${RUN}?audit=false`);
  const policies = { ...run.needs_policies, discussion: [...new Set((run.deliberations ?? []).map(c => c.policy_version))].join(',') };
  const mismatched = Object.entries(FROZEN).filter(([k, v]) => policies[k] !== v);
  if (mismatched.length) throw new Error(`run ${RUN} is not the frozen configuration: ${JSON.stringify(mismatched)}`);
  const commit = execFileSync('git', ['log', '-1', '--first-parent', '--format=%h', '--', 'frontend', 'requirement-reuse-service']).toString().trim();

  // The content each panel shows (Rule 6), chosen from the saved run. IDs are recorded in the manifest.
  const req = Object.fromEntries(run.requirements.map(r => [r.revision_id, r]));
  const ids = JSON.parse(fs.readFileSync(path.join(__dirname, 'capture_figures.ids.json'), 'utf8'))[RUN];
  if (!ids) throw new Error(`no content choice for ${RUN} in capture_figures.ids.json`);
  ids.groupNeedText = req[ids.groupNeed].normalized_statement; ids.baseNeedText = req[ids.baseNeed].normalized_statement;
  ids.traceNeedText = req[ids.traceNeed].normalized_statement;
  ids.caseIndex = run.deliberations.findIndex(c => c.case_id === ids.caseId);
  if (ids.caseIndex < 0) throw new Error(`case ${ids.caseId} not in the run`);

  const manifestFile = path.join(OUT, 'manifest.json');
  const manifest = fs.existsSync(manifestFile) ? JSON.parse(fs.readFileSync(manifestFile, 'utf8')) : { shots: [] };
  manifest.run_id = RUN; manifest.run_name = run.name; manifest.workbench_commit = commit; manifest.policy_versions = policies;
  manifest.css_injected = CSS; manifest.elements_hidden = HIDDEN; manifest.dpr = DPR;
  const save = () => { manifest.shots.sort((a, b) => a.file.localeCompare(b.file)); fs.writeFileSync(manifestFile, JSON.stringify(manifest, null, 2) + '\n'); };
  const record = entry => { manifest.shots = manifest.shots.filter(s => s.file !== entry.file); manifest.shots.push(entry); save(); };

  const browser = await chromium.launch();
  try {
    for (const width of WIDTHS) {
      const dir = path.join(OUT, width === PAPER_WIDTH ? 'paper' : 'record'); fs.mkdirSync(dir, { recursive: true });
      for (const shot of shots(ids).filter(s => !ONLY || ONLY.has(s.id) || ONLY.has(s.id.replace(/[a-z]$|-.*$/, '')))) {
        // A shot taken again replaces its earlier files and entries at this width, parts and strips included.
        for (const old of manifest.shots.filter(s => s.viewport_width === width && s.id === shot.id)) fs.rmSync(path.join(OUT, old.file), { force: true });
        manifest.shots = manifest.shots.filter(s => !(s.viewport_width === width && s.id === shot.id));
        const context = await browser.newContext({ viewport: { width, height: shot.viewportHeight ?? 1000 }, deviceScaleFactor: DPR, colorScheme: 'light',
          locale: 'en', reducedMotion: 'reduce' });
        const page = await context.newPage();
        await open(page, shot.stage);
        if (shot.act) await shot.act(page);
        const opened = shot.keepDetails ? [] : await setDetails(page, shot.open ?? []);
        await settle(page);
        const target = shot.target(page);
        const hidden = [...HIDDEN];
        if (shot.hide) {        // a long part of the panel, hidden in this shot only (recorded in the manifest)
          await target.evaluate((el, css) => el.querySelectorAll(css).forEach(node => { node.style.setProperty('display', 'none', 'important'); }), shot.hide.css);
          hidden.push(`${shot.hide.css} inside the panel: ${shot.hide.what}`);
          await settle(page);
        }
        await target.scrollIntoViewIfNeeded();
        const facts = await inspect(target);
        const file = path.join(dir, `${shot.id}-${shot.stage}-${shot.slug}@${width}.png`);
        await target.screenshot({ path: file, animations: 'disabled', caret: 'hide', scale: 'device' });
        const entry = (f, extra = {}) => ({ id: shot.id, file: path.relative(OUT, f), stage: shot.stage, route: `#/workflow/${RUN}/${shot.stage}`, run_id: RUN,
          case: shot.chosen_ids?.case ?? null, workbench_commit: commit, policy_versions: policies, viewport_width: width, dpr: DPR,
          selector: shot.target.toString().replace(/^page => /, ''), details_opened: opened, css_injected: true, elements_hidden: hidden,
          chosen_ids: shot.chosen_ids ?? {}, destination: shot.destination, shows: shot.shows, captured_at: new Date().toISOString(), sha256: sha256(f),
          element_css_px: { width: facts.width, height: facts.height }, min_font_px: facts.min_font_px,
          min_font_pt_at_12_2cm: facts.min_font_px && +(facts.min_font_px * 345.8 / facts.width).toFixed(2), forbidden_text: facts.forbidden, url_hosts: facts.hosts, ...extra });
        record(entry(file));
        console.log(`${path.relative(OUT, file)}  ${facts.width}x${facts.height}  min ${facts.min_font_px}px${facts.forbidden.length ? '  FORBIDDEN ' + facts.forbidden : ''}${facts.hosts.length ? '  hosts ' + facts.hosts : ''}`);
        // Crops for a strip or an appendix page at 600 px: parts cut between blocks, and named sub-elements.
        if (shot.split && width === PAPER_WIDTH && facts.height > shot.split) {
          const clips = await chunks(target, shot.split);
          for (const [i, clip] of clips.entries()) {
            const part = path.join(dir, `${shot.id}-part${i + 1}-${shot.stage}-${shot.slug}@${width}.png`);
            await page.screenshot({ path: part, clip, fullPage: true, animations: 'disabled', caret: 'hide', scale: 'device' });
            record(entry(part, { split_of: shot.id, part: i + 1, parts: clips.length, limit_css_px: shot.split,
              crop_css_px: { width: Math.round(clip.width), height: Math.round(clip.height) } }));
            console.log(`  part ${i + 1}/${clips.length}  ${Math.round(clip.width)}x${Math.round(clip.height)}${clip.height > shot.split + 1 ? '  (a single block over the limit)' : ''}`);
          }
        }
        for (const [i, strip] of (width === PAPER_WIDTH ? shot.strips ?? [] : []).entries()) {
          const sub = strip.get(target).first();
          await sub.scrollIntoViewIfNeeded();
          const subFacts = await inspect(sub);
          const part = path.join(dir, `${shot.id}-strip${i + 1}-${shot.stage}-${shot.slug}@${width}.png`);
          await sub.screenshot({ path: part, animations: 'disabled', caret: 'hide', scale: 'device' });
          record(entry(part, { strip_of: shot.id, strip: strip.name, shows: strip.shows, element_css_px: { width: subFacts.width, height: subFacts.height },
            min_font_px: subFacts.min_font_px, min_font_pt_at_12_2cm: subFacts.min_font_px && +(subFacts.min_font_px * 345.8 / subFacts.width).toFixed(2),
            forbidden_text: subFacts.forbidden, url_hosts: subFacts.hosts }));
          console.log(`  strip ${i + 1}  ${subFacts.width}x${subFacts.height}`);
        }
        await context.close();
      }
    }
    // One full page per stage in record/, cut at FULL_PAGE_MAX.
    if (!ONLY && WIDTHS.includes(1000)) {
      const context = await browser.newContext({ viewport: { width: 1000, height: 1000 }, deviceScaleFactor: DPR, colorScheme: 'light', locale: 'en', reducedMotion: 'reduce' });
      const page = await context.newPage();
      for (const stage of ['acquisition', 'decomposition', 'role_selection', 'elicitation', 'normalization', 'verification', 'consolidation', 'base_review', 'deliberation', 'adjudication', 'baseline']) {
        await open(page, stage); await setDetails(page, []); await settle(page);
        const height = await page.evaluate(() => document.documentElement.scrollHeight);
        const file = path.join(OUT, 'record', `page-${stage}@1000.png`);
        await page.screenshot({ path: file, fullPage: true, clip: height > FULL_PAGE_MAX ? { x: 0, y: 0, width: 1000, height: FULL_PAGE_MAX } : undefined,
          animations: 'disabled', caret: 'hide', scale: 'device' });
        const text = await page.evaluate(() => document.body.innerText);
        const hits = FORBIDDEN.filter(re => re.test(text)).map(re => re.source);
        record({ id: `page-${stage}`, file: path.relative(OUT, file), stage, route: `#/workflow/${RUN}/${stage}`, run_id: RUN, case: null, workbench_commit: commit,
          policy_versions: policies, viewport_width: 1000, dpr: DPR, selector: 'full page (all details closed)', details_opened: [], css_injected: true, elements_hidden: HIDDEN,
          chosen_ids: {}, destination: 'record', shows: `The whole ${stage} page${height > FULL_PAGE_MAX ? `, cut at ${FULL_PAGE_MAX} of ${height} CSS px` : ''}.`,
          captured_at: new Date().toISOString(), sha256: sha256(file), page_css_px: height, forbidden_text: hits });
        console.log(`record/page-${stage}@1000.png  page ${height}px${hits.length ? '  FORBIDDEN ' + hits : ''}`);
      }
      await context.close();
    }
  } finally { await browser.close(); save(); }
}

// Contact sheet: every printable paper/ panel at its print width of 12.2 cm, at most two per A4 page, with its
// id and the print size of its smallest text, so legibility can be judged on paper. A panel taller than an
// appendix page is represented by its parts and strips.
async function sheet() {
  const manifest = JSON.parse(fs.readFileSync(path.join(OUT, 'manifest.json'), 'utf8'));
  const paper = manifest.shots.filter(s => s.viewport_width === PAPER_WIDTH);
  const splitIds = new Set(paper.filter(s => s.split_of).map(s => s.split_of));
  const units = paper.filter(s => s.split_of || s.strip_of || (!splitIds.has(s.id) && s.element_css_px.height <= APPENDIX_MAX + 10));
  const size = file => { const b = fs.readFileSync(path.join(OUT, file)); return { w: b.readUInt32BE(16), h: b.readUInt32BE(20) }; };
  const PAGE = 26.5;                 // cm of A4 height left inside 1.4 cm margins, less the captions
  const pages = [];
  for (const unit of units) {
    const { w, h } = size(unit.file); const cm = 12.2 * h / w;
    const last = pages[pages.length - 1];
    if (last && last.length < 2 && last.reduce((sum, u) => sum + u.cm + 1, 0) + cm + 1 <= PAGE) last.push({ ...unit, cm }); else pages.push([{ ...unit, cm }]);
  }
  const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const caption = u => `<b>${esc(u.file.replace(/^paper\//, ''))}</b> · ${u.crop_css_px ? `${u.crop_css_px.width}×${u.crop_css_px.height}` : `${u.element_css_px.width}×${u.element_css_px.height}`} CSS px · ` +
    `${u.cm.toFixed(1)} cm high at 12.2 cm · smallest text ${u.min_font_pt_at_12_2cm ?? '—'} pt · ${esc(u.destination)}`;
  const html = `<!doctype html><meta charset="utf-8"><style>
    @page { size: A4; margin: 1.4cm; } body { margin: 0; font: 8pt/1.3 Helvetica, Arial, sans-serif; color: #111; }
    .page { break-after: page; } .page:last-child { break-after: auto; } figure { margin: 0 0 0.6cm; break-inside: avoid; }
    img { display: block; width: 12.2cm; border: 0.2pt solid #bbb; } figcaption { margin-top: 0.15cm; width: 18cm; }
    h1 { font-size: 11pt; margin: 0 0 0.3cm; } p.lead { margin: 0 0 0.5cm; width: 18cm; }</style>
    <div class="page"><h1>Workbench screenshots · contact sheet</h1><p class="lead">Run ${esc(manifest.run_id)} · workbench ${esc(manifest.workbench_commit)} ·
    every paper/ panel at 12.2 cm wide (LNCS text width), as printed. ${units.length} panels on ${pages.length} pages; a panel taller than an appendix page
    (${APPENDIX_MAX} CSS px) is shown by its parts.</p></div>` +
    pages.map(p => `<div class="page">${p.map(u => `<figure><img src="${esc(path.join(OUT, u.file))}"><figcaption>${caption(u)}</figcaption></figure>`).join('')}</div>`).join('');
  const htmlFile = path.join(require('os').tmpdir(), `contact-sheet-${process.pid}.html`);
  fs.writeFileSync(htmlFile, html);
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage();
    await page.goto(`file://${htmlFile}`, { waitUntil: 'load' });
    await page.pdf({ path: path.join(OUT, 'contact-sheet.pdf'), format: 'A4', printBackground: true, preferCSSPageSize: true });
  } finally { await browser.close(); fs.rmSync(htmlFile, { force: true }); }
  console.log(`contact-sheet.pdf: ${units.length} panels on ${pages.length + 1} pages`);
}

(process.argv.includes('--sheet') ? sheet() : main()).catch(error => { console.error(error); process.exit(1); });
