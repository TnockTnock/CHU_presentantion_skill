"""Optional rendering for all agents; PPTX creation stays dependency-free."""
import hashlib
import importlib.util
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from xml.sax.saxutils import escape
from zipfile import ZipFile
from xml.etree import ElementTree as ET

SKILL = Path(__file__).resolve().parents[1]


def capabilities(runtime=None, required=False):
    bundled = Path(runtime or os.environ.get('CGU_RUNTIME_DIR', Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies'))
    def executable(key, name):
        local = bundled/'bin/override'/name
        explicit = os.environ.get(key)
        candidate = str(local) if local.is_file() else explicit or shutil.which(name)
        if not candidate and name == 'soffice' and sys.platform == 'win32':
            for variable in ('LOCALAPPDATA', 'PROGRAMFILES', 'PROGRAMFILES(X86)'):
                base = os.environ.get(variable)
                path = Path(base)/'LibreOffice/program/soffice.exe' if base else None
                if path and path.is_file():
                    candidate = str(path)
                    break
        if candidate and not Path(candidate).is_file():
            raise ValueError(key + ': executable not found: ' + candidate)
        return Path(candidate).resolve() if candidate else None
    paths = {'runtime': 'Python standard library', 'python': Path(sys.executable),
             'soffice': executable('CGU_SOFFICE', 'soffice'),
             'pdftoppm': executable('CGU_PDFTOPPM', 'pdftoppm'),
             'pymupdf': importlib.util.find_spec('fitz') is not None}
    paths['rasterizer'] = 'poppler' if paths['pdftoppm'] else 'pymupdf' if paths['pymupdf'] else None
    if required and (not paths['soffice'] or not paths['rasterizer']):
        raise ValueError('PDF/PNG requires LibreOffice and either Poppler or PyMuPDF in this Python. Set CGU_SOFFICE / CGU_PDFTOPPM, or use --no-render.')
    return paths


def rasterize(pdf, preview, paths, scale=1920):
    preview = Path(preview)
    preview.mkdir(parents=True, exist_ok=True)
    if any(preview.glob('slide-*.png')):
        raise ValueError('Preview directory already contains slides')
    if paths.get('pdftoppm'):
        subprocess.run([str(paths['pdftoppm']), '-scale-to', str(scale), '-png', str(pdf), str(preview/'slide')], check=True, timeout=180)
        return 'poppler'
    if not paths.get('pymupdf'):
        raise ValueError('PNG requires Poppler or PyMuPDF')
    import fitz
    with fitz.open(str(pdf)) as document:
        digits = len(str(len(document)))
        for index, page in enumerate(document, 1):
            zoom = scale / max(page.rect.width, page.rect.height)
            pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
            pixmap.save(str(preview/('slide-' + str(index).zfill(digits) + '.png')))
    return 'pymupdf'


def render(pptx, pdf, preview, paths=None, scale=1920):
    pptx, pdf, preview = Path(pptx).resolve(), Path(pdf).resolve(), Path(preview).resolve()
    if not pptx.is_file():
        raise ValueError('PPTX not found: ' + str(pptx))
    if pdf.exists() or (preview.exists() and any(preview.iterdir())):
        raise ValueError('Render destinations must be empty')
    paths = paths or capabilities(required=True)
    before = hashlib.sha256(pptx.read_bytes()).hexdigest()
    with ZipFile(pptx) as archive:
        presentation = ET.fromstring(archive.read('ppt/presentation.xml'))
        count = len(presentation.findall('./{*}sldIdLst/{*}sldId'))
    # Staging also isolates concurrent LibreOffice runs. Avoid passing user file
    # names to the converter; never fall back to the user's default LO profile.
    with tempfile.TemporaryDirectory(prefix='cgu-render-') as folder:
        scratch = Path(folder).resolve()
        if sys.platform == 'win32' and not str(scratch).isascii():
            raise ValueError('LibreOffice on Windows requires an ASCII temporary path. Set TMP and TEMP to a writable ASCII path and retry.')
        source = scratch/'presentation.pptx'
        shutil.copy2(pptx, source)
        conf = scratch/'fonts.conf'
        conf.write_text('<fontconfig><dir>'+escape(str(SKILL/'assets/fonts'))+'</dir><cachedir>'+escape(str(scratch/'font-cache'))+'</cachedir><alias><family>Golos Text DemiBold</family><prefer><family>Golos Text SemiBold</family></prefer></alias></fontconfig>', encoding='utf-8')
        env = os.environ.copy()
        env['FONTCONFIG_FILE'] = str(conf)
        subprocess.run([str(paths['soffice']), '-env:UserInstallation='+(scratch/'profile').as_uri(), '--headless', '--convert-to', 'pdf', '--outdir', str(scratch), str(source)], env=env, check=True, timeout=180)
        converted = scratch/'presentation.pdf'
        if not converted.is_file():
            raise ValueError('LibreOffice did not create PDF')
        pdf.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(converted, pdf)
    engine = rasterize(pdf, preview, paths, scale)
    actual = len(list(preview.glob('slide-*.png')))
    if actual != count:
        raise ValueError(f'PDF page count {actual} does not match PPTX slides {count}')
    if hashlib.sha256(pptx.read_bytes()).hexdigest() != before:
        raise ValueError('Input PPTX changed during rendering')
    from visual_qa import html_contact, contact_sheet
    html_contact(preview)
    contact_sheet(preview)
    fonts = sorted(set(x.decode('latin1') for x in re.findall(rb'/BaseFont\s*/([^\s/<>()]+)', pdf.read_bytes())))
    return {'pdf_font_names': fonts, 'font_warning': None if fonts and all('golos' in f.lower() for f in fonts) else 'Inspect PDF font substitutions before delivery.', 'rendered': True, 'slides': count, 'rasterizer': engine, 'pptx_sha256': before,
            'input_unchanged': True, 'visual_review': 'pending', 'powerpoint': 'not-tested'}


def render_only(pptx, out, runtime=None):
    pptx, out = Path(pptx).resolve(), Path(out).resolve()
    if out.exists() and any(out.iterdir()):
        raise ValueError('Output directory is not empty. Use a new run directory.')
    paths = capabilities(runtime, required=True)
    report = render(pptx, out/'output/presentation.pdf', out/'preview', paths)
    (out/'qa').mkdir(exist_ok=True)
    (out/'qa/render.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report
