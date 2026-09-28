#!/usr/bin/env python3
"""Build a CGU deck: validate JSON, reuse template, finalize PPTX, render PDF/PNG."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from xml.sax.saxutils import escape
from audit_template import audit
from spec import validate, KINDS
from verify_output import verify
from preflight import inspect as preflight

SKILL = Path(__file__).resolve().parents[1]

def runtime_paths(runtime=None, presentation_skill=None):
    runtime = Path(runtime or os.environ.get('CGU_RUNTIME_DIR', Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies')).resolve()
    if not presentation_skill:
        presentation_skill = os.environ.get('CGU_PRESENTATIONS_SKILL')
    if not presentation_skill:
        candidates = list((Path.home()/'.codex/plugins/cache/openai-primary-runtime/presentations').glob('*/skills/presentations'))
        if not candidates:
            raise ValueError('Presentations runtime not found. Set CGU_PRESENTATIONS_SKILL and CGU_RUNTIME_DIR from load_workspace_dependencies.')
        presentation_skill = max(candidates, key=lambda p: tuple(int(x) for x in p.parts[-3].split('.') if x.isdigit()))
    presentation_skill = Path(presentation_skill).resolve()
    paths = {'runtime':runtime, 'presentation_skill':presentation_skill,
             'node':runtime/'node/bin/node', 'python':runtime/'python/bin/python3',
             'soffice':runtime/'bin/override/soffice', 'pdftoppm':runtime/'bin/override/pdftoppm'}
    for key in ['node','python','soffice','pdftoppm']:
        if not paths[key].is_file(): raise ValueError(f'Bundled {key} missing: {paths[key]}')
    if not (presentation_skill/'container_tools/artifact_tool_utils.mjs').is_file():
        raise ValueError('Presentation finalizer not found')
    return paths

def portable_paths(runtime=None, render=False):
    from render_deck import capabilities
    return capabilities(runtime, required=render)

def resolve_backend(backend, runtime=None, presentation_skill=None, render=False):
    if backend=='auto':
        try:return 'codex',runtime_paths(runtime,presentation_skill)
        except ValueError:backend='portable'
    if backend=='codex':return backend,runtime_paths(runtime,presentation_skill)
    return 'portable',portable_paths(runtime,render)

def run(cmd, env=None):
    subprocess.run([str(v) for v in cmd], env=env, check=True)

def build(specfile, out, runtime=None, presentation_skill=None, render=True, backend="auto"):
    specfile, out = Path(specfile).resolve(), Path(out).resolve()
    original=json.loads(specfile.read_text(encoding='utf-8'))
    if original.get('schema_version')=='cgu-original-deck/1':
        from original_cli import build_project
        if backend=='codex':raise ValueError('Original template adapters require --backend portable or auto')
        return build_project(specfile,out,render,runtime)
    deck = validate(json.loads(specfile.read_text(encoding='utf-8')))
    from content_review import ledger_report, write_reports
    ledger_report(deck,specfile.parent)
    for slide in deck['slides']:
        if slide.get('image'):slide['image']['path']=str((specfile.parent/slide['image']['path']).resolve())
    if any(s['kind']=='composition' for s in deck['slides']):
        if backend=='codex':raise ValueError('New semantic compositions require --backend portable; existing Codex layouts remain supported')
        backend='portable'
    resources=preflight(SKILL)
    if resources['errors']:raise ValueError('; '.join(resources['errors']))
    backend, paths = resolve_backend(backend, runtime, presentation_skill, render)
    if out.exists() and any(out.iterdir()): raise ValueError('Output directory is not empty. Use a new run directory to preserve previous results.')
    out.mkdir(parents=True, exist_ok=True)
    for folder in ['content','build','qa','preview','output']:(out/folder).mkdir()
    shutil.copy2(specfile,out/'content/deck-spec.json')
    coverage=write_reports(deck,specfile.parent,out)
    saved=copy.deepcopy(deck)
    if saved.get('content_ledger'):saved['content_ledger']['inventory']='source-archive.json'
    for slide in saved['slides']:
        if slide.get('image'):
            image=slide['image'];src=Path(image['path']);dest=out/'content/assets'/(image['sha256']+src.suffix.lower());dest.parent.mkdir(exist_ok=True)
            shutil.copy2(src,dest);image['path']='assets/'+dest.name
    (out/'content/deck-spec.json').write_text(json.dumps(saved,ensure_ascii=False,indent=2),encoding='utf-8')
    from layout_selector import diversity
    diversity_report=diversity(deck)
    (out/'qa/visual-diversity.json').write_text(json.dumps(diversity_report,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'content/sources.json').write_text(json.dumps(deck.get('sources',[]),ensure_ascii=False,indent=2), encoding="utf-8")
    (out/'qa/preflight.json').write_text(json.dumps(resources,ensure_ascii=False,indent=2), encoding="utf-8")
    if backend=='codex':
        run([paths['node'],SKILL/'scripts/build.mjs',specfile,out,paths['runtime'],paths['presentation_skill'],paths['python']])
    else:
        from portable_build import build as portable_build
        portable_build(deck,out)
    pptx = out/'output/presentation.pptx'
    report = audit(pptx)
    (out/'qa/package-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    semantic=verify(deck,pptx)
    (out/'qa/semantic-checks.json').write_text(json.dumps(semantic,ensure_ascii=False,indent=2), encoding="utf-8")
    if semantic['errors']:raise ValueError('; '.join(semantic['errors']))
    if report['missing_internal_targets']:raise ValueError('Broken package relationships')
    if report['non_golos_explicit_declarations']:raise ValueError('Unexpected explicit fonts: '+str(report['non_golos_explicit_declarations']))
    from visual_qa import inspect as inspect_visual, html_contact, contact_sheet
    geometry=inspect_visual(pptx)
    (out/'qa/visual-checks.json').write_text(json.dumps(geometry,ensure_ascii=False,indent=2),encoding='utf-8')
    if geometry['errors']:raise ValueError('Visual geometry checks failed: '+str(geometry['errors'][:5]))
    scenario = ['# '+deck['title']]
    if deck.get('demo'): scenario += ['','Демонстрационные данные. Не показатели ДИТ.']
    for n,s in enumerate(deck['slides'],1):
        scenario += ['',f"## {n}. {s['title'].replace(chr(10),' ')}",'',s.get('takeaway',''),'',s.get('notes','')]
    (out/'output/scenario.md').write_text('\n'.join(scenario)+'\n',encoding='utf-8')
    (out/'content/outline.md').write_text('\n'.join(f"{i}. {s['title'].replace(chr(10),' ')} ({s['kind']})" for i,s in enumerate(deck['slides'],1))+'\n',encoding='utf-8')
    record={'backend':backend,'validation_engine':'codex-finalizer-and-semantic' if backend=='codex' else 'portable-package-and-semantic','spec_sha256':hashlib.sha256(specfile.read_bytes()).hexdigest(),'pptx_sha256':report['sha256'],'runtime':str(paths['runtime']),'slides':len(deck['slides']),'rendered':False,'visual_review':'pending','fonts_embedded_in_pptx':False,'structure':'passed','powerpoint':'not-tested','evidence':{'policy':deck.get('evidence_policy','slide'),'references':'validated','factual_review':'demo' if deck.get('demo') else 'pending'}}
    (out/'qa/run.json').write_text(json.dumps(record,ensure_ascii=False,indent=2), encoding="utf-8")
    if render:
        from render_deck import render as render_file
        pdf=out/'output/presentation.pdf'
        rendered=render_file(pptx,pdf,out/'preview',paths)
        record['rasterizer']=rendered['rasterizer']
        html_contact(out/'preview')
        sheet=contact_sheet(out/'preview')
        (out/'qa/contact-sheet.json').write_text(json.dumps(sheet,ensure_ascii=False,indent=2),encoding='utf-8')
        previews=list((out/'preview').glob('slide-*.png'))
        if len(previews)!=len(deck['slides']):raise ValueError('PDF page count does not match input')
        fonts=sorted(set(x.decode('latin1') for x in re.findall(rb'/BaseFont\s*/([^\s/<>()]+)',pdf.read_bytes())))
        record.update(rendered=True,pdf_font_names=fonts)
        # BaseFont names are a supporting check, never a substitute for seeing the slides.
        if not fonts or any('golos' not in f.lower() for f in fonts):
            record['font_warning']='PDF font inventory is missing or includes substitutions; inspect before delivery.'
    record.update(content_ledger=coverage['status'],diversity_warnings=diversity_report['warnings'],geometry_warnings=len(geometry['warnings']))
    (out/'qa/run.json').write_text(json.dumps(record,ensure_ascii=False,indent=2), encoding="utf-8")
    (out/'qa/report.md').write_text('# Автоматическая проверка\n\nСтруктура PPTX, число слайдов и явные шрифты проверены.\nВизуальная проверка: ожидается просмотр каждого слайда.\nШрифты в PPTX не встроены; для редактирования нужны Golos Text Regular, SemiBold и Bold.\n',encoding='utf-8')
    print(json.dumps(record,ensure_ascii=False,indent=2))
    return out

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('command',choices=['doctor','validate','build','demo','render','original-catalog','original-select'])
    ap.add_argument('spec',nargs='?')
    ap.add_argument('--out',type=Path)
    ap.add_argument('--backend',choices=['auto','portable','codex'],default='auto')
    ap.add_argument('--fields',type=int,default=1);ap.add_argument('--images',type=int,default=0);ap.add_argument('--text-length',type=int,default=0);ap.add_argument('--previous-family');ap.add_argument('--data-type',choices=['text','chart','table','image'])
    ap.add_argument('--runtime');ap.add_argument('--presentation-skill');ap.add_argument('--no-render',action='store_true')
    a=ap.parse_args()
    try:
        if a.command=='render':
            if not a.spec or not a.out:ap.error('render requires a PPTX and --out')
            from render_deck import render_only
            print(json.dumps(render_only(a.spec,a.out,a.runtime),ensure_ascii=False,indent=2));return
        if a.command=='original-catalog':
            from original_cli import catalog
            print(catalog(a.out or SKILL/'assets/catalog/original'));return
        if a.command=='original-select':
            from original_template import select
            print(json.dumps(select(a.spec or 'reference',a.fields,a.images,a.text_length,a.previous_family,data_type=a.data_type),ensure_ascii=False,indent=2));return
        if a.command=='validate':
            if not a.spec:ap.error('validate requires a spec file')
            original=json.loads(Path(a.spec).read_text(encoding='utf-8'))
            if original.get('schema_version')=='cgu-original-deck/1':
                from original_build import validate as validate_original
                validate_original(original,Path(a.spec).resolve().parent)
                print(json.dumps({'valid':True,'slides':len(original['slides'])}));return
            deck=validate(original)
            from content_review import ledger_report
            ledger_report(deck,Path(a.spec).resolve().parent)
            print(json.dumps({'valid':True,'slides':len(deck['slides'])}));return
        if a.command=='doctor':
            result=preflight(SKILL)
            backend,paths=resolve_backend(a.backend,a.runtime,a.presentation_skill,False)
            print(json.dumps({'backend':backend,'supported_kinds':sorted(KINDS),'python':sys.version.split()[0],'render_available':bool(paths.get('soffice') and (paths.get('pdftoppm') or paths.get('pymupdf'))),'paths':{k:str(v) if v else None for k,v in paths.items()},'resources':result},indent=2))
            if result['errors']:raise ValueError('; '.join(result['errors']))
            return
        if not a.out:ap.error('--out is required')
        source=SKILL/'examples/demo.json' if a.command=='demo' else a.spec
        if not source:ap.error('build requires a spec file')
        build(source,a.out,a.runtime,a.presentation_skill,not a.no_render,a.backend)
    except (ValueError,OSError,subprocess.CalledProcessError,subprocess.TimeoutExpired) as e:
        print('CGU build failed: '+str(e),file=sys.stderr);sys.exit(1)

if __name__=='__main__':main()
