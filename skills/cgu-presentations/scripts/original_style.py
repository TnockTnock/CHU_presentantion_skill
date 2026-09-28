"""Reviewed presentation overrides; source template parts remain immutable.

Coordinates are pt. Figma references use 1920x1080 px (0.75 pt per px).
Only reviewed compositions receive overrides; no global rounding/recoloring.
"""
import copy
from original_template import NS
from portable_ooxml import el,tag

REVIEWED={12:'cover',14:'photo-pair',16:'four-stages',18:'three-stages'}

def field_style(number,key):
    if number==12 and key=='ph-0':return {'box_pt':[126.341,379.189,646.2,132],'font_pt':66,'max_chars':36}
    if number==12 and key=='ph-11':return {'box_pt':[126.341,522.814,646.2,72],'font_pt':24,'max_chars':90}
    if number==14:
        for x,image,heading,body in [(75,'ph-62','ph-63','ph-64'),(729,'ph-65','ph-72','ph-73')]:
            if key==image:return {'box_pt':[x,195,636,390]}
            if key==heading:return {'box_pt':[x,609,636,36],'font_pt':24,'text_insets_pt':[0,0,0,0]}
            if key==body:return {'box_pt':[x,657,636,72],'font_pt':18,'text_insets_pt':[0,0,0,0]}
    if number==16:
        for x,y,img,heading,value,body in [(75,195,'ph-34','ph-11','ph-12','ph-22'),(729,195,'ph-35','ph-36','ph-37','ph-38'),(75,460.5,'ph-39','ph-40','ph-41','ph-42'),(729,460.5,'ph-43','ph-44','ph-45','ph-46')]:
            if key==img:return {'box_pt':[x,y,636,247.5]}
            if key==heading:return {'box_pt':[x+33,y+88.5,563.25,32],'font_pt':24,'text_insets_pt':[0,0,0,0]}
            if key==value:return {'box_pt':[x+33,y+33,36,36],'font_pt':19.5,'text_insets_pt':[0,0,0,0]}
            if key==body:return {'box_pt':[x+33,y+124.5,563.25,98],'font_pt':16.5,'text_insets_pt':[0,0,0,0]}
    if number==18:
        for x,h,b,v in [(75,'ph-11','ph-22','ph-14'),(510.75,'ph-16','ph-23','ph-17'),(946.5,'ph-19','ph-24','ph-20')]:
            if key==h:return {'box_pt':[x,198.75,417.75,36],'font_pt':24,'text_insets_pt':[0,0,0,0]}
            if key==b:return {'box_pt':[x,247,417.75,210],'font_pt':16.5,'text_insets_pt':[0,0,0,0]}
            if key==v:return {'box_pt':[x,487,417.75,90],'font_pt':76.5,'font_color':'F00938','text_insets_pt':[0,0,0,0]}
    return {}

def effective_slot(record,slot):
    s=copy.deepcopy(slot);s.update(field_style(record['source_slide'],slot['id']));return s

def set_box(shape,box):
    sp=shape.find('p:spPr',NS)
    if sp is None:sp=el('p:spPr',shape)
    xf=sp.find('a:xfrm',NS)
    if xf is not None:sp.remove(xf)
    xf=el('a:xfrm');sp.insert(0,xf);el('a:off',xf,x=round(box[0]*12700),y=round(box[1]*12700));el('a:ext',xf,cx=round(box[2]*12700),cy=round(box[3]*12700))

def solid(shape,color):
    sp=shape.find('p:spPr',NS)
    for c in list(sp):
        if c.tag in (tag('a:solidFill'),tag('a:blipFill'),tag('a:gradFill'),tag('a:noFill')):sp.remove(c)
    el('a:srgbClr',el('a:solidFill',sp),val=color)

def round_geometry(shape,radius,box):
    sp=shape.find('p:spPr',NS)
    for c in list(sp):
        if c.tag in (tag('a:prstGeom'),tag('a:custGeom')):sp.remove(c)
    g=el('a:prstGeom',sp,prst='roundRect');el('a:gd',el('a:avLst',g),name='adj',fmla='val '+str(round(radius/min(box[2:])*100000)))

