#!/usr/bin/env python3
"""Build draft base needs offline from registry-pinned official source files.

No benchmark sources or reference requirements are read. Definitions are copied,
never generated. Bundled prose inputs retain the registry's original checksums.
"""
import argparse
from copy import deepcopy
from datetime import date
import hashlib
import json
from pathlib import Path
import re
import sys
from lxml import etree, html
from build_base_profile import compact, CLASS_NAMES, PREFIXES, _terms

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'requirement-reuse-service'))
from requirement_reuse_service.workflow.terms import detect_terms
DIRECTORY = ROOT / 'requirement-reuse-service/config/base_profiles'
INPUTS = DIRECTORY / 'source-inputs'
POLICY = 'rq1-base-needs-catalogue-v2'
RDF = '{http://www.w3.org/1999/02/22-rdf-syntax-ns#}'
RDFS = '{http://www.w3.org/2000/01/rdf-schema#}'
VANN = '{http://purl.org/vocab/vann/}'


def words(value):
    return re.sub(r'([a-z])([A-Z])', r'\1 \2', value.split(':')[-1]).lower().strip()


def clean_label(value):
    value = re.sub(r'^.*?\s+-\s*', '', value.strip())
    class_names = '|'.join(re.escape(name) for name in ['data catalogue', *CLASS_NAMES])
    value = re.sub(r'^(?:'+class_names+r')\s*-\s*', '', value, flags=re.I)
    if not value or value.endswith('-'):
        return None
    return words(value)


def text(element):
    return ' '.join(''.join(element.itertext()).split())


