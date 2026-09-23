#!/usr/bin/env python3
"""Build a CGU deck: validate JSON, reuse template, finalize PPTX, render PDF/PNG."""
import argparse
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
from spec import validate
from verify_output import verify

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

def run(cmd, env=None):
    subprocess.run([str(v) for v in cmd], env=env, check=True)

def build(specfile, out, runtime=None, presentation_skill=None, render=True):
    specfile, out = Path(specfile).resolve(), Path(out).resolve()
    deck = validate(json.loads(specfile.read_text(encoding='utf-8')))
    paths = runtime_paths(runtime, presentation_skill)
    if out.exists() and any(out.iterdir()): raise ValueError('Output directory is not empty. Use a new run directory to preserve previous results.')
    out.mkdir(parents=True, exist_ok=True)
    for folder in ['content','build','qa','preview','output']:(out/folder).mkdir()
    shutil.copy2(specfile,out/'content/deck-spec.json')
    run([paths['node'],SKILL/'scripts/build.mjs',specfile,out,paths['runtime'],paths['presentation_skill'],paths['python']])
    pptx = out/'output/presentation.pptx'
    report = audit(pptx)
    (out/'qa/package-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    semantic=verify(deck,pptx)
    (out/'qa/semantic-checks.json').write_text(json.dumps(semantic,ensure_ascii=False,indent=2))
    if semantic['errors']:raise ValueError('; '.join(semantic['errors']))
    if report['missing_internal_targets']:raise ValueError('Broken package relationships')
    if report['non_golos_explicit_declarations']:raise ValueError('Unexpected explicit fonts: '+str(report['non_golos_explicit_declarations']))
    scenario = ['# '+deck['title']]
    if deck.get('demo'): scenario += ['','Демонстрационные данные. Не показатели ДИТ.']
    for n,s in enumerate(deck['slides'],1):
        scenario += ['',f"## {n}. {s['title'].replace(chr(10),' ')}",'',s.get('notes',''),'', '```json',json.dumps(s,ensure_ascii=False,indent=2),'```']
    (out/'output/scenario.md').write_text('\n'.join(scenario)+'\n',encoding='utf-8')
    (out/'content/outline.md').write_text('\n'.join(f"{i}. {s['title'].replace(chr(10),' ')} ({s['kind']})" for i,s in enumerate(deck['slides'],1))+'\n',encoding='utf-8')
    record={'spec_sha256':hashlib.sha256(specfile.read_bytes()).hexdigest(),'pptx_sha256':report['sha256'],'runtime':str(paths['runtime']),'slides':len(deck['slides']),'rendered':False,'visual_review':'pending','fonts_embedded_in_pptx':False}
    (out/'qa/run.json').write_text(json.dumps(record,ensure_ascii=False,indent=2))
    if render:
        env=os.environ.copy()
        conf=out/'build/fonts.conf'
        conf.write_text('<?xml version="1.0"?><fontconfig><dir>'+escape(str(SKILL/'assets/fonts'))+'</dir><cachedir>'+escape(str(out/'build/font-cache'))+'</cachedir></fontconfig>')
        env['FONTCONFIG_FILE']=str(conf)
        run([paths['soffice'],'--headless','--convert-to','pdf','--outdir',out/'output',pptx],env)
        pdf=out/'output/presentation.pdf'
        if not pdf.is_file():raise ValueError('Renderer did not create PDF')
        run([paths['pdftoppm'],'-scale-to','1920','-png',pdf,out/'preview/slide'],env)
        previews=list((out/'preview').glob('slide-*.png'))
        if len(previews)!=len(deck['slides']):raise ValueError('PDF page count does not match input')
        fonts=sorted(set(x.decode('latin1') for x in re.findall(rb'/BaseFont\s*/([^\s/<>()]+)',pdf.read_bytes())))
        record.update(rendered=True,pdf_font_names=fonts)
        # BaseFont names are a supporting check, never a substitute for seeing the slides.
        if not fonts or any('golos' not in f.lower() for f in fonts):
            record['font_warning']='PDF font inventory is missing or includes substitutions; inspect before delivery.'
    (out/'qa/run.json').write_text(json.dumps(record,ensure_ascii=False,indent=2))
    (out/'qa/report.md').write_text('# Автоматическая проверка\n\nСтруктура PPTX, число слайдов и явные шрифты проверены.\nВизуальная проверка: ожидается просмотр каждого слайда.\nШрифты в PPTX не встроены; для редактирования нужны Golos Text Regular и SemiBold.\n',encoding='utf-8')
    print(json.dumps(record,ensure_ascii=False,indent=2))
    return out

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('command',choices=['doctor','build','demo'])
    ap.add_argument('spec',nargs='?')
    ap.add_argument('--out',type=Path)
    ap.add_argument('--runtime');ap.add_argument('--presentation-skill');ap.add_argument('--no-render',action='store_true')
    a=ap.parse_args()
    try:
        if a.command=='doctor':
            print(json.dumps({k:str(v) for k,v in runtime_paths(a.runtime,a.presentation_skill).items()},indent=2));return
        if not a.out:ap.error('--out is required')
        source=SKILL/'examples/demo.json' if a.command=='demo' else a.spec
        if not source:ap.error('build requires a spec file')
        build(source,a.out,a.runtime,a.presentation_skill,not a.no_render)
    except (ValueError,OSError,subprocess.CalledProcessError) as e:
        print('CGU build failed: '+str(e),file=sys.stderr);sys.exit(1)

if __name__=='__main__':main()
