"""Trace source inventory to visible content; keep archival text out of speaker notes."""
import argparse
import hashlib
import json
from pathlib import Path
import re
from zipfile import ZipFile
from xml.etree import ElementTree as ET
from audit_template import audit, NS

STATUSES={'preserved','condensed','appendix','excluded'}
STATEMENTS={'verified','quote','source_report','analysis','question'}

def pointer(obj,path):
    if not isinstance(path,str) or not path.startswith('/') or '~' in path:raise ValueError('Invalid content pointer')
    for key in path[1:].split('/'):
        obj=obj[int(key)] if isinstance(obj,list) else obj[key]
    return obj

def strings(value):
    if isinstance(value,str):return value
    if isinstance(value,dict):return '\n'.join(strings(v) for v in value.values())
    if isinstance(value,list):return '\n'.join(strings(v) for v in value)
    return str(value)

def extract(pptx):
    pptx=Path(pptx);facts=[]
    with ZipFile(pptx) as z:
        for i,s in enumerate(audit(pptx)['slides'],1):
            root=ET.fromstring(z.read(s['part']))
            for j,p in enumerate(root.findall('.//a:p',NS),1):
                text=''.join(t.text or '' for t in p.findall('.//a:t',NS)).strip()
                if text:facts.append({'id':f's{i}-p{j}','text':text,'location':f'{pptx.name} · slide {i} · paragraph {j}','slide':i})
    return {'schema_version':'cgu-source-inventory/1','source_file':str(pptx.resolve()),'source_sha256':hashlib.sha256(pptx.read_bytes()).hexdigest(),'facts':facts}

def metric_text(m):
    return ''.join([m.get('sign',''),m.get('currency',''),m['number'],(' '+m['scale']) if m.get('scale') else '',m.get('suffix','')])

def validate_metric(m):
    required={'number','sign','currency','scale','suffix','unit','period','explanation','source_id','source_text','display'}
    if not isinstance(m,dict) or set(m)!=required:raise ValueError('Metric requires number/sign/currency/scale/suffix/unit/period/explanation/source_id/source_text/display')
    if not all(isinstance(v,str) for v in m.values()):raise ValueError('Metric fields must be strings')
    if not re.fullmatch(r'\d[\d ,\.]*',m['number']) or m['sign'] not in ('','−','-','+','~','≈') or m['suffix'] not in ('','+','%'):raise ValueError('Invalid numeric construction')
    if m['display']!=metric_text(m):raise ValueError('KPI display splits or changes number, sign, currency or scale')
    for field in ['unit','period','explanation','source_id','source_text']:
        if not m[field].strip():raise ValueError('KPI missing '+field)
    norm=lambda s:re.sub(r'\s+','',s).replace('−','-')
    if norm(m['display']) not in norm(m['source_text']):raise ValueError('KPI differs from source numeric construction')

def validate_editorial(deck):
    if deck.get('review_policy','legacy') not in ('legacy','strict'):raise ValueError('Unknown review policy')
    ids={s['id']:s for s in deck.get('sources',[])}
    for s in deck['slides']:
        if deck.get('review_policy')=='strict':
            for k in ['intent','takeaway','statement_type','selection_reason']:
                if not isinstance(s.get(k),str) or not s[k].strip():raise ValueError(s['id']+': missing '+k)
        if s.get('intent') and s['intent'] not in ('metrics','comparison','sequence','hierarchy','process','causality','decision','profile','reference'):raise ValueError('Unknown slide intent')
        if s.get('statement_type') and s['statement_type'] not in STATEMENTS:raise ValueError('Unknown statement type')
        if s.get('statement_type')=='verified' and not all(ids[r].get('verified_at') and ids[r].get('verification_url') for r in s.get('source_ids',[])):raise ValueError('Verified claim needs dated verification URLs')
        if deck.get('review_policy')=='strict' and s['kind'] in ('kpi','kpi_grid') and not s.get('metric_bindings'):raise ValueError('Strict KPI requires metric bindings')
        if s.get('image') and s['image']['source_id'] not in ids:raise ValueError('Unresolved image source')
        for b in s.get('metric_bindings',[]):
            if set(b)!={'pointer','metric'}:raise ValueError('Invalid metric binding')
            m=b['metric'];validate_metric(m)
            if m['source_id'] not in ids:raise ValueError('Unresolved KPI source')
            if pointer(s,b['pointer'])!=m['display']:raise ValueError('Visible KPI is not atomic')
            visible=strings({k:v for k,v in s.items() if k not in ('notes','metric_bindings','source_ids','object_sources')})
            if not all(m[k] in visible for k in ('unit','period','explanation')):raise ValueError('KPI context must be visible: unit, period, explanation')