def source_descriptions(profile, input_dir):
    """Index separate RDF descriptions before RDF merging loses class context."""
    result = {}
    aliases = {re.sub(r'\W', '', name): cls for name, cls in CLASS_NAMES.items()}
    aliases.update({re.sub(r'\W', '', words(cls)): cls for cls in profile['classes']})
    aliases['datacatalogue'] = 'dcat:Catalog'
    def put(cls, prop, label, definitions, notes, relative, anchor, index=None):
        if index is None and (cls not in profile['classes'] or (prop is not None and prop not in profile['classes'][cls])):
            return
        row = (result if index is None else index).setdefault((cls, prop), {'labels': [], 'definitions': [], 'usage_notes': [], 'sources': []})
        for field, values in [('labels', [label]), ('definitions', definitions), ('usage_notes', notes)]:
            for value in values:
                if value and value not in row[field]: row[field].append(value)
        pin = {'file': relative, 'sha256': profile['source']['files'][relative], 'anchor': anchor}
        if pin not in row['sources']: row['sources'].append(pin)
    for relative, fingerprint in sorted(profile['source']['files'].items()):
        # SHACL and DOCX remain registry inputs; prose is read from RDF and HTML.
        if not relative.endswith(('.rdf', '.html')): continue
        path = input_dir / relative
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != fingerprint:
            raise ValueError(f'Pinned base prose checksum mismatch: {relative}')
        if relative.endswith('.rdf'):
            root = etree.fromstring(raw, parser=etree.XMLParser(resolve_entities=False, no_network=True))
            for index, element in enumerate(root,1):
                uri = element.get(RDF + 'about')
                if not uri: continue
                prop = compact(uri)
                labels = [text(e) for e in element.findall(RDFS + 'label')]
                definitions = [text(e) for e in element.findall(RDFS + 'comment')]
                notes = [text(e) for e in element.findall(VANN + 'usageNote')]
                anchors = [a.get(RDF+'resource') or '' for a in element.findall(RDFS+'isDefinedBy')]
                for href in anchors or [f'rdf:Description[{index}]']:
                    fragment = href.split('#')[-1]
                    cls = None
                    if fragment.startswith('Property:'):
                        local = fragment.split(':', 1)[1].lower()
                        matches = [(len(name), value) for name, value in aliases.items()
                                   if any(re.sub(r'\W', '', '_'.join(local.split('_')[:i])) == name
                                          for i in range(1, len(local.split('_'))))]
                        if matches: cls = max(matches)[1]
                    if not cls:
                        matching = [aliases.get(re.sub(r'\W', '', label.split('-', 1)[0].lower()))
                                    for label in labels if '-' in label]
                        cls = next((value for value in matching if value), None)
                    if cls:
                        put(cls, prop, next(iter(labels), None), definitions, notes, relative, href)
        else:
            doc = html.fromstring(raw, parser=html.HTMLParser(no_network=True))
            if relative.startswith('releases/'):
                for row in doc.xpath('//tr'):
                    cells = row.xpath('./td')
                    if len(cells) != 5 or text(cells[2]).lower() not in {'mandatory','recommended','optional'}: continue
                    cls, prop = compact(text(cells[1])), compact(text(cells[4]))
                    links = cells[3].xpath('.//a/@href')
                    if len(links) != 1: raise ValueError('Ambiguous base property link')
                    anchor = links[0].lstrip('#')
                    detail = doc.xpath('//*[@id=$anchor]', anchor=anchor)
                    if len(detail) != 1: raise ValueError('Missing base property description')
                    definitions = [text(e) for e in detail[0].xpath('./td[@property="rdfs:comment"]')]
                    notes = [text(e) for e in detail[0].xpath('./td[@property="skos:scopeNote"]')]
                    put(cls, prop, text(cells[3]), definitions, notes, relative, anchor)
            else:
                contexts, parents = {}, {}
                for section in doc.xpath('//section[starts-with(@id,"Class:")]'):
                    tables = section.xpath('./table')
                    if not tables: continue
                    def fields(table):
                        values = {}
                        for row in table.xpath('.//tr'):
                            cells = row.xpath('./th | ./td')
                            if len(cells) >= 2: values[text(cells[0]).rstrip(':').lower()] = text(cells[1])
                        return values
                    values = fields(tables[0])
                    cls = compact(values.get('rdf class',''))
                    parents[cls] = set()
                    for row in tables[0].xpath('.//tr'):
                        cells = row.xpath('./th | ./td')
                        if len(cells)>=2 and text(cells[0]).rstrip(':').lower()=='sub-class of':
                            parents[cls].update(_terms(cells[1]))
                    put(cls, None, words(cls), [values.get('definition','')], [values.get('usage note','')], relative, section.get('id'), contexts)
                    for subsection in section.xpath('./section[starts-with(@id,"Property:")]'):
                        tables = subsection.xpath('./table')
                        if not tables: continue
                        values = fields(tables[0]); prop = compact(values.get('rdf property',''))
                        heading = subsection.xpath('./h3 | ./h4 | ./h5')
                        label = re.sub(r'^Property:\s*', '', text(heading[0])) if heading else None
                        put(cls, prop, label, [values.get('definition','')], [values.get('usage note','')], relative, subsection.get('id'), contexts)
                result.update({key:row for key,row in contexts.items() if key[0] in profile['classes']
                               and (key[1] is None or key[1] in profile['classes'][key[0]])})
                # Preserve the existing unique-context label fallback before
                # adding inherited prose entries changes the index's cardinality.
                for cls, props in profile['classes'].items():
                    for prop in props:
                        if (cls,prop) not in result:
                            originals = [row for (context,p),row in result.items() if p==prop]
                            if len(originals)==1: result[(cls,prop)] = originals[0]
                def resource_ancestor(cls, seen=frozenset()):
                    if cls in seen: raise ValueError('Cycle in pinned W3C class inheritance.')
                    return cls=='dcat:Resource' or any(resource_ancestor(p, seen|{cls}) for p in parents.get(cls, set()))
                def inherited_description(cls, prop, seen=frozenset()):
                    if cls in seen: raise ValueError('Cycle in pinned W3C class inheritance.')
                    row=contexts.get((cls,prop))
                    if row and row['definitions']: return cls,row
                    for parent in sorted(parents.get(cls, set())):
                        found=inherited_description(parent, prop, seen|{cls})
                        if found: return found
                    return None
                # Follow declared ancestry in this exact pinned file. Preserve a
                # nearer override; never invent or import an inherited definition.
                for cls, props in profile['classes'].items():
                    if not resource_ancestor(cls): continue
                    for prop in props:
                        current=result.get((cls,prop))
                        direct=contexts.get((cls,prop))
                        if direct and direct['definitions']: continue
                        found=inherited_description(cls,prop)
                        if not found: continue
                        context, original=found
                        inherited=deepcopy(current or original)
                        # This repair copies prose, not phrasing: keep the target
                        # class's existing labels and registry-derived need text.
                        inherited['labels']=deepcopy((current or {}).get('labels',[]))
                        inherited['definitions']=deepcopy(original['definitions'])
                        inherited['sources']=[*deepcopy((direct or {}).get('sources',[])),
                            *[{**pin,'inherited_from':context} for pin in original['sources']]]
                        if not inherited['usage_notes']: inherited['usage_notes']=deepcopy(original['usage_notes'])
                        result[(cls,prop)]=inherited
    return result


