import json
import os
from pathlib import Path
from types import SimpleNamespace as NS
import tempfile
import unittest
from unittest.mock import patch

from blackboard.codebase.components.ontology_context import OntologyContext, LLMSession, PROMPT_VERSION
from blackboard.codebase.components.attribute_mapper import AttributeMapper

ONTOLOGY = '''@prefix vcslam: <https://example.org/schema#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
vcslam:Shop a owl:Class .
vcslam:name a owl:DatatypeProperty; rdfs:range xsd:string .
'''


def response(value, cached=42):
    return NS(choices=[NS(message=NS(content=json.dumps(value)))],
              usage=NS(prompt_tokens=100, completion_tokens=10,
                       prompt_tokens_details=NS(cached_tokens=cached)))


class ContextTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)/'one.ttl'
        self.path.write_text(ONTOLOGY)
        self.context = OntologyContext.from_files([self.path])

    def test_single_file_content_is_preserved_and_sources_are_immutable(self):
        self.assertEqual(ONTOLOGY, self.context.text)
        with self.assertRaises(TypeError):
            self.context.sources[0]['name'] = 'changed'
        with self.assertRaises(TypeError):
            self.context.properties['fake'] = {}

    def test_multiple_files_have_stable_order_and_scoped_blank_nodes(self):
        self.path.write_text(ONTOLOGY + '\n_:b vcslam:name "one" .')
        two = self.path.with_name('two.ttl')
        two.write_text('@prefix other: <https://other.org/#> .\n_:b other:name "two" .')
        a = OntologyContext.from_files([self.path,two])
        b = OntologyContext.from_files([two,self.path])
        self.assertEqual(a.digest,b.digest)
        self.assertEqual(a.text,b.text)
        from rdflib import Graph, BNode
        graph = Graph().parse(data=a.text,format='turtle')
        self.assertEqual(2,len({s for s,_,_ in graph if isinstance(s,BNode)}))

    def test_conflicting_prefix_fails_before_inference(self):
        two = self.path.with_name('two.ttl')
        two.write_text('@prefix vcslam: <https://different.org/#> . vcslam:C vcslam:p "x" .')
        with self.assertRaisesRegex(ValueError,'Conflicting'):
            OntologyContext.from_files([self.path,two])

    def test_imports_are_not_downloaded(self):
        self.path.write_text(ONTOLOGY+'\nvcslam: a owl:Ontology; owl:imports <https://invalid.example/remote.ttl> .')
        with patch('urllib.request.urlopen',side_effect=AssertionError('No network allowed')):
            context=OntologyContext.from_files([self.path])
        self.assertEqual(1,len(context.classes))

    def test_shared_prefix_is_identical_across_samples_and_stages(self):
        sent=[]
        def create(**kwargs):
            sent.append(kwargs['messages']);return response([])
        session=LLMSession(NS(chat=NS(completions=NS(create=create))),'shared')
        original=[{'role':'user','content':'Different task content'}]
        for sid,stage in [('0001','generation'),('0001','documentation'),('0002','generation')]:
            session.complete(model='offline',messages=original,context=self.context,sample_id=sid,stage=stage)
        self.assertEqual(sent[0][0],sent[1][0]);self.assertEqual(sent[0][0],sent[2][0])
        self.assertNotEqual(sent[0][1],sent[2][1])
        self.assertEqual(1,len(original))
        self.assertEqual(42,session.requests[0]['cached_tokens'])
        self.assertNotIn('messages',session.requests[0])

    def test_only_original_ontology_stages_receive_full_context(self):
        sent=[]
        def create(**kwargs):
            sent.append(kwargs);return response([])
        session=LLMSession(NS(chat=NS(completions=NS(create=create))),'shared')
        messages=[{'role':'user','content':'Candidate votes and column values'}]
        for stage in ('generation','documentation','history','examples',
                      'name_proximity','selection','council_planning','council','mapping','unknown'):
            with self.subTest(stage=stage):
                session.complete(model='unchanged-model',messages=messages,context=self.context,
                                 sample_id='0001',stage=stage,attribute='name')
                call=sent[-1]
                full=stage in {'generation','documentation'}
                self.assertEqual('unchanged-model',call['model'])
                self.assertEqual(messages,call['messages'][-len(messages):])
                self.assertEqual(1 if full else 0,
                                 sum(m['content'].count(ONTOLOGY) for m in call['messages']))
                scope=call['messages'][1 if full else 0]['content']
                self.assertEqual(f'Dataset ID: 0001\nColumn ID: name\nStage: {stage}',scope)
                self.assertEqual(full,session.requests[-1]['ontology_prefix_attached'])
        self.assertEqual([{'role':'user','content':'Candidate votes and column values'}],messages)

    def test_legacy_messages_are_unchanged_and_missing_cache_usage_is_unknown(self):
        sent=[]
        def create(**kwargs):
            sent.append(kwargs['messages']);return NS(choices=response([]).choices)
        session=LLMSession(NS(chat=NS(completions=NS(create=create))),'legacy')
        messages=[{'role':'system','content':'Original role'},{'role':'user','content':ONTOLOGY}]
        session.complete(model='offline',messages=messages,context=self.context,sample_id='0001',stage='generation')
        self.assertEqual(messages,sent[0]);self.assertIsNone(session.requests[0]['cached_tokens'])

    def test_failure_records_metadata_and_propagates_without_retries(self):
        calls=[]
        def create(**kwargs):
            calls.append(kwargs);raise RuntimeError('Sensitive body not to be logged')
        session=LLMSession(NS(chat=NS(completions=NS(create=create))),'shared')
        with self.assertRaises(RuntimeError):
            session.complete(model='offline',messages=[],context=self.context,sample_id='0001',stage='generation')
        self.assertEqual(1,len(calls))
        self.assertEqual('RuntimeError',session.requests[0]['error_type'])
        self.assertNotIn('Sensitive',json.dumps(session.requests))

    def test_full_namespace_validation_rejects_unknown_or_wrong_terms(self):
        session=LLMSession(NS(),'shared')
        mapper=AttributeMapper('name',{'json_data':[{'name':'Shop A'}],'ontology':ONTOLOGY},
                               api_key='offline',llm_session=session,ontology_context=self.context)
        mapper.state['candidates']=[{'candidate':c,'reason':'Fixture'} for c in (
            'vcslam:Shop vcslam:name "name".',
            '<https://not-the-ontology.org/Shop> vcslam:name "name".',
            'unknown:Shop vcslam:name "name".',
            'vcslam:Shop vcslam:missing "name".',
            'vcslam:Shop vcslam:name "wrong-column".')]
        mapper.validate_mappings()
        self.assertEqual(1,len(mapper.state['validated_candidates']))

    def test_same_local_property_name_does_not_conflate_two_ontologies(self):
        two=self.path.with_name('two.ttl')
        two.write_text('''@prefix other: <https://other.org/#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
other:Shop a owl:Class . other:name a owl:DatatypeProperty; rdfs:range xsd:int .''')
        context=OntologyContext.from_files([self.path,two])
        mapper=AttributeMapper('name',{'json_data':[{'name':'Shop A'}],'ontology':context.text},
                               api_key='offline',llm_session=LLMSession(NS(),'shared'),ontology_context=context)
        mapper.state['candidates']=[{'candidate':c,'reason':'Fixture'} for c in (
            'vcslam:Shop vcslam:name "name".','other:Shop other:name "name".')]
        mapper.validate_mappings()
        self.assertEqual(1,len(mapper.state['validated_candidates']))
        self.assertTrue(mapper.state['validated_candidates'][0]['candidate'].startswith('vcslam:'))


