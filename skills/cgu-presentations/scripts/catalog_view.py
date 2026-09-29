"""Three-level catalogue with explicit readiness and no invented approvals."""
import html,json
from pathlib import Path
from original_template import load
from original_style import effective_slot


def write(out):
    out=Path(out);records=load()['slides'];cards=[]
    filters={'family':set(),'intent':set(),'relationship':set(),'narrative_role':set(),'density':set(),'production_status':set()}
    esc=lambda value:html.escape(str(value),quote=True)
    for r in records:
        values=dict(family=r['family'],intent=r['intent'],relationship=r.get('relationships',[]),narrative_role=r.get('narrative_roles',[]),density=r.get('density','unknown'),production_status=r.get('production_status','reference-only'))
        for k,v in values.items():filters[k].update(v if isinstance(v,list) else [v])
        attrs=' '.join('data-'+k+'="'+esc(' '.join(v) if isinstance(v,list) else v)+'"' for k,v in values.items())
        attrs+=' '+ ' '.join('data-'+k+'="'+str(bool(r['editable_counts'].get(k,0))).lower()+'"' for k in ('image','chart','table'))
        attrs+=' data-kpi="'+str(bool(r['editable_counts'].get('value',0))).lower()+'"'
        levels='<figure><figcaption>ORIGINAL · '+str(r['source_slide'])+'</figcaption><img loading="lazy" src="'+esc(r['preview'])+'"></figure>'
        if r['classification']=='candidate':
            levels+='<figure><figcaption>NEUTRAL TEST · не визуальное одобрение</figcaption><img loading="lazy" src="'+esc(r['example_preview'])+'"></figure>'
            usage=r.get('approved_real_usage')
            levels+='<figure><figcaption>APPROVED REAL USAGE</figcaption>'+('<img loading="lazy" src="'+esc(usage['preview'])+'">' if usage and r.get('visual_status')=='approved' else '<p>Нет подтверждённого одобрения. Корпоративное содержание не публикуется.</p>')+'</figure>'
        slots=''.join('<tr>'+''.join('<td>'+esc(v)+'</td>' for v in [s['id'],s['role'],s['box_pt'],s['font_pt'],s['max_chars']])+'</tr>' for s in [effective_slot(r,s) for s in r['slots']])
        statuses={k:r.get(k,'not-applicable') for k in ('binding_status','visual_status','content_status','powerpoint_status','production_status','diagram_status')}
        cards.append('<article '+attrs+' data-search="'+esc(r['id']+' '+r['name']+' '+r['family'])+'"><h2>'+esc(r['id']+' · '+r['name'])+'</h2><p>'+esc(r['selection'])+'</p><pre>'+esc(json.dumps(statuses,ensure_ascii=False,indent=2))+'</pre>'+levels+'<details><summary>Поля, вместимость и наследование</summary><p>'+esc(r['layout_part']+' → '+r['master_part']+' → '+r['theme_part'])+'</p><table><tr><th>Поле</th><th>Роль</th><th>Область</th><th>pt</th><th>Символы*</th></tr>'+slots+'</table><p>* Лимит символов не гарантирует вместимость строки. Проверяется фактический текст.</p></details></article>')
    controls='<input id="search" aria-label="Поиск" placeholder="Номер, название, семейство">'
    for k,values in filters.items():controls+='<label>'+k+' <select data-filter="'+k+'"><option value="">Все</option>'+''.join('<option>'+esc(v)+'</option>' for v in sorted(values))+'</select></label>'
    for k in ('image','chart','table','kpi'):controls+='<label>'+k+' <select data-filter="'+k+'"><option value="">Все</option><option value="true">Да</option><option value="false">Нет</option></select></label>'
    page='''<!doctype html><html lang="ru"><meta charset="utf-8"><title>Каталог ЦГУ</title><style>body{font:16px system-ui;margin:28px;background:#f3f2f2;color:#222}header{position:sticky;top:0;background:#f3f2f2;padding:12px;z-index:1}label{display:inline-block;margin:6px}input,select{padding:8px;border-radius:8px;border:1px solid #aaa}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(450px,1fr));gap:24px}article{background:white;padding:24px;border-radius:24px}figure{margin:20px 0}img{width:100%}figcaption{font-weight:600;margin-bottom:8px}pre{white-space:pre-wrap}table{font-size:12px}td{padding:5px}</style><h1>Корпоративные композиции ЦГУ</h1><p>82 исходные страницы · 77 адаптеров · 18 семейств. Production требует подтверждённых проверок; это не синоним implemented.</p><header>'''+controls+'</header><main>'+''.join(cards)+'''</main><script>function filter(){const q=document.querySelector('#search').value.toLowerCase();document.querySelectorAll('article').forEach(a=>{a.hidden=!a.dataset.search.toLowerCase().includes(q)||[...document.querySelectorAll('[data-filter]')].some(s=>s.value&&!(a.getAttribute('data-'+s.dataset.filter)||'').split(' ').includes(s.value))})}document.querySelectorAll('input,select').forEach(x=>x.addEventListener('input',filter));</script></html>'''
    (out/'index.html').write_text(page,encoding='utf-8')