def ledger_report(deck,base):
    cfg=deck.get('content_ledger')
    if not cfg:
        if deck.get('review_policy')=='strict':raise ValueError('Strict review requires content_ledger')
        return {'status':'not-requested','entries':[]}
    if not isinstance(cfg,dict) or set(cfg)!={'inventory','inventory_sha256','entries'} or not isinstance(cfg['entries'],list):raise ValueError('Invalid content_ledger structure')
    invpath=(Path(base)/cfg['inventory']).resolve();raw=invpath.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=cfg['inventory_sha256']:raise ValueError('Source inventory SHA mismatch')
    inv=json.loads(raw);facts={f['id']:f for f in inv['facts']};slides={s['id']:s for s in deck['slides']}
    if len(facts)!=len(inv['facts']):raise ValueError('Duplicate inventory id')
    source_text='\n'.join(f['text'] for f in inv['facts'])
    norm=lambda v:re.sub(r'\s+','',v).replace('−','-')
    for s in deck['slides']:
        for b in s.get('metric_bindings',[]):
            if norm(b['metric']['source_text']) not in norm(source_text):raise ValueError('KPI source text absent from inventory')
    entries=cfg['entries'];seen=set();report=[]
    for entry in entries:
        if not isinstance(entry,dict) or set(entry)!={'fact_id','status','reason','statement_type','targets'}:raise ValueError('Invalid ledger entry fields')
        fid=entry['fact_id']
        if fid not in facts or fid in seen:raise ValueError('Unknown or duplicate ledger fact '+fid)
        seen.add(fid)
        if entry['status'] not in STATUSES or not entry.get('reason','').strip():raise ValueError('Ledger needs disposition and reason')
        if entry.get('statement_type') not in STATEMENTS:raise ValueError('Ledger needs statement type')
        targets=entry.get('targets',[])
        if entry['status']!='excluded' and not targets:raise ValueError('Retained fact has no visible destination')
        if entry['status']=='excluded' and targets:raise ValueError('Excluded fact cannot have destinations')
        for t in targets:
            if not isinstance(t,dict) or set(t)!={'slide_id','pointer','text'} or t['slide_id'] not in slides:raise ValueError('Invalid ledger destination')
            s=slides[t['slide_id']];p=t['pointer']
            if p.split('/')[1] in ('notes','footer','source_ids','object_sources','metric_bindings','takeaway','selection_reason'):raise ValueError('Ledger destination must be visible content')
            actual=strings(pointer(s,p))
            if not t.get('text') or t['text'] not in actual:raise ValueError('Ledger target text missing')
            if entry['status'] in ('preserved','appendix') and facts[fid]['text'] not in actual:raise ValueError('Preserved source text changed')
            if entry['status']=='appendix' and s.get('section')!='appendix':raise ValueError('Appendix fact targets main deck')
        report.append(dict(entry,source_text=facts[fid]['text'],source_location=facts[fid]['location']))
    if seen!=set(facts):raise ValueError('Unaccounted source facts: '+', '.join(sorted(set(facts)-seen)))
    return {'status':'passed','inventory_sha256':cfg['inventory_sha256'],'source_sha256':inv.get('source_sha256'),'total':len(facts),'counts':{k:sum(e['status']==k for e in entries) for k in sorted(STATUSES)},'entries':report,'limitation':'Coverage is checked against inventoried paragraphs. Atomic fact segmentation and semantic equivalence require human/agent review.'}

def write_reports(deck,base,out):
    report=ledger_report(deck,base)
    (out/'qa/content-ledger.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    rows=['# Журнал сохранности содержания','',str(report.get('counts',{})),'']
    for e in report['entries']:rows+=['## '+e['fact_id']+' · '+e['status'],e['source_location'],e['source_text'],'Решение: '+e['reason'],'Назначение: '+', '.join(t['slide_id']+t['pointer'] for t in e.get('targets',[])),'']
    (out/'qa/content-ledger.md').write_text('\n'.join(rows),encoding='utf-8')
    if deck.get('content_ledger'):
        (out/'content/source-archive.json').write_bytes((Path(base)/deck['content_ledger']['inventory']).read_bytes())
    return report

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('pptx');ap.add_argument('--out',required=True);a=ap.parse_args()
    Path(a.out).write_text(json.dumps(extract(a.pptx),ensure_ascii=False,indent=2),encoding='utf-8')
