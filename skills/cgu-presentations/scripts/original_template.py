"""Original CGU template inventory and exact placeholder bindings (stdlib only)."""
import copy, hashlib, json, math, re
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET
from audit_template import audit, relationships, NS
SKILL=Path(__file__).resolve().parents[1]
SOURCE=SKILL/'assets/templates/cgu-full.pptx'
REGISTRY=SKILL/'design-system/original-layouts.json'
SHA='ff2b8630acc36d1fd65ae0bda7cbb739ec8405997b2723a38d52efd15611497b'

def digest(data):return hashlib.sha256(data).hexdigest()
def load():return json.loads(REGISTRY.read_text(encoding='utf-8'))
def phkey(shape):
    ph=shape.find('.//p:ph',NS)
    return ph.get('idx','0') if ph is not None else None

def shapes(root):return {phkey(s):s for s in root.findall('.//p:sp',NS) if phkey(s) is not None}
def text(s):return '\n'.join(''.join(t.text or '' for t in p.findall('.//a:t',NS)) for p in s.findall('.//a:p',NS))
def target(z,part,kind):return next((r['target'] for r in relationships(z,part).values() if r['type']==kind),None)
def family(n):
    if n==17:return 'metrics','Показатели','metrics'
    # Named families reflect original structures, not counts of XML shapes.
    groups=[(6,13,'cover','Обложки','reference'),(14,14,'photo-pair','Два фото','comparison'),(15,23,'stages','Этапы','sequence'),(24,29,'path','Маршрут','process'),(30,32,'people','Команда и оргструктура','hierarchy'),(33,33,'message','Сообщение','reference'),(34,39,'devices','Мокапы устройств','reference'),(40,42,'metrics','Показатели','metrics'),(43,45,'blocks','Группы блоков','comparison'),(46,54,'photo-cards','Фото и подписи','profile'),(55,56,'photo-story','Фото и текст','reference'),(57,58,'columns','Колонки','comparison'),(59,65,'charts','Диаграммы','metrics'),(66,67,'tables','Таблицы','comparison'),(68,71,'text','Текст и буллеты','reference'),(72,72,'hero','Акцентный показатель','metrics'),(73,73,'closing','Призыв к действию','decision'),(74,82,'complex','Составные схемы','hierarchy')]
    return next((key,label,intent) for lo,hi,key,label,intent in groups if lo<=n<=hi)

def resolved(z,slide_part):
    lp=target(z,slide_part,'slideLayout');mp=target(z,lp,'slideMaster');tp=target(z,mp,'theme')
    roots=[ET.fromstring(z.read(p)) for p in [slide_part,lp,mp]]
    return lp,mp,tp,roots

def master_style(root,kind):
    style=root.find('p:txStyles/p:'+('titleStyle' if kind in ('title','ctrTitle') else 'bodyStyle' if kind=='body' else 'otherStyle'),NS)
    fake=ET.Element('{'+NS['p']+'}sp');tx=ET.SubElement(fake,'{'+NS['p']+'}txBody');ls=ET.SubElement(tx,'{'+NS['a']+'}lstStyle')
    if style is not None:
        for c in style:ls.append(copy.deepcopy(c))
    return fake

def properties(chain,role):
    run=ET.Element('{'+NS['a']+'}rPr');body=ET.Element('{'+NS['a']+'}bodyPr');ppr=ET.Element('{'+NS['a']+'}pPr')
    def merge(dst,src):
        if src is None:return
        dst.attrib.update(src.attrib)
        for child in src:
            for old in list(dst):
                if old.tag==child.tag:dst.remove(old)
            dst.append(copy.deepcopy(child))
    for shape in reversed(chain):
        merge(body,shape.find('p:txBody/a:bodyPr',NS))
        merge(ppr,shape.find('p:txBody/a:lstStyle/a:lvl1pPr',NS))
        merge(ppr,shape.find('p:txBody/a:p/a:pPr',NS))
        for path in ['p:txBody/a:lstStyle/a:lvl1pPr/a:defRPr','p:txBody/a:p/a:endParaRPr','p:txBody/a:p/a:pPr/a:defRPr','p:txBody/a:p/a:r/a:rPr']:
            merge(run,shape.find(path,NS))
    return int(run.get('sz','4400' if role=='title' else '1800'))/100,run,body,ppr

