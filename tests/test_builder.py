import os
import json
from pathlib import Path
import sys
import tempfile
import unittest
from zipfile import ZipFile

ROOT=Path(__file__).resolve().parents[1]
SKILL=ROOT/'skills/cgu-presentations'
sys.path.insert(0,str(SKILL/'scripts'))
from spec import validate
from normalize_fonts import normalize
from audit_template import audit

class BuilderContractTests(unittest.TestCase):
    def setUp(self):
        self.deck=json.loads((SKILL/'examples/demo.json').read_text(encoding="utf-8"))

    def test_demo_is_valid(self):
        validate(self.deck)

    def test_unknown_fields_are_not_silently_ignored(self):
        self.deck['slides'][0]['images']={'ignored':'photo.png'}
        with self.assertRaisesRegex(ValueError,'unknown fields'):validate(self.deck)

    def test_non_demo_requires_resolved_sources(self):
        self.deck['demo']=False
        with self.assertRaisesRegex(ValueError,'source_ids'):validate(self.deck)
        for s in self.deck['slides']:s['source_ids']=['demo']
        validate(self.deck)
        self.deck['slides'][0]['source_ids']=['missing']
        with self.assertRaisesRegex(ValueError,'unresolved source'):validate(self.deck)

    def test_diagram_dangling_edge_and_overlapping_nodes(self):
        d=next(s for s in self.deck['slides'] if s['kind']=='diagram')
        d['edges'][0]['to']='missing'
        with self.assertRaisesRegex(ValueError,'dangling'):validate(self.deck)
        d['edges'][0]['to']='api'
        d['nodes'][1]['box']=d['nodes'][0]['box'][:]
        with self.assertRaisesRegex(ValueError,'overlapping'):validate(self.deck)

    def test_chart_values_preserve_zero_and_negative(self):
        chart=next(s for s in self.deck['slides'] if s['kind']=='chart')
        chart['series'][0]['values']=[0,-5,2,10]
        validate(self.deck)
        chart['series'][0]['values'][0]=float('nan')
        with self.assertRaisesRegex(ValueError,'non-finite'):validate(self.deck)

    def test_chart_category_length_mismatch(self):
        chart=next(s for s in self.deck['slides'] if s['kind']=='chart')
        chart['series'][0]['values'].pop()
        with self.assertRaisesRegex(ValueError,'mismatch'):validate(self.deck)

    def test_font_normalization_preserves_package_and_original(self):
        source=SKILL/'assets/templates/cgu-short.pptx'
        before=source.read_bytes()
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'normalized.pptx'
            normalize(source,target)
            result=audit(target)
            self.assertEqual(result['missing_internal_targets'],[])
            self.assertEqual(result['non_golos_explicit_declarations'],{})
            self.assertEqual(result['slide_count'],19)
            self.assertIn('Golos Text SemiBold',result['font_declarations_all_xml'])
            with ZipFile(target) as z:
                self.assertFalse(any(n.startswith('ppt/fonts/') for n in z.namelist()))
            self.assertEqual(source.read_bytes(),before)

class BuiltDeckTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('CGU_TEST_DECK'), 'Set CGU_TEST_DECK for integration checks')
    def test_semantics_and_reversed_arrow_detection(self):
        from verify_output import verify
        from xml.etree import ElementTree as ET
        from zipfile import ZIP_DEFLATED
        from audit_template import NS
        source=Path(os.environ['CGU_TEST_DECK'])
        deck=json.loads((SKILL/'examples/demo.json').read_text(encoding="utf-8"))
        self.assertEqual(verify(deck,source)['errors'],[])
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'reversed.pptx'
            with ZipFile(source) as zin, ZipFile(target,'w',ZIP_DEFLATED) as zout:
                for item in zin.infolist():
                    data=zin.read(item.filename)
                    if item.filename=='ppt/slides/slide4.xml':
                        root=ET.fromstring(data)
                        arrow=root.find('.//a:tailEnd',NS)
                        self.assertIsNotNone(arrow)
                        arrow.tag='{'+NS['a']+'}headEnd'
                        data=ET.tostring(root,encoding='utf-8')
                    zout.writestr(item,data)
            self.assertTrue(any('arrowhead' in e for e in verify(deck,target)['errors']))

if __name__=='__main__':unittest.main()
