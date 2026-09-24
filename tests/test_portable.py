import contextlib
import copy
from io import BytesIO, StringIO
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile
from xml.etree import ElementTree as ET

ROOT=Path(__file__).resolve().parents[1];SKILL=ROOT/'skills/cgu-presentations'
sys.path.insert(0,str(SKILL/'scripts'))
import run
from skill_package import package, install, PROFILES
from verify_output import verify
from portable_fonts import Metrics
from portable_ooxml import NS

class PortableTests(unittest.TestCase):
    def test_all_examples_build_without_codex_or_third_party_packages(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(run,'runtime_paths',side_effect=AssertionError('Codex must not be loaded')):
            for name in ['demo.json','library-demo.json','text-blocks-demo.json','edge-cases.json']:
                with self.subTest(name=name),contextlib.redirect_stdout(StringIO()):
                    out=Path(folder)/name;run.build(SKILL/'examples'/name,out,render=False,backend='portable')
                    spec=json.loads((SKILL/'examples'/name).read_text(encoding='utf-8'))
                    self.assertEqual(verify(spec,out/'output/presentation.pptx')['errors'],[])
                    record=json.loads((out/'qa/run.json').read_text(encoding='utf-8'))
                    self.assertFalse(record['rendered']);self.assertEqual(record['visual_review'],'pending')
                    self.assertEqual(record['backend'],'portable')
                    with ZipFile(out/'output/presentation.pptx') as z:
                        self.assertEqual(len([n for n in z.namelist() if n.startswith('ppt/slides/slide') and n.endswith('.xml')]),len(spec['slides']))
                        for n in z.namelist():
                            if n.startswith('ppt/charts/chart') and n.endswith('.xml'):
                                chart=ET.fromstring(z.read(n))
                                for ser in chart.findall('.//c:barChart/c:ser',NS):
                                    self.assertEqual(ser.find('c:invertIfNegative',NS).get('val'),'0')
                                for ser in chart.findall('.//c:lineChart/c:ser',NS):
                                    self.assertEqual(ser.find('c:smooth',NS).get('val'),'0')
                            if n.endswith('.xlsx'):
                                with ZipFile(BytesIO(z.read(n))) as workbook:
                                    self.assertIsNone(workbook.testzip());root=ET.fromstring(workbook.read('xl/worksheets/sheet1.xml'))
                                    self.assertTrue(root.findall('.//s:c',NS))
                            if n.startswith('ppt/slides/slide') and n.endswith('.xml'):
                                root=ET.fromstring(z.read(n))
                                for graphic in root.findall('.//a:graphicData',NS):
                                    if graphic.find('a:tbl',NS) is not None:self.assertEqual(graphic.get('uri'),'http://schemas.openxmlformats.org/drawingml/2006/table')

    def test_auto_falls_back_only_at_capability_resolution(self):
        with patch.object(run,'runtime_paths',side_effect=ValueError('No Codex')),patch.object(run,'portable_paths',return_value={'python':sys.executable}):
            self.assertEqual(run.resolve_backend('auto')[0],'portable')
            with self.assertRaisesRegex(ValueError,'No Codex'):run.resolve_backend('codex')

    def test_font_measurement_rejects_overflow_and_missing_glyph(self):
        m=Metrics(SKILL);self.assertGreater(m.width('120',24,False),0)
        with self.assertRaisesRegex(ValueError,'overflows'):m.check('Строка\nСтрока',300,20,24,False,'sample')
        with self.assertRaisesRegex(ValueError,'glyph'):m.width('🦄',24,False)

    def test_package_excludes_local_and_work_files_and_installs_all_profiles(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'source';source.mkdir();(source/'SKILL.md').write_text('test',encoding='utf-8')
            for dirname in ['local','work','scripts','scripts/__pycache__']:
                d=source/dirname;d.mkdir(exist_ok=True);(d/'secret.txt').write_text('fixture')
            archive=root/'skill.zip';package(archive,source)
            with ZipFile(archive) as z:
                self.assertEqual(set(z.namelist()),{'cgu-presentations/SKILL.md','cgu-presentations/scripts/secret.txt'})
            for agent,path in PROFILES.items():
                dest=root/agent/path/'cgu-presentations';install(dest,source);self.assertTrue((dest/'SKILL.md').is_file())
                with self.assertRaisesRegex(ValueError,'exists'):install(dest,source)
            dest=root/'claude'/PROFILES['claude']/'cgu-presentations';(dest/'local').mkdir();(dest/'local/config.json').write_text('{}')
            result=install(dest,source,replace=True)
            self.assertTrue((Path(result['backup'])/'SKILL.md').is_file());self.assertEqual((dest/'local/config.json').read_text(),'{}')
            self.assertNotIn('/skills/',result['backup'])

    def test_package_rejects_symlinks_to_external_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'SKILL.md').write_text('test');(root/'scripts').mkdir();(root/'external').write_text('private');(root/'scripts/link').symlink_to(root/'external')
            with self.assertRaisesRegex(ValueError,'symlink'):package(root/'out.zip',root)

if __name__=='__main__':unittest.main()
