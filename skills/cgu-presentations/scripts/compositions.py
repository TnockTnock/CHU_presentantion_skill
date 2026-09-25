"""Native editable compositions using the existing corporate grid and tokens."""
from layout_selector import catalog

def validate_composition(s):
    cat=catalog()
    if s.get('layout') not in cat:raise ValueError('Unknown executable composition')
    c=cat[s['layout']];items=s.get('items')
    if not isinstance(items,list) or not c['min_items']<=len(items)<=c['max_items']:raise ValueError(s['layout']+': item capacity exceeded')
    for item in items:
        if not isinstance(item,dict) or not set(c['required'])<=set(item) or set(item)-set(c['required']+c['optional']):raise ValueError('Invalid composition item fields')
        for k,v in item.items():
            if not isinstance(v,str) or not v.strip() or len(v)>c['limits'][k]:raise ValueError(s['layout']+': invalid/long '+k)
    if not isinstance(s.get('takeaway'),str) or not s['takeaway'].strip() or len(s['takeaway'])>150:raise ValueError('Composition needs takeaway <=150 chars')
    if not isinstance(s.get('caveat'),str) or not s['caveat'].strip() or len(s['caveat'])>160:raise ValueError('Composition needs visible caveat <=160 chars')
    if s['layout'] in ('metric_scale','hero_kpi'):
        if any('value' not in x for x in items):raise ValueError('KPI composition requires values')
        if len(s.get('metric_bindings',[]))!=len(items):raise ValueError('KPI composition requires metric bindings')
    if s['layout']=='decision_tree':
        edges=s.get('connections',[])
        if not edges:raise ValueError('Decision tree needs explicit connections')
    for e in s.get('connections',[]):
        if set(e)!={'from','to'} or any(type(e[k]) is not int or not 0<=e[k]<len(items) for k in e) or e['from']==e['to']:raise ValueError('Invalid composition connection')
    if s.get('image'):
        im=s['image']
        if s['layout']!='speaker_profile' or set(im)!={'path','sha256','source_id','alt','identity_status'} or im['identity_status'] not in ('source-caption','verified'):raise ValueError('Profile image needs provenance and identity status')

def scene(s):
    """Return text/background/node/edge primitives. No rasterized evidence."""
    result=[];layout=s['layout'];items=s['items'];n=len(items)
    def text(name,value,box,pt=22,heading=False,color='text',align='left'):
        result.append(dict(type='text',name=name,text=value,box=box,pt=pt,heading=heading,color=color,align=align))
    def panel(name,box,color='surface'):result.append(dict(type='panel',name=name,box=box,color=color))
    def edge(a,b,start='right',end='left'):result.append(dict(type='edge',start=a,end=b,from_side=start,to_side=end))
    def node(j,b):
        result.append(dict(type='node',name='item-'+str(j),box=b))
    def field(j,key,box,pt=22,heading=False,color='text'):
        if key in items[j]:text(f'composition-{key}-{j}',items[j][key],box,pt,heading,color)
    text('composition-takeaway',s['takeaway'],[100,255,1720,65],24,True)
    text('composition-caveat',s['caveat'],[100,920,1720,56],18,False,'muted')
    if layout in ('metric_scale','hero_kpi'):
        for j in range(n):
            if layout=='hero_kpi':
                b=[100,350,940,530] if j==0 else [1110,350+(j-1)*275,710,245]
                x,y,w,h=b;pt=68 if j==0 else 40
            else:x,y,w,h=100+(j%2)*880,350+(j//2)*275,800,245;pt=52
            field(j,'value',[x,y,w,110],pt,True,'accent');field(j,'heading',[x,y+112,w,58],24,True);field(j,'body',[x,y+172,w,65],20,False,'muted');field(j,'label',[x,y+245,w,50],18)
    elif layout in ('timeline_horizontal','process_flow','problem_solution_result','roadmap_actions','human_loop'):
        w=(1720-60*(n-1))/n
        for j in range(n):
            x=100+j*(w+60);node(j,[x,410,w,130]);field(j,'label',[x,350,w,50],20,True,'accent');field(j,'heading',[x+18,437,w-36,85],24,True);field(j,'body',[x,595,w,235],22)
            if j:edge('item-'+str(j-1),'item-'+str(j))
        if layout=='human_loop':edge('item-1','item-0','top','top')
    elif layout in ('timeline_vertical','architecture','project_status'):
        h=520/n
        for j in range(n):
            y=350+j*h;node(j,[100,y,520,h-20]);field(j,'heading',[124,y+14,472,h-45],24,True);field(j,'body',[700,y+5,1120,h-20],22);field(j,'label',[650,y+5,40,h-20],18)
            if j:edge('item-'+str(j-1),'item-'+str(j),'bottom','top')
    elif layout in ('comparison_matrix','risk_controls'):
        result.append(dict(type='table',columns=['Предмет','Основание / статус','Содержание'],rows=[[v['heading'],v.get('label','—'),v['body']] for v in items]))
    elif layout in ('speaker_profile','expert_quote'):
        panel('profile-accent',[100,350,540,510],'accent_soft')
        if s.get('image'):result.append(dict(type='image',box=[135,380,470,450],**s['image']))
        else:field(0,'heading',[135,415,470,250],32,True,'accent')
        if s.get('image'):field(0,'heading',[720,350,1100,80],32,True)
        field(0,'label',[720,450 if s.get('image') else 350,1100,80],24,True)
        field(0,'body',[720,550 if s.get('image') else 470,1100,300],30 if layout=='expert_quote' else 26)
    elif layout in ('stakeholder_map','discussion_map'):
        result.append(dict(type='node',name='center',box=[730,555,460,125]))
        text('composition-center',s.get('center','Предмет обсуждения'),[750,580,420,80],24,True,'accent','center')
        for j in range(n):
            left=j<3;k=j%3;x=100 if left else 1310;y=350+k*180;node(j,[x,y,510,150]);field(j,'heading',[x+18,y+12,474,55],22,True);field(j,'body',[x+18,y+67,474,70],18)
            edge('center','item-'+str(j),'left' if left else 'right','right' if left else 'left')
    elif layout=='decision_tree':
        coords=[[670,350,580,100],[100,550,750,125],[1070,550,750,125],[100,745,390,130],[535,745,390,130],[995,745,390,130],[1430,745,390,130]]
        for j in range(n):
            x,y,w,h=coords[j];node(j,coords[j]);field(j,'heading',[x+16,y+10,w-32,55],22,True);field(j,'body',[x+16,y+66,w-32,h-72],18)
        for e in s['connections']:edge('item-'+str(e['from']),'item-'+str(e['to']),'bottom','top')
    elif layout in ('before_after','thesis_evidence','executive_summary'):
        for j in range(n):
            if layout=='before_after':x,y,w,h=100+j*880,350,840,520
            elif layout=='thesis_evidence':x,y,w,h=100,350+j*(520/n),1720,520/n-20
            else:x,y,w,h=100,350+j*175,1720,145
            if layout=='before_after':panel('compare-'+str(j),[x,y,w,h],'accent_soft' if j else 'surface')
            field(j,'heading',[x+24,y+15,w-48,70],28,True,'accent' if j==0 else 'text')
            field(j,'body',[x+24,y+88,w-48,h-100],22);field(j,'label',[x+24,y+h-40,w-48,35],18)
    else:raise ValueError('Unimplemented composition '+layout)
    return result
