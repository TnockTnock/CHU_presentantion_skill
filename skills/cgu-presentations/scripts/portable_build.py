"""Build all /2 compositions by editing a copy of the corporate OOXML template.

No third-party libraries or Codex services. Geometry follows the existing adapter;
portable rendering is validated independently, not claimed pixel-identical.
"""
import copy
import hashlib
from datetime import date
import json
from pathlib import Path
import posixpath
from zipfile import ZipFile, ZIP_DEFLATED
from xml.etree import ElementTree as ET
from normalize_fonts import normalize
from portable_fonts import Metrics
from portable_ooxml import NS, tag, el, xml, shape, pos, textbody, connector, frame, table, chart_xml, workbook, picture, image_size
from number_typography import transform

SKILL=Path(__file__).resolve().parents[1]

def build(deck,out):
    registry=json.loads((SKILL/'design-system/layouts.json').read_text(encoding='utf-8'))
    tokens=json.loads((SKILL/'design-system/tokens.json').read_text(encoding='utf-8'));colors=tokens['colors']
    layouts={v['kind']:v for v in registry['layouts']};metrics=Metrics(SKILL)
    normalized=out/'build/template-golos.pptx';normalize(SKILL/registry['template'],normalized)
    with ZipFile(normalized) as z:parts={n:z.read(n) for n in z.namelist()}
    originals=dict(parts)
    pres=ET.fromstring(parts['ppt/presentation.xml']);lst=pres.find('p:sldIdLst',NS);lst.clear()
    for child in list(pres):
        if child.tag in (tag('p:custShowLst'),tag('p:extLst')):pres.remove(child)
    pr=ET.fromstring(parts['ppt/_rels/presentation.xml.rels'])
    for rel in list(pr):
        if rel.get('Type','').endswith('/slide'):pr.remove(rel)
    for name in list(parts):
        if name.startswith('ppt/slides/'):del parts[name]
    ct=ET.fromstring(parts['[Content_Types].xml'])
    def content_type(name,kind):
        for existing in list(ct):
            if existing.get('PartName')=='/'+name:ct.remove(existing)
        el('ct:Override',ct,PartName='/'+name,ContentType='application/vnd.openxmlformats-officedocument.'+kind+'+xml')
    maps=[]
    red,black,gray,surface=colors['accent'],colors['text'],colors['muted'],colors['surface']
    for i,d in enumerate(deck['slides'],1):
        layout=layouts[d['kind']];slots=layout['slots'];source=layout['source_part'];root=ET.fromstring(originals[source]);tree=root.find('p:cSld/p:spTree',NS)
        for sp in list(tree):
            info=sp.find('.//p:cNvPr',NS)
            if info is not None and ((layout['keep_shape_ids'] is not None and info.get('id') not in layout['keep_shape_ids']) or info.get('id') in layout['remove_shape_ids']):tree.remove(sp)
        counter=1000;boxes={};profile_asset=None
        def label(name,text,x,y,w,h,pt=24,heading=False,color=black,align='left',center=False,background=None,pad=0):
            nonlocal counter
            metrics.check(text,w-2*pad,h-2*pad,pt,heading,name);counter+=1
            shape(tree,counter,name,[x,y,w,h],text,pt,heading,color,background,align,center,pad);boxes[counter]=[x,y,w,h];return counter
        def panel(name,x,y,w,h,fill=surface):
            nonlocal counter
            counter+=1;shape(tree,counter,name,[x,y,w,h],background=fill)
        def edit(id,text,pt=24,heading=False,b=None,color=black,align='left',center=False):
            s=next(sp for sp in tree.findall('p:sp',NS) if sp.find('p:nvSpPr/p:cNvPr',NS).get('id')==id)
            sp=s.find('p:spPr',NS);xf=sp.find('a:xfrm',NS)
            if b is None:
                if xf is None:raise ValueError('Template slot has no local geometry: '+id)
                off=xf.find('a:off',NS);ext=xf.find('a:ext',NS);b=[int(off.get('x'))/9525,int(off.get('y'))/9525,int(ext.get('cx'))/9525,int(ext.get('cy'))/9525]
            metrics.check(text,b[2],b[3],pt,heading,'slot '+id)
            if xf is not None:sp.remove(xf)
            new=pos(sp,b);sp.remove(new);sp.insert(0,new)
            tx=s.find('p:txBody',NS)
            if tx is not None:s.remove(tx)
            textbody(s,text,pt,heading,color,align,center)
        def node(name,text,b,accent=False):return label('node-'+name,text,*b,26,True,'#FFFFFF' if accent else black,'center',True,red if accent else surface,22)
        def link(a,b,start='right',end='left'):
            nonlocal counter
            counter+=1;connector(tree,counter,a,b,boxes,start,end,red)
        if d['kind']=='cover':
            edit(slots['title'],d['title'],60,True,[170,470,820,220]);edit(slots['subtitle'],d['subtitle'],24,False,[170,710,820,120]);edit(slots['department'],'ДИТ Москвы',14,False,None,gray,'center',True);edit(slots['year'],'ДЕМО' if deck.get('demo') else str(date.today().year),14,False,None,gray,'center',True)
        else:edit(slots['title'],d['title'],44,True,tokens['geometry']['title_box_px'])
        kind=d['kind']
        if kind=='cards':
            for j,slot in enumerate(slots['cards']):
                edit(slot['title'],d['items'][j]['title'],24,True);edit(slot['body'],d['items'][j]['body']);edit(slot['number'],f'{j+1:02}',14,True,None,'#FFFFFF','center',True)
        elif kind=='kpi':
            edit(slots['label'],d['label'],24,False,[100,285,790,135]);edit(slots['value'],d['value'],190,True,[100,550,790,310],red);label('kpi-detail-title',d['detail_title'],1020,300,700,90,26,True);label('kpi-detail',d['detail'],1020,420,700,390)
        elif kind=='composition':
            from compositions import scene
            primitives=scene(d);node_ids={}
            for v in primitives:
                t=v['type']
                if t=='text':label(v['name'],v['text'],*v['box'],v['pt'],v['heading'],colors[v['color']],v['align'])
                elif t=='panel':panel(v['name'],*v['box'],colors[v['color']])
                elif t=='node':
                    counter+=1;shape(tree,counter,'composition-node-'+v['name'],v['box'],background=surface);boxes[counter]=v['box'];node_ids[v['name']]=counter
                elif t=='table':
                    counter+=1;table(tree,counter,v['columns'],v['rows'],metrics,y=345,max_height=545,pt=20,row_height=110)
                elif t=='image':
                    data=Path(v['path']).read_bytes()
                    if hashlib.sha256(data).hexdigest()!=v['sha256']:raise ValueError('Profile image SHA mismatch')
                    ext='png' if data.startswith(b'\x89PNG') else 'jpeg';profile_asset=f'ppt/media/profile-{i}.{ext}';parts[profile_asset]=data
                    if not any(e.get('Extension')==ext for e in ct):el('ct:Default',ct,Extension=ext,ContentType='image/'+ext)
                    counter+=1;picture(tree,counter,'rIdProfile',v['box'],*image_size(data),v['alt'])
            for v in primitives:
                if v['type']=='edge':link(node_ids[v['start']],node_ids[v['end']],v['from_side'],v['to_side'])
        elif kind=='text':label('body',d['body'],100,290,1630,620,30)
        elif kind=='kpi_grid':
            w=(1720-30*(len(d['items'])-1))/len(d['items'])
            for j,item in enumerate(d['items']):
                x=100+j*(w+30);panel('metric-background-'+str(j),x,300,w,580);label('metric-value-'+str(j),item['value'],x+28,355,w-56,120,52,True,red);label('metric-label-'+str(j),item['label'],x+28,510,w-56,135,24,True);label('metric-detail-'+str(j),item['detail'],x+28,690,w-56,155,20,False,gray)
        elif kind=='comparison':
            for j,col in enumerate(d['columns']):
                x=100+j*890;panel('comparison-background-'+str(j),x,290,830,610);label('comparison-title-'+str(j),col['title'],x+32,320,766,115,30,True,red if j==1 else black)
                for k,value in enumerate(col['items']):label(f'comparison-item-{j}-{k}',value,x+32,465+k*100,766,90,23)
        elif kind=='process':
            n=len(d['steps']);w=(1720-90*(n-1))/n;nodes=[]
            for j,item in enumerate(d['steps']):
                x=100+j*(w+90);label('step-number-'+str(j),f'{j+1:02}',x,350,w,90,44,True,red);nodes.append(node('step-'+str(j),item['title'],[x,465,w,135],j==0));label('step-body-'+str(j),item['body'],x,645,w,200,22)
            for a,b in zip(nodes,nodes[1:]):link(a,b)
        elif kind=='roadmap':
            n=len(d['steps']);per=min(n,3);w=(1720-65*(per-1))/per;nodes=[]
            for j,item in enumerate(d['steps']):
                row=j//per;col=j if row==0 else per-1-j%per;x=100+col*(w+65);y=300+row*340
                label('roadmap-period-'+str(j),item['period'],x,y,w,50,20,True,red);nodes.append(node('roadmap-'+str(j),item['title'],[x,y+62,w,105],j==0));label('roadmap-body-'+str(j),item['body'],x,y+190,w,105,21)
            for j in range(n-1):link(nodes[j],nodes[j+1],'right' if j<per else 'left','right' if j==per-1 or j>=per else 'left')
        elif kind=='diagram':
            nodes={v['id']:node(v['id'],v['text'],v['box'],v.get('accent',False)) for v in d['nodes']}
            for j,e in enumerate(d['edges']):
                link(nodes[e['from']],nodes[e['to']],e.get('from_side','right'),e.get('to_side','left'))
                if e.get('label'):label('edge-label-'+str(j),e['label'],*e['label_box'],18,False,gray,'center',True)
        elif kind=='table':counter+=1;table(tree,counter,d['columns'],d['rows'],metrics)
        elif kind=='chart':
            label('chart-unit',d['unit'],100,250,1650,65,22,False,gray);counter+=1
            el('c:chart',frame(tree,counter,'native-chart',[100,340,1700,575],NS['c']),**{tag('r:id'):'rIdCguChart'})
            chartpart=f'ppt/charts/chart{i}.xml';parts[chartpart]=xml(chart_xml(d,[red,colors['chart_secondary'],gray]));content_type(chartpart,'drawingml.chart')
            wbpart=f'ppt/embeddings/cgu-data-{i}.xlsx';parts[wbpart]=workbook(d['categories'],d['series'])
            cr=el('rel:Relationships');el('rel:Relationship',cr,Id='rIdWorkbook',Type=NS['r']+'/package',Target=f'../embeddings/cgu-data-{i}.xlsx');parts[f'ppt/charts/_rels/chart{i}.xml.rels']=xml(cr)
        elif kind=='text_blocks':
            variant=d['variant']
            def content(j,x,y,w,number=False,accent=False):
                item=d['items'][j];ink='#FFFFFF' if accent else black;offset=78 if number else 0
                if number:label('block-number-'+str(j),f'{j+1:02}',x,y,w,65,36,True,red)
                label('block-title-'+str(j),item['title'],x,y+offset,w,65 if number else 80,26,True,ink)
                label('block-body-'+str(j),item['body'],x,y+offset+(70 if number else 88),w,105 if variant=='cards_grid' else 390 if variant=='text_columns' else 260,22,False,ink if accent else gray)
            if variant=='numbered_columns':
                for j in range(3):
                    x=100+j*590;label('block-number-'+str(j),f'{j+1:02}',x,340,530,150,90,True,red);content(j,x,545,530)
            elif variant=='cards_grid':
                for j in range(5):
                    top=j<3;w=553.333 if top else 845;x=100+(j if top else j-3)*(w+30);y=300 if top else 620;panel('block-panel-'+str(j),x,y,w,290);content(j,x+28,y+22,w-56,True)
            elif variant in ('columns_callout','text_columns'):
                for j in range(3):
                    x=100+j*583.333;callout=variant=='columns_callout';panel('block-panel-'+str(j),x,300,553.333,440 if callout else 600);content(j,x+30,330 if callout else 350,493.333,callout)
            elif variant=='split_panel':
                panel('block-panel-0',100,300,630,440);content(0,136,342,558);panel('block-panel-1',760,300,1060,440,red);content(1,804,342,972,False,True)
            elif variant=='metrics_band':
                for j,item in enumerate(d['items']):
                    x=100+j%2*875;y=300+j//2*225;panel('block-panel-'+str(j),x,y,845,200);label('block-value-'+str(j),item['value'],x+28,y+20,789,76,44,True,red);label('block-title-'+str(j),item['title'],x+28,y+101,789,46,24,True);label('block-body-'+str(j),item['body'],x+28,y+153,789,40,18,False,gray)
            if d.get('callout'):
                split=variant=='split_panel';panel('block-callout-panel',100,785,1720,125,colors['accent_soft'] if split else red);label('block-callout',d['callout'],136,817,1648,70,26,True,black if split else '#FFFFFF')
        label('footer','ДЕМОНСТРАЦИОННЫЕ ДАННЫЕ' if deck.get('demo') else d.get('footer',''),100,994,1600,38,12,False,gray);label('page-number',str(i),1740,994,80,38,12,False,gray,'right')
        transform(root);part=f'ppt/slides/slide{i}.xml';parts[part]=xml(root);content_type(part,'presentationml.slide')
        relpath=posixpath.join(posixpath.dirname(source),'_rels',posixpath.basename(source)+'.rels');rels=ET.fromstring(originals[relpath])
        for rel in list(rels):
            if rel.get('Type','').endswith(('/notesSlide','/slide')):rels.remove(rel)
        if profile_asset:el('rel:Relationship',rels,Id='rIdProfile',Type=NS['r']+'/image',Target='../media/'+profile_asset.rsplit('/',1)[1])
        if kind=='chart':el('rel:Relationship',rels,Id='rIdCguChart',Type=NS['r']+'/chart',Target=f'../charts/chart{i}.xml')
        notes=el('p:notes');nt=el('p:spTree',el('p:cSld',notes));gn=el('p:nvGrpSpPr',nt);el('p:cNvPr',gn,id=1,name='');el('p:cNvGrpSpPr',gn);el('p:nvPr',gn);el('p:grpSpPr',nt)
        ids=set(d.get('source_ids',[]))|{v for values in d.get('object_sources',{}).values() for v in values};sources=[s['location'] for s in deck.get('sources',[]) if s['id'] in ids]
        note='\n\n'.join([d.get('notes',''),'Все данные вымышлены.' if deck.get('demo') else '']+['Источник: '+v for v in sources]+[f'Данные {ptr}: '+', '.join(v) for ptr,v in d.get('object_sources',{}).items()])
        ns=shape(nt,2,'Notes',[0,0,1000,1000],note,12);el('p:ph',ns.find('p:nvSpPr/p:nvPr',NS),type='body',idx=1)
        np=f'ppt/notesSlides/notesSlide{i}.xml';parts[np]=xml(notes);content_type(np,'presentationml.notesSlide')
        nr=el('rel:Relationships');el('rel:Relationship',nr,Id='rIdSlide',Type=NS['r']+'/slide',Target=f'../slides/slide{i}.xml');parts[f'ppt/notesSlides/_rels/notesSlide{i}.xml.rels']=xml(nr)
        el('rel:Relationship',rels,Id='rIdCguNotes',Type=NS['r']+'/notesSlide',Target=f'../notesSlides/notesSlide{i}.xml');parts[f'ppt/slides/_rels/slide{i}.xml.rels']=xml(rels)
        rid='rIdCguSlide'+str(i);el('rel:Relationship',pr,Id=rid,Type=NS['r']+'/slide',Target=f'slides/slide{i}.xml');el('p:sldId',lst,id=255+i,**{tag('r:id'):rid})
        maps.append({'id':d['id'],'kind':kind,'layout_key':layout['key'],'source_slide':layout['source_slide'],'backend':'portable'})
    parts['ppt/presentation.xml']=xml(pres);parts['ppt/_rels/presentation.xml.rels']=xml(pr)
    # Retain only reachable package parts; old slides/notes/charts never leak into output.
    keep={'[Content_Types].xml'};pending=[''];seen=set()
    while pending:
        part=pending.pop()
        if part in seen:continue
        seen.add(part)
        if part:keep.add(part)
        relpath=posixpath.join(posixpath.dirname(part),'_rels',posixpath.basename(part)+'.rels') if part else '_rels/.rels'
        if relpath not in parts:continue
        keep.add(relpath)
        for rel in ET.fromstring(parts[relpath]):
            if rel.get('TargetMode')=='External':continue
            target=posixpath.normpath(posixpath.join(posixpath.dirname(part),rel.get('Target'))).lstrip('/')
            if target not in parts:raise ValueError('Missing package target '+target)
            pending.append(target)
    for item in list(ct):
        if item.get('PartName') and item.get('PartName').lstrip('/') not in keep:ct.remove(item)
    if not any(e.get('Extension')=='xlsx' for e in ct):el('ct:Default',ct,Extension='xlsx',ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    parts['[Content_Types].xml']=xml(ct)
    with ZipFile(out/'output/presentation.pptx','w',ZIP_DEFLATED) as z:
        for name in sorted(keep):z.writestr(name,parts[name])
    (out/'build/template-map.json').write_text(json.dumps(maps,ensure_ascii=False,indent=2),encoding='utf-8')
