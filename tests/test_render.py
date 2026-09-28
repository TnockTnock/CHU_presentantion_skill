import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'skills/cgu-presentations/scripts'))
import render_deck as renderer
from portable_fonts import Metrics

class RenderTests(unittest.TestCase):
    def test_optional_render_does_not_require_dependencies(self):
        with tempfile.TemporaryDirectory() as d, patch.dict('os.environ',{},clear=True), patch.object(renderer.shutil,'which',return_value=None), patch.object(renderer.importlib.util,'find_spec',return_value=None):
            self.assertIsNone(renderer.capabilities(d)['rasterizer'])
            with self.assertRaisesRegex(ValueError,'LibreOffice'):
                renderer.capabilities(d,required=True)

    def test_windows_libreoffice_discovery_and_fallback(self):
        with tempfile.TemporaryDirectory() as d:
            exe=Path(d)/'LibreOffice/program/soffice.exe';exe.parent.mkdir(parents=True);exe.touch()
            with patch.dict('os.environ',{'LOCALAPPDATA':d},clear=True), patch.object(renderer.sys,'platform','win32'), patch.object(renderer.shutil,'which',return_value=None), patch.object(renderer.importlib.util,'find_spec',return_value=object()):
                result=renderer.capabilities(Path(d)/'runtime',required=True)
                self.assertEqual(result['soffice'],exe.resolve())
                self.assertEqual(result['rasterizer'],'pymupdf')

    def test_preserve_existing_output(self):
        with tempfile.TemporaryDirectory() as d:
            sentinel=Path(d)/'keep.txt';sentinel.write_text('keep')
            with self.assertRaisesRegex(ValueError,'not empty'):
                renderer.render_only('missing.pptx',d)
            self.assertEqual(sentinel.read_text(),'keep')

    def test_pymupdf_scales_longest_edge_and_names_pages(self):
        calls=[]
        class Page:
            rect=types.SimpleNamespace(width=600,height=800)
            def get_pixmap(self,**kw):
                calls.append(kw)
                return types.SimpleNamespace(save=lambda p:Path(p).write_bytes(b'png'))
        class Document:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def __len__(self):return 12
            def __iter__(self):return iter([Page() for _ in range(12)])
        fake=types.SimpleNamespace(open=lambda p:Document(),Matrix=lambda x,y:(x,y))
        with tempfile.TemporaryDirectory() as d,patch.dict(sys.modules,{'fitz':fake}):
            engine=renderer.rasterize('input.pdf',d,{'pymupdf':True},1600)
            self.assertEqual(engine,'pymupdf');self.assertEqual(calls[0],{'matrix':(2,2),'alpha':False})
            self.assertTrue((Path(d)/'slide-01.png').exists());self.assertTrue((Path(d)/'slide-12.png').exists())
            with self.assertRaisesRegex(ValueError,'already contains'):
                renderer.rasterize('input.pdf',d,{'pymupdf':True})

    def test_numeric_width_is_not_discarded(self):
        m=Metrics(ROOT/'skills/cgu-presentations')
        self.assertGreater(m.width('План 123 456 789',24,False),m.width('План ',24,False))
        with self.assertRaisesRegex(ValueError,'word wider'):
            m.check('12345678901234567890',30,30,24,False,'numeric')
