"""Create a portable editable specification from exact corporate slide fields."""
import copy,json,shutil
from pathlib import Path
from original_template import SKILL,load

def initialize(out,layouts=None,allow_experimental=False):
    out=Path(out)
    if out.exists() and any(out.iterdir()):raise ValueError('Use empty output directory')
    registry={r['id']:r for r in load()['slides'][5:]}
    ids=layouts or [r['id'] for r in registry.values() if r.get('production_status') in ('usable','production')]
    if not ids:raise ValueError('No eligible layouts')
    for id in ids:
        if id not in registry:raise ValueError('Unknown original layout: '+id)
        if registry[id].get('production_status','experimental')=='experimental' and not allow_experimental:raise ValueError('Experimental layout requires --allow-experimental: '+id)
    examples=json.loads((SKILL/'examples/original-all.json').read_text(encoding='utf-8'))
    indexed={s['layout_id']:s for s in examples['slides']};slides=[]
    out.mkdir(parents=True,exist_ok=True)
    for index,id in enumerate(ids,1):
        slide=copy.deepcopy(indexed[id]);slide['id']='slide-'+str(index);slides.append(slide)
        for value in slide['fields'].values():
            if isinstance(value,dict) and 'path' in value:
                src=SKILL/'examples'/value['path'];dst=out/'assets'/src.name
                dst.parent.mkdir(exist_ok=True);shutil.copy2(src,dst);value['path']='assets/'+src.name
    deck={'schema_version':'cgu-original-deck/1','title':'Проверка корпоративного шаблона — замените содержание','demo':True,'readiness_policy':'experimental' if allow_experimental else 'usable','slides':slides}
    (out/'deck.json').write_text(json.dumps(deck,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'START.md').write_text('Это нейтральная проверка шаблона, не готовый отчёт.\n\nСохраните layout_id и ключи fields. Замените тестовый текст своими данными. Для фактической презентации снимите demo, добавьте sources, source_ids и content_model по references/content-model.md. Проверяйте вместимость и итоговый рендер.\n',encoding='utf-8')
    return {'spec':str((out/'deck.json').resolve()),'slides':len(slides),'demo':True,'layouts':ids}
