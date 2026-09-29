"""Renderer-independent content, evidence and KPI integrity contracts.

Checks addressability and exact supplied evidence, never factual truth.
"""
import json
from pathlib import Path
from content_review import pointer, strings

KINDS={'claim','fact','kpi','assumption','quotation','interpretation','speaker_note','appendix_candidate','chart_series','categories','node','relationship'}
CLAIMS={'fact','assumption','quotation','interpretation','source_report'}
KPI_FIELDS=('value','unit','currency','sign','period','comparison_base')
ROOT_FIELDS={'content_model','readiness_policy'}
SLIDE_FIELDS={'model_bindings','purpose','relationship','emphasis','information_density','narrative_role','visual_asset','next_layout','note_ids'}


def sources_index(sources):
    if not isinstance(sources,list):raise ValueError('sources must be an array')
    result={}
    for source in sources:
        if not isinstance(source,dict) or not all(isinstance(source.get(k),str) and source[k].strip() for k in ('id','location')):raise ValueError('Source needs id and location')
        if source['id'] in result:raise ValueError('Duplicate source id')
        if source.get('status','source') not in ('source','calculated','assumption','conflict'):raise ValueError('Unknown source status')
        if source.get('status')=='calculated' and not source.get('formula'):raise ValueError('Calculated source needs formula')
        result[source['id']]=source
    return result


def references(refs,sources,required=True):
    if not isinstance(refs,list) or (required and not refs) or any(not isinstance(r,str) or r not in sources for r in refs):raise ValueError('Unresolved source reference')
    if any(sources[r].get('status')=='conflict' for r in refs):raise ValueError('Unresolved conflicting evidence')


def validate_model(model):
    if not isinstance(model,dict) or model.get('schema_version')!='cgu-content/1':raise ValueError('Expected cgu-content/1')
    if set(model)-{'schema_version','sources','items'}:raise ValueError('Unknown Content Model field')
    sources=sources_index(model.get('sources',[]));items=model.get('items')
    if not isinstance(items,list):raise ValueError('Content items must be an array')
    result={}
    for item in items:
        if not isinstance(item,dict) or not isinstance(item.get('id'),str) or not item['id'].strip() or item['id'] in result:raise ValueError('Content item requires unique id')
        if item.get('kind') not in KINDS or item.get('claim_type') not in CLAIMS:raise ValueError('Unknown content kind or claim_type')
        if 'value' not in item:raise ValueError('Content item needs value')
        references(item.get('source_ids',[]),sources,item['claim_type'] not in ('assumption','interpretation'))
        if item['claim_type'] in ('assumption','interpretation') and not item.get('rationale'):raise ValueError('Editorial content needs rationale')
        for evidence in item.get('evidence',[]):
            if not isinstance(evidence,dict) or set(evidence)!={'source_id','pointer','value'} or evidence['source_id'] not in item.get('source_ids',[]):raise ValueError('Invalid exact evidence')
            try:actual=pointer(sources[evidence['source_id']],evidence['pointer'])
            except (KeyError,IndexError,TypeError,ValueError):raise ValueError('Evidence location missing')
            if actual!=evidence['value']:raise ValueError('Evidence differs from supplied source snapshot')
        if item['kind']=='kpi':
            kpi=item.get('kpi');origin=item.get('source_components')
            if not isinstance(kpi,dict) or set(kpi)!=set(KPI_FIELDS) or not all(isinstance(v,str) for v in kpi.values()):raise ValueError('KPI requires value/unit/currency/sign/period/comparison_base')
            if not all(kpi[k].strip() for k in ('value','unit','period','comparison_base')):raise ValueError('KPI context missing; explicitly record unknown context')
            if kpi['sign'] not in ('','+','−','-','≈','~'):raise ValueError('Invalid KPI sign')
            if item['value'] != kpi['sign']+kpi['currency']+kpi['value']:raise ValueError('KPI display must be atomic')
            if not isinstance(origin,dict) or set(origin)!=set(KPI_FIELDS):raise ValueError('KPI requires source component pointers')
            for field in KPI_FIELDS:
                ref=origin[field]
                if not isinstance(ref,dict) or set(ref)!={'source_id','pointer'} or ref['source_id'] not in item['source_ids']:raise ValueError('KPI component source missing: '+field)
                try:expected=pointer(sources[ref['source_id']],ref['pointer'])
                except (KeyError,IndexError,TypeError,ValueError):raise ValueError('KPI source component missing: '+field)
                if expected!=kpi[field]:raise ValueError('KPI component differs from source: '+field)
        result[item['id']]=item
    return result


def visible_pointer(slide,path):
    allowed={'fields'} if 'layout_id' in slide else {'title','subtitle','body','value','label','detail','detail_title','items','steps','nodes','edges','series','categories','columns','rows','unit','callout','caveat','center','connections'}
    if not isinstance(path,str) or path.split('/')[1:2] == [] or path.split('/')[1] not in allowed:raise ValueError('Binding must address visible content')
    try:return pointer(slide,path)
    except (KeyError,IndexError,TypeError,ValueError):raise ValueError('Unresolved content binding '+str(path))