def catalogue_hash(body):
    return hashlib.sha256(json.dumps({k:v for k,v in body.items() if k!='catalogue_hash'},
        sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()


def reviewed_catalogue(draft, profile, review, review_file, raw):
    """Apply only explicit human phrases; bind review to the unchanged draft."""
    required={'base_profile_id','draft_catalogue_hash','status','reviewer','reviewed_at','phrase_corrections'}
    if not isinstance(review,dict) or set(review)!=required:
        raise ValueError('Catalogue review must contain exactly: '+', '.join(sorted(required)))
    if review['base_profile_id']!=draft['base_profile_id']:
        raise ValueError('Catalogue review base_profile_id differs from the selected registry.')
    if review['draft_catalogue_hash']!=draft['catalogue_hash']:
        raise ValueError('Catalogue review draft_catalogue_hash is stale; export and review the new draft.')
    if review['status']!='reviewed' or not isinstance(review['reviewer'],str) or not review['reviewer'].strip():
        raise ValueError('Catalogue review requires status reviewed and a nonempty reviewer.')
    try:
        if not isinstance(review['reviewed_at'],str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',review['reviewed_at']):
            raise ValueError()
        date.fromisoformat(review['reviewed_at'])
    except ValueError as exc: raise ValueError('Catalogue reviewed_at must be a valid YYYY-MM-DD date.') from exc
    corrections=review['phrase_corrections']
    if not isinstance(corrections,dict): raise ValueError('phrase_corrections must be an object keyed by entry ID.')
    result=deepcopy(draft);entries={e['id']:e for e in result['entries']}
    for identifier,correction in corrections.items():
        if identifier not in entries: raise ValueError('Unknown catalogue review entry ID: '+identifier)
        if not isinstance(correction,dict) or set(correction)!={'need','note'}:
            raise ValueError(identifier+': a phrase correction needs exactly need and note.')
        phrase=correction['need']
        if not isinstance(phrase,str) or not phrase.strip(): raise ValueError(identifier+': corrected phrase must not be empty.')
        if not isinstance(correction['note'],str): raise ValueError(identifier+': review note must be text.')
        terms=detect_terms(phrase,profile)
        if terms: raise ValueError(identifier+': corrected phrase contains vocabulary terms: '+', '.join(terms))
        entry=entries[identifier]
        entry.update(need=phrase,need_draft=entry['need'],review_note=correction['note'])
    seen=set()
    for entry in result['entries']:
        key=entry['class'],' '.join(entry['need'].split()).casefold()
        if key in seen: raise ValueError('Duplicate reviewed phrase within class '+entry['class']+': '+entry['need'])
        seen.add(key)
    result['review']={k:review[k] for k in ('status','reviewer','reviewed_at')}
    result['review'].update(review_file=review_file,review_file_sha256=hashlib.sha256(raw).hexdigest(),corrected_count=len(corrections))
    result['catalogue_hash']=catalogue_hash(result)
    return result


def build(path, input_dir=INPUTS, with_review=True):
    raw = path.read_bytes(); profile = json.loads(raw); entries = []
    descriptions = source_descriptions(profile, input_dir)
    for cls, properties in sorted(profile['classes'].items()):
        resource = words(cls); article = 'an' if resource[0] in 'aeiou' else 'a'
        info = descriptions.get((cls,None), {})
        entries.append({'id':'base-'+hashlib.sha256(cls.encode()).hexdigest()[:20],
            'need':f'Identify and describe {article} {resource}.','class':cls,'property':None,'rq2_term':cls,
            'label':resource,'definition':'\n'.join(info.get('definitions',[])) or None,
            'usage_notes':info.get('usage_notes',[]),'definition_sources':info.get('sources',[]), 'base_obligation':None})
        phrases = set()
        for prop, entry in sorted(properties.items()):
            info = descriptions.get((cls,prop),{})
            same_class = [s for s in entry.get('labels',[]) if ' - ' in s and
                          re.sub(r'\W','',s.split(' - ',1)[0].lower()) in
                          {re.sub(r'\W','',resource), *(re.sub(r'\W','',k) for k,v in CLASS_NAMES.items() if v==cls)}]
            alternatives = [s for s in entry.get('labels',[]) if ' - ' not in s]
            label = next((clean_label(s) for s in [*info.get('labels',[]),*same_class,*alternatives,words(prop)] if clean_label(s)),None)
            if not label: raise ValueError(f'No usable label: {cls}/{prop}')
            phrase = f'Find the {label} of {article} {resource}.'
            if phrase in phrases: raise ValueError(f'Duplicate base need phrase in {cls}: {phrase}')
            phrases.add(phrase)
            entries.append({'id':'base-'+hashlib.sha256((cls+'/'+prop).encode()).hexdigest()[:20],
                'need':phrase,'class':cls,'property':prop,'rq2_term':prop,'label':label,
                'definition':'\n'.join(info.get('definitions',[])) or None,'usage_notes':info.get('usage_notes',[]),
                'definition_sources':info.get('sources',[]),'base_obligation':entry.get('obligation'),'vocabulary':entry.get('vocabulary')})
    result={'base_profile_id':profile['id'],'base_profile_sha256':hashlib.sha256(raw).hexdigest(),
        'policy_version':POLICY,'phrasing':'deterministic labels; verbatim pinned definitions and usage notes',
        'review':{'status':'unreviewed','reviewer':None,'reviewed_at':None},'entries':entries}
    result['catalogue_hash']=catalogue_hash(result)
    review_path=path.with_name(path.stem+'.needs-review.json')
    if with_review and review_path.exists():
        review_raw=review_path.read_bytes()
        result=reviewed_catalogue(result,profile,json.loads(review_raw),review_path.name,review_raw)
    return json.dumps(result,indent=2,ensure_ascii=False)+'\n'


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--check',action='store_true');parser.add_argument('--input-dir',type=Path,default=INPUTS);args=parser.parse_args()
    for path in sorted(DIRECTORY.glob('*.json')):
        if not re.fullmatch(r'dcat(?:-ap)?-\d+\.\d+\.\d+\.json',path.name): continue
        target=path.with_name(path.stem+'.needs.json');value=build(path,args.input_dir)
        if args.check:
            if not target.exists() or target.read_text()!=value: parser.error(f'Stale base needs catalogue: {target.name}')
        else: target.write_text(value)


if __name__=='__main__': main()
