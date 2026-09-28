"""Fill original placeholders; retain original layout/master/theme bytes."""
import copy,json,math,posixpath,re
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
from xml.etree import ElementTree as ET
from original_template import SOURCE,SHA,SKILL,load,digest,resolved,shapes,properties,master_style
from audit_template import NS,relationships,audit
from portable_ooxml import el,xml,tag,table,frame,chart_xml,workbook,picture,image_size,NS as ALL_NS
from portable_fonts import Metrics
from number_typography import transform


def check_text(metrics,slot,value):
    size=slot['font_pt'];w=(slot['box_pt'][2]-sum(slot.get('text_insets_pt',[0,0])[:2]))*4/3;lines=0
    for p in value.split('\n'):
        line=''
        for word in p.split():
            if metrics.width(word,size,slot['role'] in ('title','heading','value'))>w:raise ValueError(slot['id']+': word wider than original field')
            trial=(line+' '+word).strip()
            if line and metrics.width(trial,size,slot['role'] in ('title','heading','value'))>w:lines+=1;line=word
            else:line=trial
        lines+=1
    # The original template intentionally uses tight single-line numeric fields.
    # Keep those unchanged and reject additional lines rather than enlarging boxes.
    maxlines=max(1,int(slot['box_pt'][3]/size))
    if lines>maxlines:raise ValueError(slot['id']+': too many lines for original field')

def example(record):
    fields={};seq=0
    for slot in record['slots']:
        role=slot['role'];key=slot['id']
        if role in ('protected','image'):continue
        if role=='chart':fields[key]={'categories':['А','Б','В'],'series':[{'name':'Демо','values':[12,18,24]}],'chart_type':'bar'}
        elif role=='table':fields[key]={'columns':['Этап','Статус','Срок'],'rows':[['Анализ','Готово','2026'],['Пилот','В работе','2027']]}
        elif role=='title':fields[key]=record['name'].replace('цифройё','цифрой') if len(record['name'])<=slot['max_chars'] else 'Обзор'
        elif role=='value':fields[key]='9:00' if ':' in slot['prompt'] else '2026' if slot['prompt']=='2026' else '25' if slot['max_chars']>=2 else '1'
        elif role=='heading':seq+=1;fields[key]='Этап '+str(seq) if slot['max_chars']>=6 else 'Шаг'
        else:fields[key]='Данные для примера' if slot['max_chars']>=18 else 'Демо'
    metrics=Metrics(SKILL)
    for slot in record['slots']:
        value=fields.get(slot['id'])
        if isinstance(value,str):
            try:check_text(metrics,slot,value)
            except ValueError:fields[slot['id']]='1' if slot['role']=='value' else 'Демо'
    return {'id':record['id'],'layout_id':record['id'],'takeaway':record['purpose'],'fields':fields}


