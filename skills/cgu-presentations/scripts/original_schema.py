"""Generate per-adapter JSON Schema definitions from the original registry."""
import json
from original_template import load,SKILL
from original_style import effective_slot

def generate():
    string={'type':'string','minLength':1};image={'type':'object','additionalProperties':False,'required':['path','sha256','alt'],'properties':{'path':string,'alt':string,'sha256':{'type':'string','pattern':'^[0-9a-f]{64}$'},'fit':{'enum':['cover','contain']},'focus':{'type':'array','minItems':2,'maxItems':2,'items':{'type':'number','minimum':0,'maximum':1}}}}
    chart={'type':'object','additionalProperties':False,'required':['categories','series'],'properties':{'chart_type':{'enum':['bar','line']},'categories':{'type':'array','items':string,'minItems':1,'maxItems':8},'series':{'type':'array','minItems':1,'maxItems':3,'items':{'type':'object','additionalProperties':False,'required':['name','values'],'properties':{'name':string,'values':{'type':'array','items':{'type':'number'},'minItems':1,'maxItems':8}}}}}}
    table={'type':'object','additionalProperties':False,'required':['columns','rows'],'properties':{'columns':{'type':'array','items':string,'minItems':1,'maxItems':5},'rows':{'type':'array','minItems':1,'maxItems':6,'items':{'type':'array','items':{'type':'string'},'minItems':1,'maxItems':5}}}}
    defs={}
    for r in load()['slides'][5:]:
        props={}
        for source_slot in r['slots']:
            s=effective_slot(r,source_slot)
            if not s['editable']:continue
            props[s['id']]= image if s['role']=='image' else chart if s['role']=='chart' else table if s['role']=='table' else dict(string,maxLength=s['max_chars'])
        defs[r['id']]={'type':'object','additionalProperties':False,'required':['id','layout_id','takeaway','fields'],'properties':{'id':string,'layout_id':{'const':r['id']},'takeaway':string,'notes':{'type':'string'},'source_ids':{'type':'array','items':string},'repeat_reason':string,'fields':{'type':'object','additionalProperties':False,'required':[s['id'] for s in r['slots'] if s['required']],'properties':props}}}
    from content_model import SLIDE_FIELDS
    for definition in defs.values():
        definition['properties'].update({k:({'type':'array'} if k in ('model_bindings','metric_bindings','note_ids') else {'type':'object'} if k=='object_sources' else {'type':'string'}) for k in SLIDE_FIELDS|{'object_sources','metric_bindings','intent','statement_type','selection_reason','section'}})
    root_extra={'content_model':{'$ref':'content-model.schema.json'},'content_ledger':{'$ref':'content-ledger.schema.json'},'review_policy':{'enum':['legacy','strict']},'evidence_policy':{'enum':['slide','object']},'readiness_policy':{'enum':['production','usable','experimental']}}
    return {'$schema':'https://json-schema.org/draft/2020-12/schema','title':'CGU original template deck; 77 adapter contracts','type':'object','additionalProperties':False,'required':['schema_version','title','slides'],'properties':{**root_extra,'schema_version':{'const':'cgu-original-deck/1'},'title':string,'demo':{'type':'boolean'},'sources':{'type':'array','items':{'type':'object'}},'slides':{'type':'array','minItems':1,'maxItems':160,'items':{'oneOf':[{'$ref':'#/$defs/'+k} for k in defs]}}},'$defs':defs}
if __name__=='__main__':(SKILL/'schemas/original-deck.schema.json').write_text(json.dumps(generate(),ensure_ascii=False,indent=2),encoding='utf-8')
