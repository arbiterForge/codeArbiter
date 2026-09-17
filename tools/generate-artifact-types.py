#!/usr/bin/env python3
"""Regenerate typed Go views from the packaged closed artifact schemas."""
import argparse,json,re,subprocess,sys
from pathlib import Path
base=Path(__file__).resolve().parents[1]/'core/artifacts'
common=json.loads((base/'schemas/common.schema.json').read_text())
initialisms={'id':'ID','url':'URL','argv':'Argv','cwd':'CWD','sha256':'SHA256'}
def title(s):return ''.join(initialisms.get(x,x.title()) for x in s.split('_'))
def gotype(d):
 if '$ref' in d:return title(d['$ref'].split('/')[-1])
 t=d.get('type')
 if isinstance(t,list):return '*'+gotype({**d,'type':next(x for x in t if x!='null')})
 if 'anyOf' in d:
  real=[x for x in d['anyOf'] if x.get('type')!='null'];return '*'+gotype(real[0]) if len(real)==1 else 'json.RawMessage'
 if 'oneOf'in d:return 'json.RawMessage'
 if 'const'in d:return {str:'string',int:'int64',bool:'bool'}.get(type(d['const']),'json.RawMessage')
 if 'enum'in d:return 'string'
 if t=='string':return 'string'
 if t=='integer':return 'int64'
 if t=='boolean':return 'bool'
 if t=='array':return '[]'+gotype(d['items'])
 if t=='object':return 'map[string]json.RawMessage'
 return 'json.RawMessage'
lines=['// Code generated from the packaged, closed schemas. DO NOT EDIT.','package model','import "encoding/json"','type Block = json.RawMessage']
for name,d in common['$defs'].items():
 if name=='block':continue
 lines.append('type '+title(name)+' struct {')
 for key,prop in d['properties'].items():
  omit='' if key in d.get('required',[]) else ',omitempty'
  lines.append(f' {title(key)} {gotype(prop)} `json:"{key}{omit}"`')
 lines.append('}')
for kind in ('spec','plan'):
 s=json.loads((base/'schemas'/f'{kind}.schema.json').read_text())['properties']['normative']
 lines.append('type '+kind.title()+' struct {')
 for key,d in s['properties'].items():lines.append(f' {title(key)} {gotype(d)} `json:"{key}"`')
 lines.append('}')
parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');args=parser.parse_args()
rendered=subprocess.check_output(['gofmt'],input=('\n'.join(lines)+'\n').encode())
target=base/'internal/model/types_generated.go'
if args.check:
 if target.read_bytes()!=rendered:raise SystemExit('Generated model views are stale.')
 for kind in ('common','spec','plan'):
  if (base/'schemas'/f'{kind}.schema.json').read_bytes() != (base/'internal/schema'/f'{kind}.schema.json').read_bytes():raise SystemExit('Embedded schema drift: '+kind)
 print('Generated views and embedded schema copies match.')
else:
 target.write_bytes(rendered)
 for kind in ('common','spec','plan'):(base/'internal/schema'/f'{kind}.schema.json').write_bytes((base/'schemas'/f'{kind}.schema.json').read_bytes())