def validate(deck,base=Path('.')):
    if not isinstance(deck,dict) or deck.get('schema_version')!='cgu-original-deck/1':raise ValueError('Expected cgu-original-deck/1')
    if set(deck)-{'schema_version','title','demo','slides','sources'}:raise ValueError('Unknown original-deck field')
    if not isinstance(deck.get('title'),str) or not deck['title'].strip():raise ValueError('Nonempty deck title required')
    if not isinstance(deck.get('slides'),list) or not 1<=len(deck['slides'])<=160:raise ValueError('Need 1–160 slides')
    cat={r['id']:r for r in load()['slides'][5:]};seen=set();metrics=Metrics(SKILL)
    for slide in deck['slides']:
        if not isinstance(slide,dict):raise ValueError('Slide must be an object')
        if set(slide)-{'id','layout_id','takeaway','fields','notes','source_ids','repeat_reason'}:raise ValueError('Unknown slide field')
        if not isinstance(slide.get('id'),str) or slide['id'] in seen:raise ValueError('Slide IDs must be unique strings')
        seen.add(slide['id'])
        if slide.get('layout_id') not in cat:raise ValueError('Instructions/icons cannot be executable layouts')
        if not isinstance(slide.get('takeaway'),str) or not slide['takeaway'].strip():raise ValueError('One takeaway required')
        r=cat[slide['layout_id']];slots={s['id']:s for s in r['slots'] if s['editable']};values=slide.get('fields')
        if not isinstance(values,dict) or set(values)-set(slots):raise ValueError('Unknown or protected slot')
        if any(s['required'] and s['id'] not in values for s in slots.values()):raise ValueError('Missing required original placeholder')
        for key,value in values.items():
            from original_style import effective_slot
            s=effective_slot(r,slots[key]);role=s['role'];box=s['box_pt']
            if role=='image':
                if not isinstance(value,dict) or set(value)!={'path','sha256','alt'}:raise ValueError('Image needs path, sha256, alt')
                p=Path(base)/value['path']
                if digest(p.read_bytes())!=value['sha256']:raise ValueError('Image checksum mismatch')
                image_size(p.read_bytes())
            elif role=='chart':
                if not isinstance(value,dict):raise ValueError('Chart must be an object')
                if set(value)-{'categories','series','chart_type'} or value.get('chart_type','bar') not in ('bar','line'):raise ValueError('Chart supports native bar/line only')
                if not 1<=len(value.get('categories',[]))<=8 or not 1<=len(value.get('series',[]))<=3:raise ValueError('Chart capacity exceeded')
                for series in value['series']:
                    if set(series)!={'name','values'} or len(series['values'])!=len(value['categories']) or not all(type(v) in (int,float) and math.isfinite(v) for v in series['values']):raise ValueError('Invalid chart series')
            elif role=='table':
                if not isinstance(value,dict):raise ValueError('Table must be an object')
                if set(value)!={'columns','rows'} or not 1<=len(value['columns'])<=5 or not 1<=len(value['rows'])<=6 or any(len(row)!=len(value['columns']) for row in value['rows']):raise ValueError('Invalid table capacity')
                for row in [value['columns']]+value['rows']:
                    for cell in row:
                        if not isinstance(cell,str):raise ValueError('Table cells must be strings')
                        metrics.check(cell,box[2]*4/3/len(value['columns'])-24,box[3]*4/3/(len(value['rows'])+1)-16,18,False,'original table')
            else:
                if not isinstance(value,str) or not value.strip() or len(value)>s['max_chars']:raise ValueError('Invalid text capacity: '+r['id']+'/'+key)
                check_text(metrics,s,value)
    return deck


def set_text(shape,chain,slot,value):
    size,rpr,body,ppr=properties(chain,slot['role']);size=slot['font_pt']
    for k,v in zip(('lIns','rIns','tIns','bIns'),slot.get('text_insets_pt',[])):body.set(k,str(round(v*12700)))
    old=shape.find('p:txBody',NS)
    if old is not None:shape.remove(old)
    tx=el('p:txBody',shape)
    tx.append(body if body is not None else el('a:bodyPr'))
    # Leave geometry, fill, alignment, margins and paragraph spacing from the original.
    el('a:lstStyle',tx)
    for line in value.split('\n'):
        p=el('a:p',tx)
        if ppr is not None:p.append(copy.deepcopy(ppr))
        run=el('a:r',p);rp=copy.deepcopy(rpr) if rpr is not None else el('a:rPr');rp.tag=tag('a:rPr');rp.set('sz',str(round(size*100)));rp.set('b','0')
        for e in list(rp):
            if e.tag in [tag('a:latin'),tag('a:ea'),tag('a:cs')]:rp.remove(e)
        if slot.get('font_color'):
            for c in list(rp):
                if c.tag in (tag('a:solidFill'),tag('a:gradFill')):rp.remove(c)
            el('a:srgbClr',el('a:solidFill',rp),val=slot['font_color'])
        for typ in ('latin','ea','cs'):el('a:'+typ,rp,typeface='Golos Text SemiBold' if slot['role'] in ('title','heading','value') else 'Golos Text')
        run.append(rp);el('a:t',run).text=line
    transform(tx)


def original_chart(value,slot):
    root=chart_xml(value,['#FF254A','#9A1530','#B5B5B5']);ns=ALL_NS
    layout=root.find('.//c:plotArea/c:layout',ns);manual=el('c:manualLayout',layout)
    for key in ('xMode','yMode','wMode','hMode'):el('c:'+key,manual,val='factor')
    for key,value in [('x',.18),('y',.27),('w',.67),('h',.55)]:el('c:'+key,manual,val=value)
    for e in root.iter():
        if e.get('sz'):e.set('sz',str(round(max(12,slot['font_pt'])*100)))
    return root

