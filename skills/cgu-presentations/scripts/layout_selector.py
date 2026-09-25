"""Recommend by meaning/capacity, with explicit series exceptions."""
import json
from pathlib import Path
from collections import Counter
CATALOG=Path(__file__).resolve().parents[1]/'design-system/semantic-layouts.json'

def catalog():return {x['key']:x for x in json.loads(CATALOG.read_text(encoding='utf-8'))['layouts']}
def family(s):
    if s['kind']=='composition':
        key=s['layout'];n=len(s['items'])
        groups=[('linear',{'timeline_horizontal','process_flow','problem_solution_result','roadmap_actions','human_loop'}),('rows',{'timeline_vertical','architecture','project_status'}),('matrix',{'comparison_matrix','risk_controls'}),('hub',{'stakeholder_map','discussion_map'})]
        for name,keys in groups:
            if key in keys:return name+'-'+str(n)
        return catalog()[key]['family']+'-'+str(n)
    return s['kind']+(':'+s['variant'] if s.get('variant') else '')
def candidates(s,previous=None):
    cat=catalog();intent=s.get('intent','reference');count=len(s.get('items',s.get('steps',[]))) or 1
    items=s.get('items',[])
    def fits(v):
        return all(len(str(value))<=v['limits'].get(key,100000) for item in items for key,value in item.items())
    fitting=[v for v in cat.values() if intent in v['intents'] and v['min_items']<=count<=v['max_items'] and fits(v)]
    # Alternate base adapters are valid options, not automatic content conversions.
    alternatives={'metrics':['kpi_grid','kpi'],'sequence':['roadmap','process'],'process':['diagram','process'],'hierarchy':['diagram','text'],'comparison':['comparison','table'],'decision':['diagram','table'],'profile':['text','text_blocks'],'reference':['text','text_blocks'],'causality':['process','diagram']}
    ordered=sorted(fitting,key=lambda x:(family({'kind':'composition','layout':x['key'],'items':[{}]*count})==previous,x['key']))
    result=[{'layout':x['key'],'family':x['family'],'reason':x['purpose']} for x in ordered]
    result += [{'layout':x,'family':x,'reason':'Alternative adapter; adapt fields and revalidate capacity before use'} for x in alternatives.get(intent,[]) ]
    return result[:3]
def diversity(deck):
    slides=deck['slides'];runs=[];start=0
    for i in range(1,len(slides)+1):
        if i==len(slides) or family(slides[i])!=family(slides[start]):
            if i-start>=3:
                justified=all(s.get('repeat_reason') for s in slides[start:i])
                runs.append({'slides':[s['id'] for s in slides[start:i]],'family':family(slides[start]),'status':'justified' if justified else 'warning','reasons':[s.get('repeat_reason','') for s in slides[start:i]]})
            start=i
    return {'families':dict(Counter(family(s) for s in slides)),'runs':runs,'warnings':sum(r['status']=='warning' for r in runs),'selection':[{'slide':s['id'],'intent':s.get('intent','unspecified'),'takeaway':s.get('takeaway',''),'selected':s.get('layout',family(s)),'alternatives':candidates(s,family(slides[i-1]) if i else None),'reason':s.get('selection_reason','legacy spec: not recorded')} for i,s in enumerate(slides)]}
