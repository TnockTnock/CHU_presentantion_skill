#!/usr/bin/env python3
"""Create a LOCAL searchable PDF/PPTX reference library. Never modifies sources.

Run with Python plus optional pypdf and Pillow. Output contains internal content;
keep it outside git or in ignored work/. No uploads or automatic approval.
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import hashlib
import html
import json
from pathlib import Path
import subprocess
try:
    from pypdf import PdfReader
    from PIL import Image, ImageDraw
except ImportError as e:
    raise SystemExit("Reference catalog requires pypdf and Pillow; install these optional packages in your Python environment.") from e
from run import portable_paths
from audit_template import audit

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def catalog(source, out, runtime=None):
    source,out=Path(source).resolve(),Path(out).resolve()
    paths=portable_paths(runtime,render=True)
    if out == source or source in out.parents:
        raise ValueError('Output must be outside source folder')
    out.mkdir(parents=True,exist_ok=True)
    if any(out.iterdir()): raise ValueError('Use an empty output directory')
    (out/'previews').mkdir();(out/'rendered').mkdir();(out/'sheets').mkdir()
    allfiles=sorted(p for p in source.rglob('*') if p.is_file())
    docs=[];byhash={};ignored=Counter()
    for p in allfiles:
        if p.name.startswith('~$') or p.suffix.lower() not in ('.pdf','.pptx'):
            ignored[p.suffix.lower()]+=1;continue
        digest=sha(p)
        if digest in byhash:
            byhash[digest]['aliases'].append(str(p.relative_to(source)));continue
        d={'id':f'doc-{len(docs)+1:03d}','path':str(p.relative_to(source)),'sha256':digest,'format':p.suffix.lower()[1:],'aliases':[],'pages':[],'status':'unreviewed'}
        docs.append(d);byhash[digest]=d
    for d in docs:
        p=source/d['path']
        if d['format']=='pptx':
            try:
                d['ooxml']=audit(p)
                dest=out/'rendered'/d['id'];dest.mkdir()
                profile=(dest/'lo-profile').as_uri()
                subprocess.run([str(paths['soffice']),f'-env:UserInstallation={profile}','--headless','--convert-to','pdf','--outdir',str(dest),str(p)],check=True,capture_output=True,timeout=180)
                d['pdf']=str((dest/(p.stem+'.pdf')).relative_to(out))
            except Exception as e:
                d['error']=str(e);continue
        else:d['pdf_external']=str(p)
    def render(d):
        if 'error' in d:return
        pdf=Path(d['pdf_external']) if 'pdf_external' in d else out/d['pdf']
        try:
            reader=PdfReader(pdf)
            subprocess.run([str(paths['pdftoppm']),'-scale-to','960','-jpeg','-jpegopt','quality=80',str(pdf),str(out/'previews'/d['id'])],check=True,capture_output=True,timeout=180)
            previews=sorted((out/'previews').glob(d['id']+'-*.jpg'),key=lambda p:int(p.stem.rsplit('-',1)[1]))
            if len(previews)!=len(reader.pages):raise ValueError('Render/page count mismatch')
            for i,(page,preview) in enumerate(zip(reader.pages,previews),1):
                im=Image.open(preview).convert('RGB')
                d['pages'].append({'page':i,'text':page.extract_text() or '', 'preview':str(preview.relative_to(out)), 'width_pt':float(page.mediabox.width),'height_pt':float(page.mediabox.height),'pixel_hash':hashlib.sha256(im.tobytes()).hexdigest(),'review':'unreviewed'})
        except Exception as e:d['error']=str(e)
    with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(render,docs))
    pages=[(d,p) for d in docs for p in d['pages']];seen={};unique=[]
    for d,p in pages:
        key=p['pixel_hash']
        if key in seen:p['same_pixels_as']=seen[key]
        else:seen[key]=f"{d['id']}:{p['page']}";unique.append((d,p))
    for start in range(0,len(unique),20):
        sheet=Image.new('RGB',(1600,1050),'#dddddd');draw=ImageDraw.Draw(sheet)
        for j,(d,p) in enumerate(unique[start:start+20]):
            im=Image.open(out/p['preview']);im.thumbnail((390,185));x=(j%4)*400;y=(j//4)*210
            sheet.paste(im,(x,y));draw.text((x+5,y+187),f"{d['id']} / {p['page']}",fill='black')
        sheet.save(out/'sheets'/f'sheet-{start//20+1:02d}.jpg',quality=90)
    summary={'input_documents':sum(1 for p in allfiles if p.suffix.lower() in ('.pdf','.pptx')),'unique_documents':len(docs),'rendered_pages':len(pages),'unique_pixel_pages':len(unique),'errors':sum('error' in d for d in docs),'other_files':dict(ignored)}
    data={'schema_version':'cgu-local-references/1','source_root':str(source),'summary':summary,'documents':docs}
    (out/'catalog.json').write_text(json.dumps(data,ensure_ascii=False,indent=2), encoding="utf-8")
    cards=[]
    for d,p in unique:
        caption=f"{d['path']} · слайд {p['page']} · {d['id']}"
        cards.append('<article data-search="'+html.escape(caption+' '+p['text'],quote=True)+'"><a href="'+html.escape(p['preview'])+'"><img loading="lazy" src="'+html.escape(p['preview'])+'"></a><p>'+html.escape(caption)+'</p><details><summary>Текст и статус</summary><p>Референс. Не подключён автоматически к сборщику.</p><pre>'+html.escape(p['text'])+'</pre></details></article>')
    (out/'index.html').write_text('<!doctype html><html lang="ru"><meta charset="utf-8"><title>Библиотека референсов ЦГУ</title><style>body{font:16px system-ui;margin:32px;background:#f3f2f2;color:#222}input{padding:14px;width:90%;margin:20px 0}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:24px}article{background:white;padding:12px}img{width:100%}pre{white-space:pre-wrap}p{line-height:1.4}</style><h1>Библиотека референсов ЦГУ</h1><p>Локальные материалы. '+str(len(unique))+' уникальных изображений страниц. Поиск по названиям и извлечённому тексту.</p><input aria-label="Поиск" placeholder="Поиск: процесс, план, результат…"><main>'+''.join(cards)+'</main><script>document.querySelector("input").oninput=e=>{let q=e.target.value.toLocaleLowerCase();document.querySelectorAll("article").forEach(a=>a.hidden=!a.dataset.search.toLocaleLowerCase().includes(q))}</script></html>', encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False))
    return data

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('source');ap.add_argument('--out',required=True);ap.add_argument('--runtime');a=ap.parse_args();catalog(a.source,a.out,a.runtime)