class PipelineTests(unittest.TestCase):
    def test_real_pipeline_all_stages_and_council_in_both_modes(self):
        from blackboard.codebase.core import blackboard_semantic_mapping as pipeline
        for mode,separate in [('legacy',False),('shared',False),('shared',True)]:
            with self.subTest(mode=mode,separate=separate),tempfile.TemporaryDirectory() as tmp:
                base=Path(tmp);(base/'ontology').mkdir();(base/'ontology/ontology.ttl').write_text(ONTOLOGY)
                alternate=base/'ontology/alternate.ttl';alternate.write_text(ONTOLOGY+'\nvcslam:Shop rdfs:comment \"Alternate vocabulary version\" .')
                for sid,value in [('0001','Alpha Shop'),('0002','Beta Shop')]:
                    folder=base/sid;folder.mkdir()
                    (folder/f'{sid}_samples.json').write_text(json.dumps([{'name':value}]))
                    (folder/f'{sid}.txt').write_text('Name of the shop')
                    (folder/f'{sid}_mapped.json').write_text(json.dumps({'prefix':ONTOLOGY.split('vcslam:Shop')[0],
                        'mappings':{'name':{'mapping':'vcslam:Shop vcslam:name "name".'}}}))
                history=base/'0000';history.mkdir()
                (history/'0000_samples.json').write_text(json.dumps([{'name':'Historical Shop'}]))
                (history/'0000_mapped.json').write_text(json.dumps({'mappings':{
                    'name':{'mapping':'vcslam:Shop vcslam:name "name".'}}}))
                calls=[]
                def create(**kwargs):
                    messages=kwargs['messages'];calls.append(messages)
                    prompt=messages[-1]['content']
                    if 'You are a semantic mapping consistency checker' in prompt:
                        result={'d1':{'participants':[{'attribute':'name','role':'weak'}],
                                      'reason':'Offline council fixture','max_turns':2}}
                    elif 'You are participating in a semantic mapping' in prompt:
                        result={'attribute':'name','response':'Fixture','commands':['DiscussionState:End'],
                                'command_parameters':['']}
                    elif 'generate exactly' in prompt:
                        result=[{'object':'vcslam:Shop','relation':'vcslam:name','reason':'Offline fixture'}]*3
                    else:
                        result=[{'accepted':i==0,'score':3-i,'reason':'Offline fixture'} for i in range(3)]
                    return response(result)
                client=NS(chat=NS(completions=NS(create=create)))
                with patch.dict(os.environ,{'OPENAIKEY':'offline'}),patch.object(pipeline,'OpenAI',return_value=client),patch.object(OntologyContext,'from_files',wraps=OntologyContext.from_files) as load:
                    pipeline.run_pipeline(str(base),['0001','0002'],['0000'],str(base/'out'),False,context_mode=mode,sample_ontology_paths={'0002':[alternate]} if separate else None)
                self.assertEqual(2 if separate else 1,load.call_count)
                outputs=sorted((base/'out').glob('*/*/*_mapping_results.json'))
                self.assertEqual(2,len(outputs))
                for path in outputs:
                    raw=json.loads(path.read_text())
                    self.assertEqual(1,raw['evaluation']['after_reasoning']['hits@1'])
                    self.assertEqual('Acceptance',raw['discussions']['d1']['conclusion'])
                    records=raw['llm_context']['requests']
                    self.assertEqual({'generation','documentation','history','examples','name_proximity','selection','council_planning','council'},set(r['stage'] for r in records))
                    self.assertEqual({path.parent.name},set(r['sample_id'] for r in records))
                    if mode=='shared':
                        self.assertEqual(PROMPT_VERSION,raw['llm_context']['prompt_version'])
                        for record in records:
                            self.assertEqual(record['stage'] in {'generation','documentation'},
                                             record['ontology_prefix_attached'])
                if mode=='shared':
                    column_calls=[c for c in calls if c[0]['role']=='system']
                    compact_calls=[c for c in calls if c[0]['role']!='system']
                    council_calls=[c for c in compact_calls if c[0]['content'].splitlines()[-1]
                                   in {'Stage: council_planning','Stage: council'}]
                    self.assertTrue(council_calls)
                    self.assertEqual({'Stage: history','Stage: examples','Stage: name_proximity',
                                      'Stage: selection','Stage: council_planning','Stage: council'},
                                     {c[0]['content'].splitlines()[-1] for c in compact_calls})
                    self.assertTrue(all(ONTOLOGY not in m['content'] for c in compact_calls for m in c))
                    if separate:
                        by_sample={sid:[c[0] for c in column_calls if c[1]['content'].startswith('Dataset ID: '+sid)] for sid in ('0001','0002')}
                        self.assertNotEqual(by_sample['0001'][0],by_sample['0002'][0])
                        self.assertTrue(all(prefix==prefixes[0] for prefixes in by_sample.values() for prefix in prefixes))
                    else:
                        self.assertTrue(all(c[0]==column_calls[0][0] for c in column_calls))
                    self.assertTrue(all(sum(m['content'].count(ONTOLOGY) for m in c)==1 for c in column_calls))
                    for c in calls:
                        sid=c[1 if c[0]['role']=='system' else 0]['content'].splitlines()[0]
                        self.assertNotIn('Beta Shop' if sid.endswith('0001') else 'Alpha Shop',c[-1]['content'])

    def test_bad_sample_ontology_selection_fails_before_model_call(self):
        from blackboard.codebase.core import blackboard_semantic_mapping as pipeline
        with tempfile.TemporaryDirectory() as tmp,patch.object(pipeline,'OpenAI') as create:
            with self.assertRaisesRegex(ValueError,'unselected'):
                pipeline.run_pipeline(tmp,['0001'],[],tmp,False,sample_ontology_paths={'0002':['missing.ttl']})
            create.assert_not_called()


if __name__=='__main__':
    unittest.main()
