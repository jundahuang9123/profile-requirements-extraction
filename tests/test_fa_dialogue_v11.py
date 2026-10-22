"""Synthetic tests of the rule added in rq1-fa-dialogue-v11: no evaluation answers or live generation."""
from copy import deepcopy
import pytest
from test_routed_stakeholder_workflow import setup  # noqa: F401  (pytest fixture)
from test_base_review import prepared
from test_fa_workflow import Dialogue
from requirement_reuse_service.models import ArtifactPayload
from requirement_reuse_service.workflow import fa_discussion as fd, stakeholder_workflow as old
from requirement_reuse_service.workflow.evidence import register_source
from requirement_reuse_service.workflow.models import SourceRequest
from requirement_reuse_service.workflow.storage import digest

# Shaped like the PDF and HTML text of the live runs: wrapped lines, a word broken after its hyphen,
# one phrase twice.
UNIT=('3.   The data shall, to all possible extent, be made available in an accepted, platform-\n'
    '     independent, machine-readable format via accepted interfaces.\n'
    'If the distributions are accessible only through a landing page\n'
    '(i.e. direct download URLs are not known), then the landing page link SHOULD be duplicated.')


def cited(quote,content=UNIT):
    span=fd.folded_span(content,quote);return content[span[0]:span[1]] if span else None


def test_a_quotation_that_differs_only_in_whitespace_cites_the_exact_source_text():
    quote='accessible only through a landing page (i.e. direct download URLs are not known)'
    assert UNIT.count(quote)==0
    assert cited(quote)=='accessible only through a landing page\n(i.e. direct download URLs are not known)'
    # Surrounding whitespace in the quotation is not part of the span.
    assert cited('\t accessible only through a landing page ')=='accessible only through a landing page'


def test_a_non_breaking_hyphen_where_the_source_breaks_the_line_after_the_hyphen():
    quote='made available in an accepted, platform‑independent, machine‑readable format'
    assert cited(quote)=='made available in an accepted, platform-\n     independent, machine-readable format'
    assert cited('platform‐independent')=='platform-\n     independent'


@pytest.mark.parametrize('quote',[
    'The data shall, to all possible extent, ... machine-readable format',  # text left out
    'The data shall, to all possible extent, … machine-readable format',
    'The data shall be made available in an accepted format',  # wording changed
    'made available in an accepted, platform independent format',  # the hyphen dropped
    'landing page',  # occurs twice
    '', ' \n '])
def test_text_left_out_changed_or_repeated_is_never_matched(quote):
    assert fd.folded_span(UNIT,quote) is None


def test_a_quotation_that_fits_two_spans_once_folded_stays_unmatched():
    content='Find the licence for a\ndataset. Find the rights holder for a\n  dataset.'
    assert content.count('for a dataset')==0 and fd.folded_span(content,'for a dataset') is None
    assert cited('the licence for a dataset',content)=='the licence for a\ndataset'


def test_only_a_line_break_after_a_hyphen_joins_two_words():
    content='Describe data- and metadata-level rules. A long-\nterm plan.'
    assert fd.folded_span(content,'data-and metadata-level') is None
    assert cited('data- and metadata-level',content)=='data- and metadata-level'
    assert cited('A long-term plan.',content)=='A long-\nterm plan.'


def html_unit(store):
    """A source unit as the HTML and PDF adapters produce it: one passage whose lines keep their breaks."""
    source=register_source(store,SourceRequest(artifact=ArtifactPayload(name='wrapped.html',content='<p>'+UNIT+'</p>'),
        source_role='stakeholder_need'))
    units=[u for u in store.list('evidence') if u.get('source_version_id')==source['source_version_id']]
    assert len(units)==1 and 'landing page\n(i.e. direct' in units[0]['content']
    return units[0]


def applied_revision(setup,monkeypatch,policy):
    """fd.apply on one revise whose quotation reads a line break as a space; returns the outcome and the
    action as the strict verifier received it."""
    store,run,_=prepared(setup)
    if policy==fd.BASE_POLICY:run['request']['base_review']='expert_v1'
    assert fd.discussion_policy(run)==policy
    record=run['requirements'][0];case=fd.build_cases(store,run,[],Dialogue())[0]
    unit=html_unit(store);seen=[]
    def downstream(store,run,case,plan,checks,client,**kw):
        seen.append(deepcopy(plan.actions[0]));return [{'applied':False}],[],{}
    monkeypatch.setattr(old,'apply_plan',downstream)
    written='accessible only through a landing page (i.e. direct download URLs are not known)'
    plan=fd.Plan(actions=[{'action_id':'rev','action':'revise','parent_revision_ids':[record['revision_id']],
        'statement':'Users can find the access URL of a distribution.','rationale':'Cited wording.',
        'evidence_links':[{'evidence_id':unit['evidence_id'],'quote':written,'quote_start':7}]}],summary='Synthetic revision.')
    checks=fd.Checks(checks=[dict(action_id='rev',supported=True,fa_relevant=True,disposition_justified=True,
        preserves_distinctions=True,priority_supported=False,condition_supported=True,obligation_preserved=True,rationale='Checked.')])
    outcomes,_,_,_=fd.apply(store,run,case,plan,checks,None,{unit['evidence_id']})
    assert plan.actions[0].evidence_links[0].quote==written  # the plan keeps what the mediator wrote
    return outcomes[0],seen,unit,written


def test_v11_gives_the_verifier_the_exact_source_text_and_records_the_repair(setup,monkeypatch):
    outcome,seen,unit,written=applied_revision(setup,monkeypatch,fd.BASE_POLICY)
    link=seen[0].evidence_links[0];exact='accessible only through a landing page\n(i.e. direct download URLs are not known)'
    assert link.quote==exact and unit['content'][link.quote_start:link.quote_start+len(link.quote)]==exact
    assert outcome['citation_repairs']==[{'evidence_id':unit['evidence_id'],'from':7,'to':unit['content'].index(exact),'quote_hash':digest(exact),
        'written_quote_hash':digest(written),'method':fd.QUOTE_MATCH_POLICY}]
    assert 'validation_error' not in outcome


def test_the_legacy_protocol_keeps_the_exact_match(setup,monkeypatch):
    outcome,seen,_,_=applied_revision(setup,monkeypatch,fd.POLICY)
    assert seen==[] and outcome['validation_error']=='Ambiguous or unmatched source quotation.'
    assert outcome['status']=='blocked_change' and 'citation_repairs' not in outcome