def build(deck,destination,base=Path('.'),raw=False):
    if not raw:validate(deck,base)
    if digest(SOURCE.read_bytes())!=SHA:raise ValueError('Source changed')
    cat={r['id']:r for r in load()['slides'][5:]}
    with ZipFile(SOURCE) as z:
        parts={n:z.read(n) for n in z.namelist()};pres=ET.fromstring(parts['ppt/presentation.xml']);lst=pres.find('p:sldIdLst',NS)
        for c in list(lst):lst.remove(c)
        prels=ET.fromstring(parts['ppt/_rels/presentation.xml.rels'])
        for r in list(prels):
            if r.get('Type','').endswith('/slide'):prels.remove(r)
        ct=ET.fromstring(parts['[Content_Types].xml']);metrics=Metrics(SKILL)
        def content(part,mime):el('ct:Override',ct,PartName='/'+part,ContentType='application/vnd.openxmlformats-officedocument.'+mime)
        for i,d in enumerate(deck['slides'],1):
            r=cat[d['layout_id']];lp,mp,tp,roots=resolved(z,r['slide_part']);root=roots[0];tree=root.find('p:cSld/p:spTree',NS);maps=[shapes(x) for x in roots]
            if not raw:
                from original_style import prepare
                prepare(root,maps,r,d.get('fields',{}))
            part=f'ppt/slides/original{i}.xml';rels=ET.fromstring(parts[posixpath.join(posixpath.dirname(r['slide_part']),'_rels',posixpath.basename(r['slide_part'])+'.rels')])
            for rel in list(rels):
                if rel.get('Type','').endswith(('/notesSlide','/slide')):rels.remove(rel)
            inherited=[slot for slot in r['slots'] if slot['idx'] is None and slot['id'] in d.get('fields',{})]
            if inherited:
                layout=roots[1];master=roots[2];newlp=f'ppt/slideLayouts/original{i}.xml';newmp=f'ppt/slideMasters/original{i}.xml'
                for slot in inherited:
                    sh=next(s for s in layout.findall('.//p:sp',NS) if s.find('.//p:cNvPr',NS).get('id')==slot['shape_id']);set_text(sh,[sh],slot,d['fields'][slot['id']])
                lr=ET.fromstring(parts[posixpath.dirname(lp)+'/_rels/'+posixpath.basename(lp)+'.rels'])
                for rel in lr:
                    if rel.get('Type','').endswith('/slideMaster'):rel.set('Target','../slideMasters/'+posixpath.basename(newmp))
                mr=ET.fromstring(parts[posixpath.dirname(mp)+'/_rels/'+posixpath.basename(mp)+'.rels'])
                for rel in list(mr):
                    if rel.get('Type','').endswith('/slideLayout'):mr.remove(rel)
                el('rel:Relationship',mr,Id='rIdOriginalLayout',Type=NS['r']+'/slideLayout',Target='../slideLayouts/'+posixpath.basename(newlp))
                ml=master.find('p:sldLayoutIdLst',NS)
                for e in list(ml):ml.remove(e)
                el('p:sldLayoutId',ml,id=2147483649,**{tag('r:id'):'rIdOriginalLayout'})
                for path,obj,mime,rr in [(newlp,layout,'presentationml.slideLayout+xml',lr),(newmp,master,'presentationml.slideMaster+xml',mr)]:
                    parts[path]=xml(obj);parts[posixpath.dirname(path)+'/_rels/'+posixpath.basename(path)+'.rels']=xml(rr);content(path,mime)
                for rel in rels:
                    if rel.get('Type','').endswith('/slideLayout'):rel.set('Target','../slideLayouts/'+posixpath.basename(newlp))
                masterrid='rIdOriginalMaster'+str(i);el('rel:Relationship',prels,Id=masterrid,Type=NS['r']+'/slideMaster',Target='slideMasters/'+posixpath.basename(newmp));el('p:sldMasterId',pres.find('p:sldMasterIdLst',NS),id=2147484000+i,**{tag('r:id'):masterrid})
            for source_slot in r['slots']:
                from original_style import effective_slot
                slot=effective_slot(r,source_slot) if not raw else source_slot
                if slot['idx'] is None:continue
                key=slot['id']
                if key not in d.get('fields',{}):continue
                value=d['fields'][key];shape=maps[0][slot['idx']];role=slot['role'];sid=slot['shape_id'];b=[v*4/3 for v in slot['box_pt']];rid='rIdOriginal'+slot['idx']
                if role not in ('image','chart','table'):
                    set_text(shape,[m[slot['idx']] for m in maps if slot['idx'] in m]+[master_style(roots[2],slot['placeholder_type'])],slot,value);continue
                index=list(tree).index(shape);tree.remove(shape)
                if role=='image':
                    data=(Path(base)/value['path']).read_bytes();ext='png' if data.startswith(b'\x89PNG') else 'jpeg';asset=f'ppt/media/original-{digest(data)}.{ext}';parts[asset]=data
                    if not any(e.get('Extension')==ext for e in ct):el('ct:Default',ct,Extension=ext,ContentType='image/'+ext)
                    picture(tree,sid,rid,b,*image_size(data),value['alt']);kind='image';dest='../media/'+posixpath.basename(asset)
                    # Fill the original photo window, preserving aspect via explicit center crop.
                    pic=tree[-1];sp=pic.find('p:spPr',NS);xf=sp.find('a:xfrm',NS);xf.find('a:off',NS).attrib.update(x=str(round(b[0]*9525)),y=str(round(b[1]*9525)));xf.find('a:ext',NS).attrib.update(cx=str(round(b[2]*9525)),cy=str(round(b[3]*9525)))
                    iw,ih=image_size(data);ratio=(b[2]/b[3])/(iw/ih);crop=el('a:srcRect',l=round(max(0,1-ratio)*50000),r=round(max(0,1-ratio)*50000),t=round(max(0,1-1/ratio)*50000),b=round(max(0,1-1/ratio)*50000));pic.find('p:blipFill',NS).insert(1,crop);pic.find('p:blipFill/a:stretch/a:fillRect',NS).attrib.update(l='0',r='0',t='0',b='0')
                    for source_shape in [m[slot['idx']] for m in maps if slot['idx'] in m]:
                        geom=source_shape.find('p:spPr/a:prstGeom',NS)
                        if geom is None:geom=source_shape.find('p:spPr/a:custGeom',NS)
                        if geom is not None:
                            old=sp.find('a:prstGeom',NS)
                            if old is not None:sp.remove(old)
                            sp.append(copy.deepcopy(geom));break
                elif role=='table':
                    table(tree,sid,value['columns'],value['rows'],metrics,y=b[1],max_height=b[3],pt=18,row_height=b[3]/(len(value['rows'])+1))
                    obj=tree[-1];xf=obj.find('p:xfrm',NS);xf.find('a:off',NS).set('x',str(round(b[0]*9525)));xf.find('a:ext',NS).set('cx',str(round(b[2]*9525)))
                    for col in obj.findall('.//a:gridCol',NS):col.set('w',str(round(b[2]*9525/len(value['columns']))))
                else:
                    asset=f'ppt/charts/original-{i}-{slot["idx"]}.xml';wb=f'ppt/embeddings/original-{i}-{slot["idx"]}.xlsx';parts[asset]=xml(original_chart(value,slot));parts[wb]=workbook(value['categories'],value['series']);content(asset,'drawingml.chart+xml')
                    if not any(e.get('Extension')=='xlsx' for e in ct):el('ct:Default',ct,Extension='xlsx',ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
                    cr=el('rel:Relationships');el('rel:Relationship',cr,Id='rIdWorkbook',Type=NS['r']+'/package',Target='../embeddings/'+posixpath.basename(wb));parts[posixpath.dirname(asset)+'/_rels/'+posixpath.basename(asset)+'.rels']=xml(cr)
                    el('c:chart',frame(tree,sid,'original-chart',[b[0]+b[2]*.12,b[1]+b[3]*.20,b[2]*.76,b[3]*.68],ALL_NS['c']),**{tag('r:id'):rid});kind='chart';dest='../charts/'+posixpath.basename(asset)
                obj=tree[-1];tree.remove(obj);tree.insert(index,obj)
                # Retain placeholder identity even after conversion to native pic/frame.
                nv=obj.find('p:nvPicPr/p:nvPr' if role=='image' else 'p:nvGraphicFramePr/p:nvPr',NS);nv.append(copy.deepcopy(shape.find('.//p:ph',NS)))
                if role!='table':el('rel:Relationship',rels,Id=rid,Type=NS['r']+'/'+kind,Target=dest)
            if not raw:
                from original_style import finish
                finish(root,r,d.get('fields',{}),metrics)
            parts[part]=xml(root);parts['ppt/slides/_rels/'+posixpath.basename(part)+'.rels']=xml(rels);content(part,'presentationml.slide+xml')
            rid='rIdOriginalSlide'+str(i);el('rel:Relationship',prels,Id=rid,Type=NS['r']+'/slide',Target='slides/'+posixpath.basename(part));el('p:sldId',lst,id=1000+i,**{tag('r:id'):rid})
        parts['ppt/presentation.xml']=xml(pres);parts['ppt/_rels/presentation.xml.rels']=xml(prels)
        # Remove original source slides and their notes, keeping exact corporate inheritance.
        for n in list(parts):
            if re.match(r'ppt/slides/(?:_rels/)?slide\d+\.xml',n) or n.startswith('ppt/notesSlides/'):del parts[n]
        for e in list(ct):
            if e.get('PartName','').lstrip('/') not in parts and e.tag==tag('ct:Override'):ct.remove(e)
        parts['[Content_Types].xml']=xml(ct)
    destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True)
    with ZipFile(destination,'w',ZIP_DEFLATED) as z:
        for n,data in parts.items():z.writestr(n,data)
    report=verify(deck,destination,raw);return report