def inventory():
    if digest(SOURCE.read_bytes())!=SHA:raise ValueError('Original template checksum mismatch')
    raw=audit(SOURCE);records=[]
    with ZipFile(SOURCE) as z:
        for s in raw['slides']:
            n=s['slide_number'];lp,mp,tp,roots=resolved(z,s['part']);maps=[shapes(r) for r in roots];slots=[]
            for key,shape in maps[0].items():
                chain=[m[key] for m in maps if key in m];ph=shape.find('.//p:ph',NS);kind=ph.get('type','obj');prompt=next((text(x).strip() for x in chain if text(x).strip()),'');box=None;box_owner=None
                for owner,x in zip([s['part'],lp,mp],roots):
                    sh=shapes(x).get(key)
                    if sh is None:continue
                    xf=sh.find('p:spPr/a:xfrm',NS)
                    if xf is not None:
                        off,ext=xf.find('a:off',NS),xf.find('a:ext',NS)
                        if off is not None and ext is not None:box=[int(off.get('x'))/12700,int(off.get('y'))/12700,int(ext.get('cx'))/12700,int(ext.get('cy'))/12700];box_owner=owner;break
                if box is None:continue
                protected=kind in ('ftr','sldNum','dt') or (not prompt and box[1]<140 and box[3]<100 and kind!='title') or key=='4294967295' or (n==16 and key in ('34','35','39','43'))
                role='image' if kind=='pic' else 'chart' if kind=='chart' else 'table' if kind=='tbl' else 'title' if kind in ('title','ctrTitle') else 'heading' if re.search('заголов|наименован',prompt,re.I) else 'value' if (prompt=='>XX' or re.fullmatch(r'\d\d:\d\d',prompt)) else 'value' if re.fullmatch(r'[\d\s.,%+−\-а-яА-Я]+',prompt) and re.search(r'\d',prompt) and len(prompt)<24 else 'body'
                if protected:role='protected'
                size,_,bp,_=properties(chain+[master_style(roots[2],kind)],role)
                # Explicitly conservative estimate; physical font metrics checked at build time.
                lines=max(1,int(box[3]/(size*1.15)));limit=max(1,int(box[2]/(size*.60))*lines)
                if box[0]<0:limit=min(limit,8)
                slots.append({'id':'ph-'+key,'idx':key,'shape_id':shape.find('.//p:cNvPr',NS).get('id'),'role':role,'placeholder_type':kind,'required':role not in ('protected','image'),'prompt':prompt,'box_pt':[round(v,3) for v in box],'geometry_owner':box_owner,'font_pt':size,'text_insets_pt':[int(bp.get(k,'91440' if k in ('lIns','rIns') else '45720'))/12700 for k in ('lIns','rIns','tIns','bIns')],'max_chars':limit,'max_lines_estimate':lines,'editable':not protected,'source_chain':[p for p,m in zip([s['part'],lp,mp],maps) if key in m]})
            if n>=6:
                for sh in roots[1].findall('.//p:sp',NS):
                    if phkey(sh) is not None or not text(sh).strip():continue
                    info=sh.find('.//p:cNvPr',NS);xf=sh.find('p:spPr/a:xfrm',NS);off=xf.find('a:off',NS);ext=xf.find('a:ext',NS);box=[int(off.get('x'))/12700,int(off.get('y'))/12700,int(ext.get('cx'))/12700,int(ext.get('cy'))/12700];size,_,_,_=properties([sh],'heading')
                    slots.append({'id':'layout-'+info.get('id'),'idx':None,'shape_id':info.get('id'),'role':'heading','placeholder_type':'non-placeholder','required':True,'prompt':text(sh),'box_pt':box,'geometry_owner':lp,'font_pt':size,'max_chars':max(1,int(box[2]/size/.6)),'max_lines_estimate':1,'editable':True,'source_chain':[lp]})
            classification='instructions' if n<=3 else 'icons' if n<=5 else 'candidate'
            fam,label,intent=family(n) if n>=6 else (classification,classification,'reference')
            lname=roots[1].find('p:cSld',NS).get('name','')
            # Structural fingerprint excludes placeholder IDs, prompt content and variant colors.
            structure=[(v['role'],v['box_pt']) for v in slots if v['role']!='protected']
            records.append({'id':f'original-{n:02d}','source_slide':n,'classification':classification,'name':lname,'family':fam,'family_label':label,'intent':intent,'purpose':lname,'selection':f'{label}: выбирайте по содержанию и вместимости полей; вариант «{lname}» сохраняет исходную геометрию.','slide_part':s['part'],'layout_part':lp,'master_part':mp,'theme_part':tp,'slots':slots,'structure_fingerprint':digest(json.dumps(structure,sort_keys=True).encode()),'exact_source_fingerprint':digest(z.read(s['part'])+z.read(lp)+z.read(mp)),'status':'candidate' if n>=6 else 'inventory','preview':f'previews/slide-{n:02d}.png','example_preview':f'examples/slide-{n-5:02d}.png' if n>=6 else None,'editable_counts':{r:sum(v['role']==r for v in slots) for r in ['title','heading','body','value','image','table','chart']},'ownership':{'slide':{'part':s['part'],'objects':len(list(roots[0].find('p:cSld/p:spTree',NS)))-2},'layout':{'part':lp,'objects':len(list(roots[1].find('p:cSld/p:spTree',NS)))-2},'master':{'part':mp,'objects':len(list(roots[2].find('p:cSld/p:spTree',NS)))-2}},'colors':{'slide':s['explicit_rgb_colors'],'layout':next(l['explicit_rgb_colors'] for l in raw['layouts'] if l['part']==lp)},'limitations':['Лимит символов предварительный; проверяется ширина и высота текста.','Не менять исходные координаты, изображения бренда и фоновую графику.','Изображения по умолчанию сохраняют исходное заполнение; замена требует явного поля.']})
        groups={}
        for r in records[5:]:groups.setdefault(r['structure_fingerprint'],[]).append(r['id'])
        for r in records:r['geometry_variants']=[i for i in groups.get(r['structure_fingerprint'],[]) if i!=r['id']]
        parts=[]
        for label in ['layouts','masters','themes']:
            for part in raw[label]:
                p=part['part'];parts.append({'part':p,'kind':label,'name':part['name'],'sha256':digest(z.read(p)),'relationships':relationships(z,p),'fonts':part['fonts'],'explicit_rgb_colors':part['explicit_rgb_colors'],'objects':part['fields']})
    return {'schema_version':'cgu-original-catalog/1','source_sha256':SHA,'counts':{'slides':82,'layouts':77,'masters':12,'candidates':77,'families':len({r['family'] for r in records[5:]}),'distinct_geometry_signatures':len(groups)},'slides':records,'parts':parts,'limits':['Geometry-signature equality is not proof of identical visual design.','Family classification requires visual review; status does not imply designer approval.']}

def select(intent,fields=1,images=0,text_length=0,previous=None,limit=3,data_type=None,allow_experimental=False,**context):
    from planning import rank
    previous_layouts=list(context.get('previous_layouts',[]))
    if previous and not previous_layouts:
        previous_layouts=[r['id'] for r in load()['slides'][5:] if r['family']==previous][:1]
    return rank(dict(intent=intent,fields=fields,images=images,text_length=text_length,data_type=data_type or 'text',**context),previous_layouts,context.get('next_layout'),allow_experimental,context.get('feedback',[]))[:limit]

if __name__=='__main__':
    REGISTRY.write_text(json.dumps(inventory(),ensure_ascii=False,indent=2),encoding='utf-8')
    print(REGISTRY)
