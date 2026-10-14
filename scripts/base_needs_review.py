#!/usr/bin/env python3
"""Export a human catalogue worksheet and import explicit phrase corrections.

Reads only the selected registry and pinned base sources. It performs no review,
model inference or benchmark access. Rebuild the catalogue after importing.
"""
import argparse
import csv
import json
from pathlib import Path
import re
import build_base_needs as builder

COLUMNS=['entry id','class','property','draft phrase','definition','usage notes',
         'base obligation','corrected phrase','note']


def registry_path(profile_id, directory):
    if not re.fullmatch(r'dcat(?:-ap)?-\d+\.\d+\.\d+',profile_id):
        raise ValueError('Invalid base profile ID.')
    return directory/(profile_id+'.json')


def worksheet_row(entry):
    return dict(zip(COLUMNS,[entry['id'],entry['class'],entry['property'] or '',
        entry['need'],entry['definition'] or '',json.dumps(entry['usage_notes'],ensure_ascii=False),
        entry['base_obligation'] or '','','']))


def export_worksheet(profile_id, output, directory=None, input_dir=None):
    path=registry_path(profile_id,directory or builder.DIRECTORY)
    draft=json.loads(builder.build(path,input_dir or builder.INPUTS,with_review=False))
    with output.open('w',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=COLUMNS)
        writer.writeheader();writer.writerows(worksheet_row(entry) for entry in draft['entries'])
    return output


def import_review(profile_id, csv_path, reviewer, reviewed_at, directory=None, input_dir=None):
    path=registry_path(profile_id,directory or builder.DIRECTORY)
    draft=json.loads(builder.build(path,input_dir or builder.INPUTS,with_review=False))
    entries={e['id']:worksheet_row(e) for e in draft['entries']}
    corrections={};seen=set()
    with csv_path.open(encoding='utf-8-sig',newline='') as stream:
        reader=csv.DictReader(stream)
        if reader.fieldnames!=COLUMNS: raise ValueError('Worksheet columns must match the exported CSV.')
        for row in reader:
            if set(row)!=set(COLUMNS) or any(not isinstance(value,str) for value in row.values()):
                raise ValueError('Malformed worksheet row.')
            identifier=row['entry id']
            if identifier not in entries: raise ValueError('Unknown worksheet entry ID: '+identifier)
            if identifier in seen: raise ValueError('Repeated worksheet entry ID: '+identifier)
            seen.add(identifier)
            if any(row[field]!=entries[identifier][field] for field in COLUMNS[:-2]):
                raise ValueError(identifier+': worksheet draft fields changed or are stale; export a fresh worksheet.')
            if row['corrected phrase'].strip():
                corrections[identifier]={'need':row['corrected phrase'],'note':row['note']}
    if seen!=set(entries): raise ValueError('Worksheet must retain every exported entry exactly once.')
    review={'base_profile_id':profile_id,'draft_catalogue_hash':draft['catalogue_hash'],
        'status':'reviewed','reviewer':reviewer,'reviewed_at':reviewed_at,'phrase_corrections':corrections}
    raw=(json.dumps(review,indent=2,ensure_ascii=False)+'\n').encode()
    target=path.with_name(profile_id+'.needs-review.json')
    # Validate everything before replacing an existing human review file.
    builder.reviewed_catalogue(draft,json.loads(path.read_bytes()),review,target.name,raw)
    target.write_bytes(raw)
    return target


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='command',required=True)
    export=commands.add_parser('export');export.add_argument('profile_id');export.add_argument('--output',type=Path)
    importing=commands.add_parser('import');importing.add_argument('profile_id');importing.add_argument('csv',type=Path)
    importing.add_argument('--reviewer',required=True);importing.add_argument('--reviewed-at',required=True)
    args=parser.parse_args(argv)
    try:
        if args.command=='export':
            result=export_worksheet(args.profile_id,args.output or Path(args.profile_id+'.needs-review.csv'))
        else: result=import_review(args.profile_id,args.csv,args.reviewer,args.reviewed_at)
    except (OSError,ValueError,csv.Error) as exc: parser.error(str(exc))
    print(result)


if __name__=='__main__': main()