def validate_deck(deck):
    policy=deck.get('readiness_policy','experimental')
    levels={'experimental':0,'usable':1,'production':2}
    if policy not in levels:raise ValueError('Unknown readiness_policy')
    if levels[policy]:
        from original_template import load
        registry={r['id']:r for r in load()['slides']}
        for slide in deck['slides']:
            status=registry.get(slide.get('layout_id'),{}).get('production_status','experimental')
            if levels.get(status,0)<levels[policy]:
                raise ValueError('Layout '+str(slide.get('layout_id',slide.get('layout',slide.get('kind'))))+' does not meet readiness_policy '+policy)
    model=deck.get('content_model');sources=sources_index(deck.get('sources',[]))
    items=validate_model(model) if model else {}
    if model and model['sources']!=deck.get('sources',[]):raise ValueError('Deck sources differ from Content Model sources')
    used=set()
    for slide in deck['slides']:
        for cid in slide.get('note_ids',[]):
            if cid not in items or items[cid]['kind']!='speaker_note':raise ValueError('note_ids must address speaker_note items')
            used.add(cid)
        references(slide.get('source_ids',[]),sources,not deck.get('demo',False))
        obj=slide.get('object_sources',{})
        if not isinstance(obj,dict):raise ValueError('object_sources must be an object')
        for path,refs in obj.items():visible_pointer(slide,path);references(refs,sources)
        bindings=slide.get('model_bindings',[])
        if not isinstance(bindings,list):raise ValueError('model_bindings must be an array')
        seen=set()
        for binding in bindings:
            if not isinstance(binding,dict) or set(binding)!={'pointer','content_id'}:raise ValueError('Invalid model binding')
            path=binding['pointer'];cid=binding['content_id']
            if cid not in items or path in seen:raise ValueError('Unknown content id or duplicate binding')
            seen.add(path);used.add(cid);item=items[cid]
            if visible_pointer(slide,path)!=item['value']:raise ValueError('Visible data differs from Content Model: '+cid)
            if not set(item.get('source_ids',[]))<=set(obj.get(path,[])):raise ValueError('Binding source differs from Content Model: '+cid)
            if item['kind']=='kpi':
                context=strings({k:v for k,v in slide.items() if k in ('fields','body','items','value','label','detail','detail_title','title','unit')})
                for key in ('unit','period','comparison_base'):
                    if item['kpi'][key] not in context:raise ValueError('Visible KPI context missing: '+key)
        if deck.get('evidence_policy')=='object' and not deck.get('demo') and (model or 'fields' in slide):
            if 'fields' in slide:
                required=[]
                for key,value in slide['fields'].items():
                    prefix='/fields/'+key
                    if isinstance(value,dict) and 'series' in value:required += [prefix+'/categories']+[prefix+'/series/'+str(i) for i in range(len(value['series']))]
                    else:required.append(prefix)
            else:
                required= ['/categories']+['/series/'+str(i) for i in range(len(slide['series']))] if slide.get('kind')=='chart' else ['/nodes/'+str(i) for i in range(len(slide['nodes']))]+['/edges/'+str(i) for i in range(len(slide['edges']))] if slide.get('kind')=='diagram' else []
            if any(path not in obj for path in required):raise ValueError('Object evidence missing')
    missing=set(items)-used
    for cid in list(missing):
        disposition=items[cid].get('disposition',{})
        if disposition.get('status')=='excluded' and isinstance(disposition.get('reason'),str) and disposition['reason'].strip():missing.remove(cid)
    if missing:raise ValueError('Unaccounted Content Model items: '+', '.join(sorted(missing)))
    return {'status':'passed','model':'shared' if model else 'legacy','items':len(items),'provenance':'addressability checked','truth_verification':'not-automated'}


def notes_text(deck,slide):
    items={i['id']:i for i in deck.get('content_model',{}).get('items',[])}
    ids=set(slide.get('source_ids',[]))|{r for refs in slide.get('object_sources',{}).values() for r in refs}
    ids |= {r for cid in slide.get('note_ids',[]) for r in items[cid].get('source_ids',[])}
    rows=['SOURCES','']
    for source in deck.get('sources',[]):
        if source['id'] in ids:rows += ['['+source['id']+']','Source: '+source.get('file',source['location']),'Location: '+source['location'],'']
    rows+=['CLAIMS','']
    for binding in slide.get('model_bindings',[]):
        item=items[binding['content_id']];rows += [item['id']+' → '+', '.join(item.get('source_ids',[]))+' ['+item['claim_type']+']']
    rows += [path+' → '+', '.join(refs) for path,refs in slide.get('object_sources',{}).items()]
    # Keep legacy strings consumed by the existing output verifier.
    rows += ['Источник: '+s['location'] for s in deck.get('sources',[]) if s['id'] in ids]
    rows += ['Данные '+path+': '+', '.join(refs) for path,refs in slide.get('object_sources',{}).items()]
    rows += ['','EDITORIAL NOTES','',slide.get('notes','')]
    rows += [strings(items[cid]['value']) for cid in slide.get('note_ids',[])]
    if deck.get('demo'):rows+=['Все данные вымышлены.']
    return '\n'.join(rows)


def write_report(deck,out):
    report=validate_deck(deck);out=Path(out)
    (out/'qa/content-model.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    if deck.get('content_model'):(out/'content/content-model.json').write_text(json.dumps(deck['content_model'],ensure_ascii=False,indent=2),encoding='utf-8')
    return report
