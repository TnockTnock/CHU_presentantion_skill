"""Explainable composition ranking and conservative deck-level planning QA."""
import json
from pathlib import Path
from collections import Counter

RELATIONSHIPS={'comparison','sequence','hierarchy','cause-effect','part-whole','process','network','independent'}
ROLES={'opening','context','evidence','analysis','decision','recommendation','action','reference','appendix','closing'}
FEEDBACK={'approved','too_dense','too_empty','wrong_layout','poor_hierarchy','too_repetitive','image_problem','other'}


def fingerprint(slide):
    if 'layout_id' in slide:
        from original_template import load
        from original_style import effective_slot
        record=next(r for r in load()['slides'] if r['id']==slide['layout_id'])
        slots=[effective_slot(record,s) for s in record['slots'] if s['editable']]
        boxes=[{'box':[v*4/3 for v in s['box_pt']],'type':'image' if s['role']=='image' else 'text','role':s['role']} for s in slots]
        geometry='original-slots';kpi=any(s['role']=='value' for s in slots)
    elif slide.get('kind')=='composition':
        from compositions import scene
        boxes=[v for v in scene(slide) if 'box' in v];geometry='native-scene';kpi=slide['layout'] in ('hero_kpi','metric_scale')
    else:
        # Describe known base templates by geometry rather than kind names.
        n=len(slide.get('items',slide.get('columns',slide.get('steps',[])))) or 1
        cols=3 if slide.get('kind')=='text_blocks' and slide.get('variant') in ('text_columns','columns_callout','numbered_columns') else n if slide.get('kind') in ('cards','comparison','process') else 1
        boxes=[dict(box=[100+i*1720/cols,300,1720/cols-30,550],type='panel') for i in range(cols)];geometry='base-grid-estimate';kpi=slide.get('kind') in ('kpi','kpi_grid')
    content=[v for v in boxes if v['box'][1]>=260 and v['box'][1]<920]
    centers=[(v['box'][0]+v['box'][2]/2)/1920 for v in content]
    # Cluster centers so title/subtitle variations don't create false columns.
    clusters=[]
    for x in sorted(centers):
        if not clusters or x-clusters[-1]>.09:clusters.append(x)
    images=sum(v['box'][2]*v['box'][3] for v in content if v['type']=='image')/(1920*1080)
    occupied=[0]*12
    for v in content:
        x,y,w,h=v['box']
        for gy in range(3):
            for gx in range(4):
                cx,cy=(gx+.5)*480,270+(gy+.5)*216
                if x<=cx<=x+w and y<=cy<=y+h:occupied[gy*4+gx]=1
    panels=sum(v['type'] in ('node','panel') for v in content)
    left=sum(x<.5 for x in centers);right=len(centers)-left
    accent=[v for v in content if v.get('color')=='accent' or v.get('role')=='value']
    return {'columns':len(clusters),'cards':panels,'dominant_geometry':'grid' if len(clusters)>1 else 'stack',
            'symmetry':abs(left-right)<=1,'image_coverage':round(min(images,1),2),'text_image_ratio':round(sum(v['type']=='text' for v in content)/max(1,sum(v['type']=='image' for v in content)),2),
            'primary_emphasis':'left' if accent and accent[0]['box'][0]<960 else 'right' if accent else 'top',
            'kpi':kpi,'chart':slide.get('kind')=='chart' or any(v.get('role')=='chart' for v in boxes),
            'table':slide.get('kind')=='table' or any(v.get('role')=='table' for v in boxes),
            'accent_area':round(sum(v['box'][2]*v['box'][3] for v in accent)/(1920*1080),2),
            'whitespace_distribution':[1-v for v in occupied],'measurement':geometry}


def similarity(a,b):
    keys=['columns','cards','dominant_geometry','symmetry','primary_emphasis','kpi','chart','table']
    scores=[float(a[k]==b[k]) for k in keys]
    scores += [1-abs(a['image_coverage']-b['image_coverage']),1-abs(a['accent_area']-b['accent_area']),sum(x==y for x,y in zip(a['whitespace_distribution'],b['whitespace_distribution']))/12]
    return round(sum(scores)/len(scores),3)


