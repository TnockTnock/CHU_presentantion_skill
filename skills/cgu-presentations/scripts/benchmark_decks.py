"""Reproducible synthetic deck benchmarks; no corporate source data bundled."""
import argparse,copy,hashlib,json
from pathlib import Path
from content_review import strings
from run import build,SKILL

PLANS={
'executive': [('executive_summary','Итоги пилота','opening'),('hero_kpi','Главный результат','evidence'),('comparison_matrix','План и результат','analysis'),('before_after','Изменения процесса','analysis'),('thesis_evidence','Основания вывода','evidence'),('risk_controls','Проблемы и контроль','analysis'),('decision_tree','Выбор следующего шага','decision'),('project_status','Готовность к расширению','context'),('roadmap_actions','Следующие действия','action'),('executive_summary','Решение для руководства','closing')],
'project-status':[('executive_summary','Статус проекта','opening'),('metric_scale','Результаты этапа','evidence'),('project_status','Ход работ','context'),('timeline_horizontal','План этапов','context'),('before_after','Изменения за период','analysis'),('risk_controls','Риски и меры','analysis'),('thesis_evidence','Проверка результата','evidence'),('decision_tree','Необходимые решения','decision'),('roadmap_actions','План следующего этапа','action'),('executive_summary','Условия завершения','closing')],
'research':[('executive_summary','Результаты исследования','opening'),('chart','Динамика показателя','evidence'),('comparison_matrix','Сопоставление групп','analysis'),('before_after','До и после пилота','analysis'),('chart','Проверка второй выборки','evidence'),('thesis_evidence','Основания интерпретации','evidence'),('risk_controls','Ограничения данных','analysis'),('decision_tree','Варианты проверки гипотез','decision'),('roadmap_actions','Следующие исследования','action'),('executive_summary','Выводы и ограничения','closing')],
'architecture':[('executive_summary','Цель трансформации','opening'),('architecture','Слои системы','context'),('process_flow','Путь обращения','context'),('stakeholder_map','Участники и ответственность','analysis'),('human_loop','Контроль решений человеком','analysis'),('decision_tree','Границы автоматизации','decision'),('risk_controls','Зависимости и риски','analysis'),('project_status','Готовность компонентов','evidence'),('roadmap_actions','Этапы внедрения','action'),('executive_summary','Условия запуска','closing')]
}


def attach_model(deck):
    """Migrate explicit evidence pointers, preserving all legacy claims/ledger."""
    items=[]
    for slide in deck['slides']:
        slide['model_bindings']=[]
        for path,refs in slide.get('object_sources',{}).items():
            from content_review import pointer
            cid=slide['id']+':'+path
            item={'id':cid,'kind':'claim','claim_type':'source_report','value':copy.deepcopy(pointer(slide,path)),'source_ids':refs}
            items.append(item);slide['model_bindings'].append({'pointer':path,'content_id':cid})
    deck['content_model']={'schema_version':'cgu-content/1','sources':copy.deepcopy(deck['sources']),'items':items}
    return deck


def synthetic(name,base):
    semantic=json.loads((SKILL/'examples/semantic-demo.json').read_text(encoding='utf-8'));pool={s['layout']:s for s in semantic['slides']}
    demo=json.loads((SKILL/'examples/demo.json').read_text(encoding='utf-8'));pool['chart']=next(s for s in demo['slides'] if s['kind']=='chart')
    slides=[];facts=[];entries=[]
    for i,(key,title,role) in enumerate(PLANS[name],1):
        s=copy.deepcopy(pool[key]);s.update(id=f'{name}-{i:02d}',title=title,narrative_role=role,purpose=title,information_density='medium',selection_reason='Контроль '+key+' на синтетических данных',source_ids=['BENCHMARK'])
        if s.get('kind')=='composition':
            s['takeaway']='Синтетический пример: результат требует проверки на рабочих данных';s['caveat']='Демонстрационные данные, не показатели организации'
            for binding in s.get('metric_bindings',[]):binding['metric']['source_id']='BENCHMARK'
        if s.get('kind')=='chart':paths=['/categories']+['/series/'+str(j) for j in range(len(s['series']))]
        else:paths=['/items/'+str(j) for j in range(len(s['items']))]+['/caveat']
        s['object_sources']={p:['BENCHMARK'] for p in paths}
        from content_review import pointer
        for j,path in enumerate(paths):
            text=strings(pointer(s,path));fid=f'{s["id"]}-{j}';facts.append(dict(id=fid,text=text,location='Synthetic benchmark '+name+' / '+fid));entries.append(dict(fact_id=fid,status='preserved',reason='Контроль сохранности',statement_type='source_report',targets=[dict(slide_id=s['id'],pointer=path,text=text)]))
        slides.append(s)
    # Legacy KPI source_text must also be covered in inventory.
    for slide in slides:
        for j,binding in enumerate(slide.get('metric_bindings',[])):
            text=binding['metric']['source_text'];fid=slide['id']+'-metric-'+str(j);facts.append(dict(id=fid,text=text,location='Synthetic KPI'));entries.append(dict(fact_id=fid,status='condensed',reason='Число и контекст в KPI',statement_type='source_report',targets=[dict(slide_id=slide['id'],pointer=binding['pointer'],text=binding['metric']['display'])]))
    inv={'schema_version':'cgu-source-inventory/1','facts':facts};raw=json.dumps(inv,ensure_ascii=False,indent=2).encode();(base/'inventory.json').write_bytes(raw)
    deck=dict(schema_version='cgu-presentations/2',title='Benchmark '+name,demo=True,sources=[dict(id='BENCHMARK',location='Synthetic fixture '+name)],slides=slides,content_ledger=dict(inventory='inventory.json',inventory_sha256=hashlib.sha256(raw).hexdigest(),entries=entries))
    return attach_model(deck)


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True,type=Path);ap.add_argument('--no-render',action='store_true');a=ap.parse_args()
    if a.out.exists() and any(a.out.iterdir()):raise ValueError('Use new benchmark directory')
    a.out.mkdir(parents=True,exist_ok=True)
    for name in PLANS:
        folder=a.out/name;folder.mkdir();deck=synthetic(name,folder);spec=folder/'deck.json';spec.write_text(json.dumps(deck,ensure_ascii=False,indent=2),encoding='utf-8');build(spec,folder/'result',backend='portable',render=not a.no_render)

if __name__=='__main__':main()
