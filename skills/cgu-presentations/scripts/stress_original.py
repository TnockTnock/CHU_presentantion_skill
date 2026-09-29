"""Exercise every original contract; rejected inputs are not visual passes."""
import argparse,copy,json
from pathlib import Path
from original_template import load,SKILL,digest
from original_build import example,validate,build
from original_style import effective_slot

CASES=('minimum','normal','maximum','long-russian','numeric-edge','missing-optional','image-edge','table-min','table-max','chart-min','chart-max','portrait-image','landscape-image','square-image','transparent-image')

def generate(record,case,assets):
    slide=example(record);slots=[effective_slot(record,s) for s in record['slots'] if s['editable']]
    applicable=True
    if 'image' in case:
        pictures=[s for s in slots if s['role']=='image']
        if not pictures:return None
        if case=='image-edge':slide['fields'][pictures[0]['id']]=dict(path='missing.png',sha256='0'*64,alt='Missing image');return slide
        path=assets/case.replace('-image','.png');slide['fields'][pictures[0]['id']]=dict(path=str(path),sha256=digest(path.read_bytes()),alt='Synthetic focus marker',fit='cover',focus=[.95,.15])
    elif case.startswith(('table-','chart-')):
        role=case.split('-')[0];targets=[s for s in slots if s['role']==role]
        if not targets:return None
        for s in targets:
            if role=='table':slide['fields'][s['id']]={'columns':['А']*(5 if case.endswith('max') else 1),'rows':[['1']*(5 if case.endswith('max') else 1) for _ in range(6 if case.endswith('max') else 1)]}
            else:slide['fields'][s['id']]={'categories':['А']*(8 if case.endswith('max') else 1),'series':[{'name':'Ряд','values':[-1,0,1,2,3,4,5,6][:8 if case.endswith('max') else 1]} for _ in range(3 if case.endswith('max') else 1)]}
    elif case=='missing-optional':
        for s in slots:
            if not s['required']:slide['fields'].pop(s['id'],None)
    elif case!='normal':
        for s in slots:
            if s['role'] in ('image','chart','table'):continue
            if case=='minimum':value='1' if s['role']=='value' else 'А'
            elif case=='maximum':value=('Данные '*((s['max_chars']//7)+1))[:s['max_chars']].strip()
            elif case=='long-russian':value='Межведомственное взаимодействие государственных информационных систем'
            else:value='$10 трлн · −36 млн · +17% · 2025–2026 · 4–8 октября'
            slide['fields'][s['id']]=value
    return slide


def run(out,render=False):
    out=Path(out).resolve()
    if out.exists() and any(out.iterdir()):raise ValueError('Use empty stress output directory')
    out.mkdir(parents=True,exist_ok=True);assets=out/'assets';assets.mkdir()
    from PIL import Image,ImageDraw
    for name,size,alpha in [('portrait',(400,800),False),('landscape',(800,400),False),('square',(500,500),False),('transparent',(500,500),True)]:
        im=Image.new('RGBA' if alpha else 'RGB',size,(255,255,255,0) if alpha else '#f3f2f2');ImageDraw.Draw(im).ellipse((size[0]*.8,0,size[0],size[1]*.3),fill='#ff254a');im.save(assets/(name+'.png'))
    results=[]
    for case in CASES:
        accepted=[]
        for record in load()['slides'][5:]:
            slide=generate(record,case,assets);row={'layout_id':record['id'],'case':case,'render':'not-run','visual_review':'unreviewed'}
            if slide is None:row['contract']='not-applicable'
            else:
                deck={'schema_version':'cgu-original-deck/1','title':'Stress '+case,'demo':True,'slides':[slide]}
                try:validate(deck,out)
                except (ValueError,OSError) as e:row.update(contract='rejected',reason=str(e))
                else:row['contract']='accepted';row['page']=len(accepted)+1;accepted.append(slide)
            results.append(row)
        if accepted:
            deck={'schema_version':'cgu-original-deck/1','title':'Stress '+case,'demo':True,'slides':accepted};folder=out/case;folder.mkdir();(folder/'deck.json').write_text(json.dumps(deck,ensure_ascii=False,indent=2),encoding='utf-8')
            report=build(deck,folder/'presentation.pptx',out)
            if report['errors']:raise ValueError(str(report['errors']))
            if render:
                from original_cli import render as render_deck
                render_deck(folder/'presentation.pptx',folder)
                for row in results:
                    if row['case']==case and row['contract']=='accepted':row['render']='passed'
        (out/'matrix.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    summary={'layouts':77,'cases':len(results),'accepted':sum(r['contract']=='accepted' for r in results),'rejected':sum(r['contract']=='rejected' for r in results),'not_applicable':sum(r['contract']=='not-applicable' for r in results),'visual_approval':0,'limitation':'Contract rejection is a capacity guard, not a successful visual stress test. Clipping, hierarchy, crop semantics and font substitution require rendered inspection.'}
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8');return summary

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);ap.add_argument('--render',action='store_true');a=ap.parse_args();print(json.dumps(run(a.out,a.render),ensure_ascii=False,indent=2))
