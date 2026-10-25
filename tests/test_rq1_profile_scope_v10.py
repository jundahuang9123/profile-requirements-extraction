"""rq1-profile-scope-v10 (Junda, 25 Oct): the record test names access conditions as information a dataset record
states. Whether access needs registration, an individual application or request, or a fee, and the conditions or
exceptions that restrict it, are not the "legal or administrative procedure" the prompt sends to none; the
procedure's steps, deadlines and duties still are. Runs under v9 and earlier keep the prompt they started with.
The model's reading shows only live; these tests check the prompt and which runs get it."""
import json
from test_resume_discussions import setup as needs_setup  # noqa: F401  (pytest fixture)
from test_rq1_profile_scope import variants
from test_scope_contract_v1_normalisation import BothTests, fa_run
from test_scope_contract_v1_discussion import RULE
from requirement_reuse_service.workflow import needs


def test_the_record_test_names_access_conditions_a_dataset_record_states():
    prompt = ' '.join(needs.SCOPE_SYSTEM.split())
    assert ('whether access to a dataset requires registration, an individual application or request, or a fee, and the '
            'conditions or exceptions under which access to it is restricted, are access conditions its record states') in prompt
    assert 'only the steps, deadlines and duties of such a procedure are none' in prompt
    # The rest of the prompt is unchanged: rules, procedures and statements about the source still have no record.
    assert 'how data must be processed, for a legal or administrative procedure' in prompt
    assert ' '.join(needs.SCOPE_SYSTEM_V9.split()) == prompt.replace(' '.join(needs.SCOPE_ACCESS_CONDITIONS.split()) + ' ', '')


def test_runs_under_earlier_policies_keep_their_prompt():
    # Every earlier label, not only the ones still in use: a base-review trial derived from a v5 run keeps v5.
    for version in range(1, 10):
        assert needs.scope_system(f'rq1-profile-scope-v{version}') == needs.SCOPE_SYSTEM_V9
    assert needs.scope_system('rq1-profile-scope-v10') == needs.SCOPE_SYSTEM
    assert needs.POLICIES['profile_scope'] == 'rq1-profile-scope-v10'


def test_the_record_test_sends_each_run_the_prompt_of_its_policy(needs_setup):
    # The rule fails, so it is judged again alone: both judgements must get the policy's prompt.
    statements = {'need-access': 'Users can know whether access to a dataset requires registration.', 'need-rule': RULE}
    store, run, _, made = variants(needs_setup, statements)
    run = fa_run(store, run)
    class Systems(BothTests):
        def generate_structured(self, **kwargs):
            if kwargs['output_model'].__name__ == 'ProfileScope':
                self.systems.append((sorted(json.loads(kwargs['user'])['needs']), kwargs.get('system', '')))
            return super().generate_structured(**kwargs)
    for policy, prompt in (('rq1-profile-scope-v10', needs.SCOPE_SYSTEM), ('rq1-profile-scope-v9', needs.SCOPE_SYSTEM_V9),
                           ('rq1-profile-scope-v8', needs.SCOPE_SYSTEM_V9)):
        client = Systems(statements); client.systems = []
        view = {**run, 'needs_policies': {**(run.get('needs_policies') or {}), 'profile_scope': policy}}
        verdicts = needs.record_scope_verdicts(store, view, made, client)
        assert client.systems == [(['need-access', 'need-rule'], prompt), (['need-rule'], prompt)]
        assert verdicts['need-rule'][0]['confirmation']['outcome'] == 'confirmed' and not verdicts['need-access'][1]
