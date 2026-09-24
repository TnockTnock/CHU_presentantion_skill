import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from zipfile import ZipFile, ZIP_DEFLATED
from xml.etree import ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
SKILL=ROOT/'skills/cgu-presentations'
sys.path.insert(0,str(SKILL/'scripts'))
from spec import validate
from number_typography import transform, numeric_errors, A
from verify_output import verify

class TextBlocksTests(unittest.TestCase):
    def setUp(self):
        self.deck=json.loads((SKILL/'examples/text-blocks-demo.json').read_text())

    def test_variants_and_capacities(self):
        validate(self.deck)
        self.deck['slides'][1]['items'].pop()
        with self.assertRaisesRegex(ValueError,'block count'):validate(self.deck)

    def test_missing_callout_and_wrong_fields(self):
        del self.deck['slides'][2]['callout']
        with self.assertRaisesRegex(ValueError,'callout'):validate(self.deck)
        self.setUp();self.deck['slides'][0]['items'][0]['value']='5'
        with self.assertRaisesRegex(ValueError,'block fields'):validate(self.deck)

    def test_object_evidence_covers_items_and_conclusion(self):
        self.deck.update(demo=False,evidence_policy='object',sources=[{'id':'s','location':'test fixture'}])
        for slide in self.deck['slides']:
            slide['source_ids']=['s']
            slide['object_sources']={f'/items/{j}':['s'] for j in range(len(slide['items']))}
            if 'callout' in slide:slide['object_sources']['/callout']=['s']
        validate(self.deck)
        del self.deck['slides'][2]['object_sources']['/callout']
        with self.assertRaisesRegex(ValueError,'object evidence missing'):validate(self.deck)

    def test_numeric_runs_preserve_text_color_size_and_other_weights(self):
        root=ET.Element(A+'p')
        run=ET.SubElement(root,A+'r');props=ET.SubElement(run,A+'rPr',{'sz':'2400','b':'0'})
        ET.SubElement(props,A+'latin',{'typeface':'Golos Text SemiBold'})
        ET.SubElement(props,A+'solidFill');value='За 2026 год: 1 200 и −3,5%, версия 2.0'
        ET.SubElement(run,A+'t').text=value
        transform(root)
        self.assertEqual(''.join(e.text or '' for e in root.iter(A+'t')),value)
        self.assertEqual(numeric_errors(root),[])
        for run in root:
            props=run.find(A+'rPr')
            self.assertEqual(props.get('sz'),'2400');self.assertIsNotNone(props.find(A+'solidFill'))
            if not any(c.isdigit() for c in run.find(A+'t').text):
                self.assertEqual(props.find(A+'latin').get('typeface'),'Golos Text SemiBold')
                self.assertEqual(props.get('b'),'0')
        before=ET.tostring(root);transform(root);self.assertEqual(ET.tostring(root),before)

    @unittest.skipUnless(os.environ.get('CGU_TEXT_BLOCKS_DECK'),'Set CGU_TEXT_BLOCKS_DECK for integration')
    def test_editable_blocks_typography_and_corruption_detection(self):
        source=Path(os.environ['CGU_TEXT_BLOCKS_DECK'])
        self.assertEqual(verify(self.deck,source)['errors'],[])
        wrong=copy.deepcopy(self.deck);wrong['slides'][0]['items'][0]['body']='Missing content'
        self.assertTrue(any('native text mismatch' in e for e in verify(wrong,source)['errors']))
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'wrong-font.pptx'
            with ZipFile(source) as zin,ZipFile(target,'w',ZIP_DEFLATED) as zout:
                for item in zin.infolist():
                    data=zin.read(item.filename)
                    if item.filename=='ppt/slides/slide1.xml':
                        root=ET.fromstring(data)
                        for run in root.iter(A+'r'):
                            props=run.find(A+'rPr');value=run.find(A+'t')
                            if props is not None and value is not None:
                                if any(c.isdigit() for c in value.text or ''):props.set('b','0')
                                else:
                                    font=props.find(A+'latin')
                                    if font is not None:font.set('typeface','Golos Text')
                        data=ET.tostring(root)
                    zout.writestr(item,data)
            errors=verify(self.deck,target)['errors']
            self.assertTrue(any('number must' in e for e in errors))
            self.assertTrue(any('heading must' in e for e in errors))