def verify(deck,pptx,raw=False):
    errors=[];cat={r['id']:r for r in load()['slides'][5:]};a=audit(pptx)
    if a['slide_count']!=len(deck['slides']):errors.append('Slide count mismatch')
    if a['missing_internal_targets']:errors.append('Broken package relationships')
    with ZipFile(SOURCE) as src,ZipFile(pptx) as out:
        for n in src.namelist():
            if n.startswith(('ppt/slideLayouts/','ppt/slideMasters/','ppt/theme/')) and src.read(n)!=out.read(n):errors.append('Corporate inheritance changed: '+n)
        for d,s in zip(deck['slides'],a['slides']):
            r=cat[d['layout_id']]
            if next(v['target'] for v in s['relationships'].values() if v['type']=='slideLayout')!=r['layout_part'] and not any(slot['idx'] is None for slot in r['slots']):errors.append(d['id']+': wrong layout')
            root=ET.fromstring(out.read(s['part']));actual=shapes(root)
            if not raw:
                from original_style import verify_style
                errors.extend(d['id']+': '+e for e in verify_style(root,r))
            for slot in r['slots']:
                if slot['id'] not in d.get('fields',{}):continue
                value=d['fields'][slot['id']];role=slot['role']
                if role not in ('image','chart','table'):
                    sh=actual.get(slot['idx'])
                    if slot['idx'] is None:
                        lp=next(v['target'] for v in s['relationships'].values() if v['type']=='slideLayout');sh=next(sp for sp in ET.fromstring(out.read(lp)).findall('.//p:sp',NS) if sp.find('.//p:cNvPr',NS).get('id')==slot['shape_id'])
                    got='' if sh is None else '\n'.join(''.join(t.text or '' for t in p.findall('.//a:t',NS)) for p in sh.findall('p:txBody/a:p',NS))
                    if got!=value:errors.append(d['id']+': lost native text '+slot['id'])
                    if sh is not None:
                        from number_typography import numeric_errors
                        errors.extend(d['id']+': '+e for e in numeric_errors(sh))
                elif role=='table':
                    obj=next((o for o in root.findall('p:cSld/p:spTree/p:graphicFrame',NS) if o.find('.//p:ph',NS) is not None and o.find('.//p:ph',NS).get('idx','0')==slot['idx']),None)
                    got=[] if obj is None else [[''.join(t.text or '' for t in tc.findall('.//a:t',NS)) for tc in tr.findall('a:tc',NS)] for tr in obj.findall('.//a:tr',NS)]
                    if got!=[value['columns']]+value['rows']:errors.append(d['id']+': changed editable table values')
                elif role=='chart':
                    obj=next((o for o in root.findall('p:cSld/p:spTree/p:graphicFrame',NS) if o.find('.//p:ph',NS) is not None and o.find('.//p:ph',NS).get('idx','0')==slot['idx']),None)
                    cs=None if obj is None else obj.find('.//{'+ALL_NS['c']+'}chart')
                    if cs is None:errors.append(d['id']+': missing editable chart')
                    else:
                        rel=s['relationships'][cs.get(tag('r:id'))];chart=ET.fromstring(out.read(rel['target']));series=chart.findall('.//c:ser',ALL_NS)
                        got=[[float(v.text) for v in ser.findall('c:val/c:numRef/c:numCache/c:pt/c:v',ALL_NS)] for ser in series]
                        if got!=[ser['values'] for ser in value['series']]:errors.append(d['id']+': changed chart values')
                        cats=[[v.text for v in ser.findall('c:cat/c:strRef/c:strCache/c:pt/c:v',ALL_NS)] for ser in series]
                        if any(c!=value['categories'] for c in cats):errors.append(d['id']+': changed chart categories')
                elif role=='image':
                    if not any(digest(out.read(rel['target']))==value['sha256'] for rel in s['relationships'].values() if rel['type']=='image' and not rel['external']):errors.append(d['id']+': image changed')
    return {'status':'passed' if not errors else 'failed','errors':errors,'slides':len(deck['slides']),'inheritance':'original layout/master/theme parts unchanged; inherited text uses independent cloned layout/master' ,'powerpoint':'not-tested','visual_review':'pending'}
