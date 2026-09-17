"""Strict read-only reference primitives; not a production storage/authority engine."""
from __future__ import annotations
import hashlib
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
MAX_FILE_BYTES=8*1024*1024
MAX_DEPTH=64
MAX_SYMBOLS=8192
SAFE_INTEGER=9007199254740991
ID=re.compile(r'[A-Z][A-Z0-9-]{1,79}')

def _pairs(items):
    out={}
    for key,value in items:
        if key in out: raise ValueError(f'DUPLICATE_KEY: {key!r}')
        out[key]=value
    return out

def _reject_number(value): raise ValueError(f'INVALID_NUMBER: {value}')

def _depth_check(text):
    """Bound nesting before json.loads allocates nested containers."""
    depth=0;quoted=False;escape=False
    for ch in text:
        if quoted:
            if escape: escape=False
            elif ch=='\\': escape=True
            elif ch=='"': quoted=False
        elif ch=='"':quoted=True
        elif ch in '{[':
            depth+=1
            if depth>MAX_DEPTH:raise ValueError('MAX_DEPTH')
        elif ch in '}]':depth-=1

def decode_json(text):
    _depth_check(text)
    value=json.loads(text,object_pairs_hook=_pairs,parse_float=_reject_number,parse_constant=_reject_number)
    canonical(value)
    return value

def canonical(value:Any)->bytes:
    """RFC 8785 string/boolean/null/safe-integer subset; NOT full numeric JCS."""
    def emit(v,depth=0):
        if depth>MAX_DEPTH:raise ValueError('MAX_DEPTH')
        if v is None:return 'null'
        if v is True:return 'true'
        if v is False:return 'false'
        if isinstance(v,int):
            if abs(v)>SAFE_INTEGER:raise ValueError('INVALID_NUMBER')
            return str(v)
        if isinstance(v,str):
            v.encode('utf-8',errors='strict')
            return json.dumps(v,ensure_ascii=False,separators=(',',':'))
        if isinstance(v,list):return '['+','.join(emit(i,depth+1) for i in v)+']'
        if isinstance(v,dict):
            if not all(isinstance(k,str) for k in v):raise ValueError('NON_STRING_KEY')
            return '{'+','.join(emit(k,depth+1)+':'+emit(v[k],depth+1) for k in sorted(v,key=lambda s:s.encode('utf-16be')))+'}'
        raise ValueError(f'UNSUPPORTED_VALUE: {type(v).__name__}')
    return emit(value).encode('utf-8')

def sha(value):return hashlib.sha256(canonical(value)).hexdigest()
def normative_projection(model):return {k:model[k] for k in ('format_version','kind','schema_version','artifact_id','normative')}
def digests(model):return sha(normative_projection(model)),sha({k:v for k,v in model.items() if k!='integrity'})

def records(model):
    out={}
    def visit(v):
        if isinstance(v,dict):
            if 'id' in v:
                ident=v['id']
                if not isinstance(ident,str) or not ID.fullmatch(ident):raise ValueError(f'INVALID_ID: {ident!r}')
                if ident in out:raise ValueError(f'DUPLICATE_ID: {ident}')
                out[ident]=v
                if len(out)>MAX_SYMBOLS:raise ValueError('MAX_SYMBOLS')
            for item in v.values():visit(item)
        elif isinstance(v,list):
            for item in v:visit(item)
    visit(model['normative'])
    return out

class ModelParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.models=[];self.capture=False;self.buf=[]
        self.symbols=[];self.markers=[];self.executable_scripts=0;self.ids=[];self.links=[]
    def handle_starttag(self,tag,attrs):
        if len({k for k,v in attrs})!=len(attrs):raise ValueError('DUPLICATE_HTML_ATTRIBUTE')
        a=dict(attrs)
        if 'id' in a:
            if a['id'] in self.ids:raise ValueError('DUPLICATE_DOM_ID: '+a['id'])
            self.ids.append(a['id'])
        if 'data-ca-symbol' in a:
            if a.get('id')!=a['data-ca-symbol']:raise ValueError('SYMBOL_ELEMENT_MISMATCH')
            self.symbols.append(a['data-ca-symbol'])
        if tag=='a' and 'href' in a:self.links.append(a['href'])
        if tag=='script':
            if a.get('id')=='ca-artifact-model' and a.get('type')=='application/json' and 'src' not in a:
                if self.capture:raise ValueError('NESTED_MODEL')
                self.capture=True;self.buf=[]
            else:self.executable_scripts+=1
    def handle_startendtag(self,tag,attrs):
        if tag=='script':raise ValueError('INVALID_SELF_CLOSING_MODEL')
        self.handle_starttag(tag,attrs)
    def handle_endtag(self,tag):
        if tag=='script' and self.capture:self.models.append(''.join(self.buf));self.capture=False
    def handle_data(self,data):
        if self.capture:self.buf.append(data)
    def handle_comment(self,data):
        m=re.fullmatch(r'\s*CA:(BEGIN|END):([A-Z][A-Z0-9-]{1,79})\s*',data)
        if m:self.markers.append(m.groups())
        elif data.strip().startswith('CA:'):raise ValueError('MALFORMED_MARKER')
    def check_markers(self):
        stack=[];begins=[]
        for kind,ident in self.markers:
            if kind=='BEGIN':stack.append(ident);begins.append(ident)
            elif not stack or stack.pop()!=ident:raise ValueError('CROSSED_MARKER: '+ident)
        if stack:raise ValueError('UNCLOSED_MARKER')
        if len(set(begins))!=len(begins):raise ValueError('DUPLICATE_MARKER')
        return begins

def load(path:Path):
    """Parse only; normal user commands must call verified_load below."""
    with path.open('rb') as f:raw=f.read(MAX_FILE_BYTES+1)
    if len(raw)>MAX_FILE_BYTES:raise ValueError('FILE_TOO_LARGE')
    text=raw.decode('utf-8',errors='strict')
    parser=ModelParser();parser.feed(text);parser.close()
    if len(parser.models)!=1 or parser.capture:raise ValueError('MODEL_COUNT')
    return decode_json(parser.models[0]),text,parser

def verified_load(path:Path,root:Path|None=None):
    """Validate schema, integrity and view before returning a normal read."""
    from reference_validation import structural_errors,semantic_errors
    from render_reference import render
    model,text,parser=load(path)
    root=root or Path(__file__).resolve().parents[1]
    if model.get('presentation',{}).get('renderer')!='codearbiter-reference-html/0.2.0':raise ValueError('UNSUPPORTED_RENDERER')
    errors=structural_errors(model,root)
    if errors:raise ValueError('INVALID_MODEL: '+'; '.join(errors[:12]))
    errors=semantic_errors(model)
    if errors:raise ValueError('INVALID_MODEL: '+'; '.join(errors[:12]))
    idx=records(model);begins=parser.check_markers()
    if set(idx)!=set(begins) or len(idx)!=len(begins):raise ValueError('MARKER_MODEL_MISMATCH')
    if sorted(parser.symbols)!=sorted(idx):raise ValueError('DOM_MODEL_MISMATCH')
    if parser.executable_scripts:raise ValueError('EXECUTABLE_SCRIPT')
    nh,mh=digests(model)
    if (nh,mh)!=(model['integrity']['normative_sha256'],model['integrity']['model_sha256']):raise ValueError('DIGEST_MISMATCH')
    if len(idx)!=model['integrity']['symbol_count']:raise ValueError('SYMBOL_COUNT')
    css=(root/'assets/artifact.css').read_text(encoding='utf-8')
    if hashlib.sha256(css.encode()).hexdigest()!=model['presentation']['stylesheet_sha256']:raise ValueError('STYLESHEET_MISMATCH')
    if render(model,css)!=text:raise ValueError('RENDER_DRIFT')
    return model,text,parser
