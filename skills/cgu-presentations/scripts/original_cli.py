"""CLI artifacts for exact original-template adapters."""
import copy,csv,html,json,os,shutil,subprocess
from pathlib import Path
from xml.sax.saxutils import escape
from original_template import SKILL,SOURCE,load,digest
from original_build import build,validate
from original_style import effective_slot

def dump(path,value):Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
def render(pptx,out,scale=1440):
    from run import portable_paths
    from visual_qa import contact_sheet,html_contact
    paths=portable_paths(render=True);out=Path(out).resolve();out.mkdir(parents=True,exist_ok=True);conf=out/'fonts.conf'
    conf.write_text('<fontconfig><dir>'+escape(str(SKILL/'assets/fonts'))+'</dir><cachedir>'+escape(str(out/'font-cache'))+'</cachedir><alias><family>Golos Text DemiBold</family><prefer><family>Golos Text SemiBold</family></prefer></alias></fontconfig>',encoding='utf-8');env=os.environ.copy();env['FONTCONFIG_FILE']=str(conf)
    subprocess.run([str(paths['soffice']),'-env:UserInstallation='+(out/'lo-profile').as_uri(),'--headless','--convert-to','pdf','--outdir',str(out),str(Path(pptx).resolve())],env=env,check=True,timeout=180)
    pdf=out/(Path(pptx).stem+'.pdf');preview=out/'preview';preview.mkdir(exist_ok=True)
    subprocess.run([str(paths['pdftoppm']),'-scale-to',str(scale),'-png',str(pdf),str(preview/'slide')],env=env,check=True,timeout=180)
    html_contact(preview);contact_sheet(preview)
    return pdf

def diversity(deck):
    cat={r['id']:r for r in load()['slides']};seq=[cat[s['layout_id']]['family'] for s in deck['slides']];runs=[];start=0
    for i in range(1,len(seq)+1):
        if i==len(seq) or seq[i]!=seq[start]:
            if i-start>=3:runs.append({'slides':[s['id'] for s in deck['slides'][start:i]],'family':seq[start],'status':'justified' if all(s.get('repeat_reason') for s in deck['slides'][start:i]) else 'warning'})
            start=i
    return {'families':list(dict.fromkeys(seq)),'runs':runs,'warnings':sum(r['status']=='warning' for r in runs)}

def build_project(spec,out,do_render=True):
    spec=Path(spec).resolve();out=Path(out).resolve()
    if out.exists() and any(out.iterdir()):raise ValueError('Use empty output directory')
    deck=json.loads(spec.read_text(encoding='utf-8'));validate(deck,spec.parent)
    for folder in ['output','content','qa']:(out/folder).mkdir(parents=True,exist_ok=True)
    report=build(deck,out/'output/presentation.pptx',spec.parent)
    if report['errors']:raise ValueError('; '.join(report['errors']))
    saved=copy.deepcopy(deck)
    for slide in saved['slides']:
        for value in slide['fields'].values():
            if isinstance(value,dict) and 'path' in value:
                src=(spec.parent/value['path']).resolve();dst=out/'content/assets'/(digest(src.read_bytes())+src.suffix);dst.parent.mkdir(exist_ok=True);shutil.copy2(src,dst);value['path']='assets/'+dst.name
    dump(out/'content/deck-spec.json',saved);dump(out/'content/sources.json',deck.get('sources',[]));dump(out/'qa/structural.json',report);dump(out/'qa/visual-diversity.json',diversity(deck))
    (out/'output/scenario.md').write_text('# '+deck.get('title','Презентация')+'\n\n'+'\n\n'.join('## '+s['id']+'\n'+s['takeaway']+'\n'+s.get('notes','') for s in deck['slides']),encoding='utf-8')
    if do_render:
        render(out/'output/presentation.pptx',out/'output');report['rendered']=True
    else:report['rendered']=False
    report.update(backend='original-portable',pptx_sha256=digest((out/'output/presentation.pptx').read_bytes()),visual_review='pending');dump(out/'qa/run.json',report);print(json.dumps(report,ensure_ascii=False));return out

