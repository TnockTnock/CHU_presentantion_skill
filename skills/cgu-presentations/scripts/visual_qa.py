"""Conservative native-object QA. Warnings require visual review, not auto approval."""
import json
import re
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET
from audit_template import audit,NS,relationships
from portable_ooxml import image_size
from portable_fonts import Metrics

def inspect(pptx):
    skill=Path(__file__).resolve().parents[1];metrics=Metrics(skill)
    tokens=json.loads((skill/'design-system/tokens.json').read_text(encoding='utf-8'));allowed={c.lstrip('#').upper() for c in tokens['colors'].values()}
    errors=[];warnings=[];slides=[]
    with ZipFile(pptx) as z:
        for n,desc in enumerate(audit(pptx)['slides'],1):
            root=ET.fromstring(z.read(desc['part']));texts=[]
            for sp in root.findall('.//p:sp',NS):
                nv=sp.find('.//p:cNvPr',NS);name=nv.get('name','');xf=sp.find('p:spPr/a:xfrm',NS);tx=sp.find('p:txBody',NS)
                if tx is None or xf is None:continue
                text='\n'.join(''.join(t.text or '' for t in p.findall('.//a:t',NS)) for p in tx.findall('a:p',NS))
                if not text.strip():continue
                off=xf.find('a:off',NS);ext=xf.find('a:ext',NS);b=[int(off.get('x'))/9525,int(off.get('y'))/9525,int(ext.get('cx'))/9525,int(ext.get('cy'))/9525]
                sizes=[int(p.get('sz'))/100 for p in tx.findall('.//a:rPr',NS) if p.get('sz')];pt=max(sizes or [24]);heading=any(f.get('typeface')=='Golos Text SemiBold' for f in tx.findall('.//a:latin',NS))
                bp=tx.find('a:bodyPr',NS);padx=sum(int(bp.get(k,'0')) for k in ('lIns','rIns'))/9525;pady=sum(int(bp.get(k,'0')) for k in ('tIns','bIns'))/9525
                try:metrics.check(text,b[2]-padx,b[3]-pady,pt,heading,name)
                except ValueError as e:errors.append({'slide':n,'object':name,'issue':str(e)})
                if min(b[:2])<0 or b[0]+b[2]>1921 or b[1]+b[3]>1081:errors.append({'slide':n,'object':name,'issue':'outside slide'})
                authored=int(nv.get('id','0'))>=1000
                if authored and name not in ('footer','page-number') and min(sizes or [24])<18:errors.append({'slide':n,'object':name,'issue':'content text below 18 pt'})
                if authored:
                    for c in sp.findall('.//a:srgbClr',NS):
                        if c.get('val','').upper() not in allowed:errors.append({'slide':n,'object':name,'issue':'non-brand color '+str(c.get('val'))})
                if re.search(r'\{\{.+?\}\}|\bLOREM IPSUM\b|\bTODO\b|ВСТАВЬТЕ ТЕКСТ',text,re.I):errors.append({'slide':n,'object':name,'issue':'unreplaced placeholder'})
                texts.append((name,b))
            for i,(name,b) in enumerate(texts):
                for other,c in texts[i+1:]:
                    ix=min(b[0]+b[2],c[0]+c[2])-max(b[0],c[0]);iy=min(b[1]+b[3],c[1]+c[3])-max(b[1],c[1])
                    if ix>4 and iy>4:warnings.append({'slide':n,'objects':[name,other],'issue':'text boxes intersect; inspect rendered text'})
            # Repeated aligned rows: compare vertical gaps only among equal-size boxes.
            aligned={}
            for name,b in texts:
                aligned.setdefault(tuple(round(v) for v in (b[0],b[2],b[3])),[]).append(b[1])
            for ys in aligned.values():
                ys=sorted(ys)
                if len(ys)>=3:
                    gaps=[ys[i+1]-ys[i] for i in range(len(ys)-1)]
                    if max(gaps)-min(gaps)>12:warnings.append({'slide':n,'issue':'uneven repeated-row spacing; inspect intended grouping'})
            rels=relationships(z,desc['part'])
            for pic in root.findall('.//p:pic',NS):
                blip=pic.find('.//a:blip',NS);ext=pic.find('p:spPr/a:xfrm/a:ext',NS)
                if blip is not None and ext is not None:
                    rid=blip.get('{'+NS['r']+'}embed')
                    if rid in rels and not rels[rid]['external']:
                        try:
                            w,h=image_size(z.read(rels[rid]['target']));ratio=int(ext.get('cx'))/int(ext.get('cy'))
                            if abs(ratio/(w/h)-1)>0.02:errors.append({'slide':n,'issue':'image aspect ratio changed'})
                            if min(w,h)<100:warnings.append({'slide':n,'issue':'low-resolution image'})
                        except ValueError:pass
                crop=pic.find('.//a:srcRect',NS)
                if crop is not None and any(int(v) for v in crop.attrib.values()):warnings.append({'slide':n,'issue':'cropped image: inspect face/logo'})
            slides.append({'slide':n,'text_objects':len(texts),'visual_review':'pending'})
    return {'errors':errors,'warnings':warnings,'slides':slides,'limitations':['Native text fit uses bundled font advances; actual line breaks require PNG review.','Uneven spacing and connector crossings require visual inspection; text intersections are conservative candidates.','Existing template art is exempt from new-object color rules.']}

def contact_sheet(preview):
    # Optional Pillow is for arranging rendered page thumbnails, never drawing slide artwork.
    try:from PIL import Image,ImageDraw
    except ImportError:return {'status':'unavailable','reason':'Pillow is optional; HTML contact sheet is available'}
    paths=sorted(Path(preview).glob('slide-*.png'),key=lambda p:int(p.stem.split('-')[-1]));sheets=[]
    for start in range(0,len(paths),12):
        batch=paths[start:start+12];im=Image.new('RGB',(1440,((len(batch)+2)//3)*295),'#eeeeee');draw=ImageDraw.Draw(im)
        for j,p in enumerate(batch):
            tile=Image.open(p).convert('RGB');tile.thumbnail((470,265));x=j%3*480;y=j//3*295;im.paste(tile,(x,y));draw.text((x+8,y+268),str(start+j+1),fill='black')
        dest=Path(preview)/f'contact-sheet-{start//12+1:02}.jpg';im.save(dest,quality=90);sheets.append(str(dest))
    return {'status':'created','files':sheets}

def html_contact(preview):
    paths=sorted(Path(preview).glob('slide-*.png'),key=lambda p:int(p.stem.split('-')[-1]))
    html='<!doctype html><meta charset="utf-8"><title>Контактный лист</title><style>body{font:16px sans-serif}main{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}img{width:100%}</style><h1>Контактный лист</h1><main>'
    html+=''.join(f'<figure><a href="{p.name}"><img src="{p.name}"></a><figcaption>{i}</figcaption></figure>' for i,p in enumerate(paths,1))+'</main>'
    (Path(preview)/'contact-sheet.html').write_text(html,encoding='utf-8')
