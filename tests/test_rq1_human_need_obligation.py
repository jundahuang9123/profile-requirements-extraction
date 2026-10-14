import pytest
from test_resume_discussions import setup
from test_rq1_need_grouping import need_inputs
from requirement_reuse_service.workflow import engine,needs


@pytest.mark.parametrize('word',['must','SHALL','Should'])
def test_human_edits_and_acceptance_cannot_add_obligation_words(setup,word):
    store,run,records=need_inputs(setup)
    record=records[0].model_copy(deep=True)
    record.normalized_statement=f'Users {word} identify a dataset title.'
    with pytest.raises(ValueError,match='neutral need wording'):
        needs.prepare_human_need(store,run,record,records)
    record.need_statement=record.normalized_statement
    with pytest.raises(ValueError,match='neutral need wording'):
        engine.require_need_form(run,record)