def catalog(out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True);data=load();dump(out/'catalog.json',data)
    cards=[]
    for r in data['slides']:
        slots=''.join('<tr><td>'+html.escape(s['id'])+'</td><td>'+s['role']+'</td><td>'+str(s['box_pt'])+'</td><td>'+str(s['font_pt'])+' pt</td><td>'+str(s['max_chars'])+'</td><td>'+('да' if s['required'] else 'нет')+'</td></tr>' for s in [effective_slot(r,v) for v in r['slots']])
        image=r['example_preview'] if r['classification']=='candidate' else r['preview']
        cards.append('<article data-search="'+html.escape(str(r['source_slide'])+' '+r['name']+' '+r['family']+' '+r['intent'],quote=True)+'"><h2>'+str(r['source_slide'])+'. '+html.escape(r['name'])+'</h2><p>'+r['family']+' · '+r['status']+' · visual: '+r.get('visual_status','not-reviewed')+'</p><a href="'+image+'"><img loading="lazy" src="'+image+'"></a><p>'+html.escape(r['selection'])+'</p><details><summary>Поля, ограничения и наследование</summary><p>'+html.escape(r['layout_part']+' → '+r['master_part']+' → '+r['theme_part'])+'</p><p>Варианты с одинаковой геометрией: '+html.escape(', '.join(r['geometry_variants']) or 'нет')+'</p><p>Исходный пустой слайд: <a href="'+r['preview']+'">превью</a>. Исходные части сохраняются. В таблице показаны итоговые области с учётом документированных правок по Figma.</p><table><tr><th>Поле</th><th>Роль</th><th>Область, pt</th><th>Шрифт</th><th>Символы*</th><th>Обязательно</th></tr>'+slots+'</table><p>* Консервативная оценка. Ширина, переносы и рендер проверяются отдельно.</p><pre>'+html.escape(json.dumps(r['ownership'],ensure_ascii=False,indent=2))+'</pre></details></article>')
    (out/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>Оригинальный шаблон ЦГУ</title><style>body{font:16px system-ui;margin:32px;background:#f4f4f4}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(480px,1fr));gap:24px}article{background:white;padding:24px;border-radius:24px}img{width:100%}table{font-size:12px;border-collapse:collapse}td,th{border:1px solid #ddd;padding:6px}input{padding:12px;width:90%}pre{white-space:pre-wrap}</style><h1>Каталог оригинального шаблона ЦГУ</h1><p>82 страницы · 77 макетов · 12 образцов. Страницы 1–3: инструкции; 4–5: иконки; 6–82: кандидаты. Названия и номера не равны уникальным дизайнам. Превью кандидатов заполнены нейтральными тестовыми данными.</p><p>Обновление по Figma: см. <a href="../../../references/card-system.md">правила карточной системы</a>. <a href="card-style-review.pdf">Четыре исправленных примера</a>. Техническое покрытие не означает визуального одобрения. Карточки 12, 14, 16, 18 соответствуют слайдам 7, 9, 11, 13 контрольного набора.</p><p>Статус tested относится к конкретному контракту полей, а не ко всем возможным данным. Оригинальные растровые декоративные схемы остаются изображениями; текст, добавленные таблицы и графики редактируемы.</p><input placeholder="Поиск: номер, название, семейство, intent" aria-label="Поиск"><main>'+''.join(cards)+'</main><script>document.querySelector("input").oninput=e=>document.querySelectorAll("article").forEach(a=>a.hidden=!a.dataset.search.toLowerCase().includes(e.target.value.toLowerCase()))</script>',encoding='utf-8')
    with (out/'coverage.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f,lineterminator="\n");w.writerow(['slide','id','family','variant','layout','master','theme','status','text_fields','image_fields','table_fields','chart_fields','visual_status'])
        for r in data['slides']:w.writerow([r['source_slide'],r['id'],r['family'],r['name'],r['layout_part'],r['master_part'],r['theme_part'],r['status'],sum(r['editable_counts'][k] for k in ['title','heading','body','value']),r['editable_counts']['image'],r['editable_counts']['table'],r['editable_counts']['chart'],r.get('visual_status','not-reviewed')])
    return out

def compare_images(expected,actual):
    """Exact pixel regression, same renderer and image dimensions required."""
    from PIL import Image,ImageChops,ImageStat
    a=Image.open(expected).convert('RGB');b=Image.open(actual).convert('RGB')
    if a.size!=b.size:return {'passed':False,'reason':'dimensions','expected':a.size,'actual':b.size}
    diff=ImageChops.difference(a,b);return {'passed':diff.getbbox() is None,'bbox':diff.getbbox(),'mean_error':sum(ImageStat.Stat(diff).mean)/3}
