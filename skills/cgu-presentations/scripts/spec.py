"""Validation for the supported template adapter. No silent ignored slide types."""
import math

KINDS = {'cover', 'cards', 'kpi', 'process', 'diagram', 'chart', 'table', 'text', 'kpi_grid', 'comparison', 'roadmap'}

def validate(deck):
    def require(ok, message):
        if not ok:
            raise ValueError(message)
    def text(value, limit, label):
        require(isinstance(value, str) and bool(value.strip()), f'{label}: nonempty text required')
        require(len(value) <= limit, f'{label}: maximum {limit} characters; shorten or split the slide')
    require(isinstance(deck, dict), 'Root must be an object')
    require(not (set(deck) - {'schema_version','title','demo','sources','slides','evidence_policy'}), 'Unknown root fields')
    require(deck.get('evidence_policy','slide') in ('slide','object'), 'Unknown evidence policy')
    require(deck.get('schema_version') == 'cgu-presentations/2', 'Expected schema_version cgu-presentations/2')
    text(deck.get('title'), 100, 'title')
    require(type(deck.get('demo',False)) is bool, 'demo must be boolean')
    slides = deck.get('slides')
    require(isinstance(slides, list) and 1 <= len(slides) <= 40, 'Expected 1–40 slides')
    facts = deck.get('sources', [])
    require(isinstance(facts, list), 'sources must be an array')
    ids = []
    for f in facts:
        require(isinstance(f, dict), 'Source must be an object')
        text(f.get('id'), 80, 'source id'); text(f.get('location'), 500, 'source location')
        require(f.get('status','source') in ('source','calculated','assumption','conflict'), 'Invalid source status')
        if f.get('status')=='calculated':
            text(f.get('formula'),500,'calculation formula')
        ids.append(f['id'])
    require(len(ids) == len(set(ids)), 'Duplicate source id')
    slide_ids = []
    for i, s in enumerate(slides, 1):
        prefix = f'Slide {i}'
        require(isinstance(s, dict), prefix + ': expected object')
        text(s.get('id'), 80, prefix + ' id'); slide_ids.append(s['id'])
        kind = s.get('kind'); require(isinstance(kind,str) and kind in KINDS, prefix + ': unsupported kind')
        text(s.get('title'), 85, prefix + ' title')
        extra = {'cover':{'subtitle'}, 'cards':{'items'}, 'kpi':{'value','label','detail_title','detail'}, 'text':{'body'}, 'process':{'steps'}, 'diagram':{'nodes','edges'}, 'chart':{'chart_type','categories','series','unit'}, 'table':{'columns','rows'}}
        extra.update(kpi_grid={'items'},comparison={'columns'},roadmap={'steps'})
        require(not (set(s) - {'id','kind','title','source_ids','notes','footer','object_sources'} - extra[kind]), prefix + ': unknown fields')
        for key,limit in [('notes',10000),('footer',120)]:
            if key in s: require(isinstance(s[key],str) and len(s[key])<=limit, prefix + ': invalid '+key)
        refs = s.get('source_ids', [])
        require(isinstance(refs, list) and all(r in ids for r in refs), prefix + ': unresolved source')
        require(deck.get('demo') is True or bool(refs), prefix + ': source_ids required for non-demo slides')
        object_sources=s.get('object_sources',{})
        require(isinstance(object_sources,dict),prefix+': object_sources must be an object')
        for pointer,source_ids in object_sources.items():
            require(isinstance(pointer,str) and pointer.startswith('/') and '~' not in pointer,prefix+': use a simple JSON pointer')
            require(pointer.split('/')[1] in extra[kind],prefix+': pointer must address slide content')
            value=s
            try:
                for key in pointer[1:].split('/'):
                    if isinstance(value,list):
                        require(key.isdigit() and str(int(key))==key,prefix+': invalid array index')
                        value=value[int(key)]
                    else:value=value[key]
            except (KeyError,IndexError,TypeError,ValueError):
                raise ValueError(prefix+': unresolved object pointer '+pointer)
            require(isinstance(source_ids,list) and bool(source_ids) and all(r in ids for r in source_ids),prefix+': unresolved object source')
            require(not any(f.get('status')=='conflict' for f in facts if f['id'] in source_ids),prefix+': unresolved conflicting evidence')
        if deck.get('evidence_policy')=='object' and not deck.get('demo'):
            required={'kpi':['/value'],'kpi_grid':['/items/'+str(j) for j in range(len(s.get('items',[])))],'roadmap':['/steps/'+str(j) for j in range(len(s.get('steps',[])))],'chart':['/series/'+str(j) for j in range(len(s.get('series',[])))],'diagram':['/edges/'+str(j) for j in range(len(s.get('edges',[])))]}.get(kind,[])
            require(all(key in object_sources for key in required),prefix+': object evidence missing')
        if kind == 'kpi_grid':
            require(isinstance(s.get('items'),list) and 2<=len(s['items'])<=4,prefix+': 2–4 KPI items')
            for item in s['items']:
                require(isinstance(item,dict) and set(item)=={'value','label','detail'},prefix+': invalid KPI item')
                text(item['value'],12,prefix+': KPI value');text(item['label'],65,prefix+': KPI label');text(item['detail'],130,prefix+': KPI detail')
        elif kind == 'comparison':
            require(isinstance(s.get('columns'),list) and len(s['columns'])==2,prefix+': two comparison columns')
            for col in s['columns']:
                require(isinstance(col,dict) and set(col)=={'title','items'},prefix+': invalid comparison column')
                text(col['title'],45,prefix+': comparison title')
                require(isinstance(col['items'],list) and 2<=len(col['items'])<=4,prefix+': 2–4 comparison items')
                for item in col['items']:text(item,110,prefix+': comparison item')
            require(len(s['columns'][0]['items'])==len(s['columns'][1]['items']),prefix+': compare matching criteria row by row')
        elif kind == 'roadmap':
            require(isinstance(s.get('steps'),list) and 3<=len(s['steps'])<=6,prefix+': 3–6 roadmap steps')
            for step in s['steps']:
                require(isinstance(step,dict) and set(step)=={'title','period','body'},prefix+': invalid roadmap step')
                text(step['title'],38,prefix+': roadmap title');text(step['period'],25,prefix+': roadmap period');text(step['body'],100,prefix+': roadmap body')
        elif kind == 'cover':
            text(s.get('subtitle'), 180, prefix + ' subtitle')
        elif kind == 'cards':
            require(isinstance(s.get('items'), list) and len(s['items']) == 4, prefix + ': cards requires exactly 4 items')
            for item in s['items']:
                require(isinstance(item,dict) and set(item)<= {'title','body'}, prefix + ': invalid card object')
                text(item.get('title'), 42, prefix + ' card title'); text(item.get('body'), 160, prefix + ' card body')
        elif kind == 'kpi':
            text(s.get('value'), 9, prefix + ' value'); text(s.get('label'), 130, prefix + ' label')
            text(s.get('detail_title'), 45, prefix + ' detail title'); text(s.get('detail'), 350, prefix + ' detail')
        elif kind == 'text':
            text(s.get('body'), 650, prefix + ' body')
        elif kind == 'process':
            require(isinstance(s.get('steps'), list) and 2 <= len(s['steps']) <= 5, prefix + ': 2–5 steps required')
            for step in s['steps']:
                require(isinstance(step,dict) and set(step)<= {'title','body'}, prefix + ': invalid step object')
                text(step.get('title'), 35, prefix + ' step title'); text(step.get('body'), 90, prefix + ' step body')
        elif kind == 'diagram':
            nodes = s.get('nodes', []); edges = s.get('edges', [])
            require(isinstance(nodes, list) and 2 <= len(nodes) <= 8, prefix + ': 2–8 nodes required')
            require(isinstance(edges, list), prefix + ': edges must be an array')
            node_ids = []
            for node in nodes:
                require(isinstance(node,dict) and set(node)<= {'id','text','box','accent'}, prefix + ': invalid node object')
                require(type(node.get('accent',False)) is bool, prefix + ': accent must be boolean')
                text(node.get('id'), 60, prefix + ' node id'); node_ids.append(node['id'])
                text(node.get('text'), 80, prefix + ' node text')
                b = node.get('box')
                require(isinstance(b, list) and len(b) == 4 and all(type(v) in (int, float) and math.isfinite(v) for v in b), prefix + ': node box must be [x,y,w,h] in CSS px')
                x,y,w,h = b
                require(x >= 100 and y >= 270 and w >= 160 and h >= 100 and x+w <= 1820 and y+h <= 920, prefix + ': node outside safe area or too small')
            require(len(node_ids) == len(set(node_ids)), prefix + ': duplicate node id')
            for aidx, a in enumerate(nodes):
                x,y,w,h=a['box']
                for b in nodes[aidx+1:]:
                    bx,by,bw,bh=b['box']
                    require(not (x<bx+bw and x+w>bx and y<by+bh and y+h>by), prefix + ': overlapping nodes')
            for edge in edges:
                require(isinstance(edge,dict), prefix + ': invalid edge object')
                require(not (set(edge) - {'from','to','from_side','to_side','label','label_box'}), prefix + ': unknown edge fields')
                if 'label' in edge or 'label_box' in edge:
                    text(edge.get('label'),60,prefix+': edge label')
                    b=edge.get('label_box')
                    require(isinstance(b,list) and len(b)==4 and all(type(v) in (int,float) and math.isfinite(v) for v in b),prefix+': label_box required')
                    x,y,w,h=b
                    require(x>=100 and y>=270 and w>=60 and h>=30 and x+w<=1820 and y+h<=920,prefix+': label outside safe area')
                    for node in nodes:
                        nx,ny,nw,nh=node['box']
                        require(not (x<nx+nw and x+w>nx and y<ny+nh and y+h>ny),prefix+': label overlaps node')
                require(edge.get('from') in node_ids and edge.get('to') in node_ids, prefix + ': dangling edge')
                require(edge['from'] != edge['to'], prefix + ': self-edge unsupported')
                require(edge.get('from_side', 'right') in ('left','right','top','bottom') and edge.get('to_side','left') in ('left','right','top','bottom'), prefix + ': invalid connector side')
        elif kind == 'chart':
            require(s.get('chart_type','bar') in ('bar','line'), prefix + ': supported charts: bar, line')
            cats=s.get('categories'); series=s.get('series')
            require(isinstance(cats,list) and 2<=len(cats)<=10 and all(isinstance(v,str) and 0<len(v)<=25 for v in cats), prefix+': expected 2–10 short categories')
            require(isinstance(series,list) and 1<=len(series)<=3, prefix+': expected 1–3 series')
            for ser in series:
                require(isinstance(ser,dict) and set(ser)<= {'name','values'}, prefix + ': invalid series object')
                text(ser.get('name'),40,prefix+' series name')
                vals=ser.get('values')
                require(isinstance(vals,list) and len(vals)==len(cats) and all(type(v) in (int,float) and math.isfinite(v) for v in vals),prefix+': category/value mismatch or non-finite number')
            text(s.get('unit'),50,prefix+' unit')
        elif kind == 'table':
            rows=s.get('rows');columns=s.get('columns')
            require(isinstance(columns,list) and 2<=len(columns)<=4,prefix+': expected 2–4 columns')
            require(isinstance(rows,list) and 1<=len(rows)<=7,prefix+': expected 1–7 rows')
            for row in [columns]+rows:
                require(isinstance(row,list) and len(row)==len(columns),prefix+': ragged table')
                for cell in row: text(cell,100,prefix+' cell')
    require(len(slide_ids)==len(set(slide_ids)), 'Duplicate slide id')
    return deck