def rank(request,previous_layouts=(),next_layout=None,allow_experimental=False,feedback=()):
    from original_template import load
    from original_build import example
    if request.get('relationship') and request['relationship'] not in RELATIONSHIPS:raise ValueError('Unknown relationship')
    if request.get('narrative_role') and request['narrative_role'] not in ROLES:raise ValueError('Unknown narrative role')
    cat=load()['slides'][5:];indexed={r['id']:r for r in cat};result=[]
    neighbors=[indexed[x] for x in list(previous_layouts)[-2:]+([next_layout] if next_layout else []) if x in indexed]
    for record in cat:
        if record['intent']!=request.get('intent','reference'):continue
        status=record.get('production_status','experimental')
        if status=='experimental' and not allow_experimental:continue
        counts=record['editable_counts'];typ=request.get('data_type','text')
        if typ in ('chart','table','image') and not counts[typ]:continue
        if typ=='text' and (counts['chart'] or counts['table']):continue
        capacity=sum(s['max_chars'] for s in record['slots'] if s['role'] in ('body','heading','value'))
        fields=sum(counts[k] for k in ('body','heading','value'));needed=request.get('fields',1)
        if fields<needed or counts['image']<request.get('images',0) or capacity<request.get('text_length',0):continue
        semantic=1.0 if record['intent']==request.get('intent','reference') else .2
        relation=1.0 if (request.get('relationship') or 'independent') in record.get('relationships',[]) else 0.0
        role=1.0 if (request.get('narrative_role') or 'reference') in record.get('narrative_roles',[]) else 0.0
        fp=fingerprint(example(record));near=max([similarity(fp,fingerprint(example(n))) for n in neighbors] or [0])
        density=1.0 if request.get('information_density','medium')==record.get('density','medium') else .3
        # Small bounded feedback signal, no free text or corporate contents.
        votes=[f for f in feedback if f.get('layout_id')==record['id'] and f.get('intent')==request.get('intent')]
        signal=max(-.03,min(.03,sum(.01 if v['feedback']=='approved' else -.01 for v in votes)))
        emphasis=request.get('emphasis');emphasis_fit=(emphasis in ('kpi','value') and counts['value']>0) or (emphasis=='image' and counts['image']>0) or (emphasis=='chart' and counts['chart']>0)
        # Takeaway length is a conservative capacity signal, not understanding.
        takeaway_fit=min(1,capacity/max(len(request.get('takeaway') or ''),1))
        parts={'takeaway_capacity':round(.02*takeaway_fit,3),'emphasis':.03 if emphasis_fit else 0,'semantic_fit':round(.23*semantic+.10*relation+.08*role,3),'capacity_fit':round(.17*needed/max(fields,1),3),'visual_diversity':round(.12*(1-near),3),'production_status':{'production':.13,'usable':.06,'experimental':0}[status],'asset_compatibility':.05 if not request.get('visual_asset') or counts['image'] else 0,'density':round(.07*density,3),'feedback':signal}
        result.append({'id':record['id'],'source_slide':record['source_slide'],'family':record['family'],'status':record['status'],'production_status':status,'score':round(sum(parts.values()),3),'score_components':parts,'reason':record['selection'],'warning':None if status=='production' else 'Layout is '+status+'; visual review required','takeaway_review':'manual; no lexical meaning score claimed'})
    return sorted(result,key=lambda v:({'production':0,'usable':1,'experimental':2}[v['production_status']],-v['score'],v['source_slide']))[:3]


def storyboard(deck):
    rows=[];warnings=[];slides=deck['slides']
    for i,s in enumerate(slides):
        role=s.get('narrative_role','appendix' if s.get('section')=='appendix' else 'opening' if i==0 else 'reference')
        if role not in ROLES:raise ValueError('Unknown narrative role')
        fp=fingerprint(s)
        if rows and similarity(fp,rows[-1]['fingerprint'])>=.90 and not s.get('repeat_reason'):warnings.append({'slide':s['id'],'issue':'neighboring compositions look similar','similarity':similarity(fp,rows[-1]['fingerprint'])})
        if i>=2 and all(r['narrative_role']==role for r in rows[-2:]):warnings.append({'slide':s['id'],'issue':'three repeated narrative roles'})
        if role in ('decision','recommendation') and not s.get('source_ids'):warnings.append({'slide':s['id'],'issue':'strong claim without evidence'})
        if role=='appendix' and s.get('section')!='appendix':warnings.append({'slide':s['id'],'issue':'appendix-like slide in main section'})
        if 'layout_id' in s:
            alternatives=rank(dict(intent=s.get('intent','reference'),fields=1,relationship=s.get('relationship','independent'),narrative_role=role),[x.get('layout_id','') for x in slides[:i]],slides[i+1].get('layout_id') if i+1<len(slides) else None,deck.get('demo',False))
        else:
            from layout_selector import candidates
            alternatives=candidates(s)
        rows.append({'slide':s['id'],'purpose':s.get('purpose',s.get('title',s.get('takeaway',''))),'takeaway':s.get('takeaway',''),'narrative_role':role,'selected_layout':s.get('layout_id',s.get('layout',s.get('kind'))),'alternative_layouts':alternatives,'reason':s.get('selection_reason','legacy: reason not recorded'),'density':s.get('information_density','unspecified'),'sources':s.get('source_ids',[]),'fingerprint':fp})
    main=[r for r in rows if r['narrative_role']!='appendix']
    if main and main[-1]['narrative_role'] not in ('decision','recommendation','action','closing'):warnings.append({'issue':'main narrative has no final conclusion'})
    if sum(r['fingerprint']['table'] for r in main)>max(2,len(main)//3):warnings.append({'issue':'many tables in main narrative'})
    return {'slides':rows,'warnings':warnings,'logical_sequence':'heuristic checks only; narrative review required'}


def write_storyboard(deck,out):
    out=Path(out);report=storyboard(deck)
    (out/'content/storyboard.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# Storyboard','']
    for r in report['slides']:lines += ['## '+r['slide'],r['purpose'],r['takeaway'],r['narrative_role']+' · '+str(r['selected_layout'])+' · '+r['density'],r['reason'],'Sources: '+', '.join(r['sources']),'']
    lines+=['## QA',json.dumps(report['warnings'],ensure_ascii=False,indent=2)]
    (out/'content/storyboard.md').write_text('\n'.join(lines),encoding='utf-8')
    (out/'qa/storyboard.json').write_text(json.dumps({'warnings':report['warnings'],'logical_sequence':report['logical_sequence']},ensure_ascii=False,indent=2),encoding='utf-8')
    return report


def record_feedback(entry,path):
    if not isinstance(entry,dict) or set(entry)!={'layout_id','intent','density','feedback'} or entry['feedback'] not in FEEDBACK or entry['density'] not in ('low','medium','high'):raise ValueError('Only anonymized structured feedback is allowed')
    from original_template import load
    if entry['layout_id'] not in {r['id'] for r in load()['slides'][5:]}:raise ValueError('Unknown layout')
    if entry['intent'] not in {'metrics','comparison','sequence','process','hierarchy','reference','decision','profile','causality'}:raise ValueError('Unknown intent')
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a',encoding='utf-8') as f:f.write(json.dumps(entry,ensure_ascii=False)+'\n')