def prepare(root,maps,record,fields):
    # Some renderers lose shape geometry inherited by an empty pic placeholder.
    # Materialize only geometry/solid fill/line, never cross-part blip relations.
    for key,shape in maps[0].items():
        sp=shape.find('p:spPr',NS)
        if sp is None:sp=el('p:spPr',shape)
        for parent in maps[1:]:
            if key not in parent:continue
            src=parent[key].find('p:spPr',NS)
            if src is None:continue
            for c in src:
                if c.tag in (tag('a:prstGeom'),tag('a:custGeom'),tag('a:solidFill'),tag('a:ln')) and sp.find(c.tag) is None:
                    if c.tag in (tag('a:prstGeom'),tag('a:custGeom')) and any(sp.find(tag(t)) is not None for t in ['a:prstGeom','a:custGeom']):continue
                    sp.append(copy.deepcopy(c))
    # A pic placeholder is rendered as a rectangular picture slot by LibreOffice,
    # even with explicit roundRect. Unfilled solid surfaces must be ordinary shapes.
    for key,shape in maps[0].items():
        ph=shape.find('.//p:ph',NS);sp=shape.find('p:spPr',NS)
        if ph is None or ph.get('type')!='pic' or 'ph-'+key in fields:continue
        chain=[m[key] for m in maps if key in m]
        if any(sh.find('p:spPr/a:blipFill',NS) is not None for sh in chain):continue
        if sp.find('a:solidFill',NS) is None or sp.find('a:prstGeom',NS) is None:continue
        slot=next(v for v in record['slots'] if v['idx']==key)
        set_box(shape,slot['box_pt'])
        shape.find('p:nvSpPr/p:nvPr',NS).remove(ph)
        shape.find('p:nvSpPr/p:cNvPr',NS).set('name','original-surface-ph-'+key)
    n=record['source_slide']
    if n==16:
        cs=root.find('p:cSld',NS);old=cs.find('p:bg',NS)
        if old is not None:cs.remove(old)
        bg=el('p:bg');cs.insert(0,bg);el('a:srgbClr',el('a:solidFill',el('p:bgPr',bg)),val='F3F2F2')
        for key in ['34','35','39','43']:
            box=field_style(n,'ph-'+key)['box_pt'];set_box(maps[0][key],box);round_geometry(maps[0][key],24,box);solid(maps[0][key],'FFFFFF')
        for key in ['12','37','41','45']:solid(maps[0][key],'F7849B')
    for slot in record['slots']:
        patch=field_style(n,slot['id'])
        if patch and slot['idx'] in maps[0]:set_box(maps[0][slot['idx']],patch['box_pt'])

def finish(root,record,fields,metrics):
    if record['source_slide']!=18:return
    # Auto-layout analogue: number follows its own content, aligned across columns.
    shapes={s.find('.//p:ph',NS).get('idx','0'):s for s in root.findall('p:cSld/p:spTree/p:sp',NS) if s.find('.//p:ph',NS) is not None}
    max_lines=1
    for key in ['ph-22','ph-23','ph-24']:
        text=fields.get(key,'');lines=0
        for para in text.split('\n'):
            line=''
            for word in para.split():
                trial=(line+' '+word).strip()
                if line and metrics.width(trial,16.5,False)>417.75*4/3:lines+=1;line=word
                else:line=trial
            lines+=1
        max_lines=max(max_lines,lines)
    y=min(487,247+max_lines*16.5*1.2+24)
    for key,x in [('14',75),('17',510.75),('20',946.5)]:set_box(shapes[key],[x,y,417.75,90])

def verify_style(root,record):
    errors=[]
    if record['source_slide']==16:
        for key in ('34','35','39','43'):
            sh=next((s for s in root.findall('p:cSld/p:spTree/p:sp',NS) if s.find('p:nvSpPr/p:cNvPr',NS).get('name')=='original-surface-ph-'+key),None)
            if sh is None:errors.append('Missing native card surface '+key);continue
            geom=sh.find('p:spPr/a:prstGeom',NS)
            if geom is None or geom.get('prst')!='roundRect':errors.append('Card lost rounded geometry '+key)
            if sh.find('.//p:ph',NS) is not None:errors.append('Card remains a picture placeholder '+key)
            color=sh.find('p:spPr/a:solidFill/a:srgbClr',NS)
            if color is None or color.get('val')!='FFFFFF':errors.append('Card surface must be white '+key)
    return errors
