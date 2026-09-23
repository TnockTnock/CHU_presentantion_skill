import copy
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
SKILL=ROOT/'skills/cgu-presentations'
sys.path.insert(0,str(SKILL/'scripts'))
from spec import validate
from preflight import inspect
from search_references import search
from verify_output import verify

class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.deck=json.loads((SKILL/'examples/library-demo.json').read_text())

    def test_new_compositions_and_repeated_layout(self):
        validate(self.deck)
        self.assertEqual(self.deck['slides'][0]['kind'],self.deck['slides'][-1]['kind'])

    def test_mismatched_comparison_rows(self):
        self.deck['slides'][1]['columns'][1]['items'].pop()
        with self.assertRaisesRegex(ValueError,'matching criteria'):validate(self.deck)

    def test_label_geometry_and_unknown_target(self):
        edge=self.deck['slides'][3]['edges'][0]
        edge['label_box']=[150,460,200,70]
        with self.assertRaisesRegex(ValueError,'overlaps node'):validate(self.deck)
        edge['label_box']=[560,375,170,65]
        edge['to']='absent'
        with self.assertRaisesRegex(ValueError,'dangling'):validate(self.deck)

    def test_object_sources_resolve_and_conflicts_block(self):
        self.deck['demo']=False;self.deck['evidence_policy']='object'
        self.deck['sources']=[{'id':'r','location':'test fixture / page 1'}]
        for s in self.deck['slides']:
            s['source_ids']=['r']
            field={'kpi_grid':'items','roadmap':'steps','diagram':'edges'}.get(s['kind'])
            if field:s['object_sources']={f'/{field}/{j}':['r'] for j in range(len(s[field]))}
        validate(self.deck)
        self.deck['slides'][0]['object_sources']['/items/999']=['r']
        with self.assertRaisesRegex(ValueError,'unresolved object pointer'):validate(self.deck)
        del self.deck['slides'][0]['object_sources']['/items/999']
        self.deck['sources'][0]['status']='conflict'
        with self.assertRaisesRegex(ValueError,'conflicting evidence'):validate(self.deck)

    def test_object_policy_does_not_accept_slide_only_evidence(self):
        self.deck['demo']=False;self.deck['evidence_policy']='object'
        self.deck['sources']=[{'id':'r','location':'test fixture'}]
        for s in self.deck['slides']:s['source_ids']=['r']
        with self.assertRaisesRegex(ValueError,'object evidence missing'):validate(self.deck)

    def test_calculated_source_needs_formula(self):
        self.deck['sources']=[{'id':'r','location':'test fixture','status':'calculated'}]
        with self.assertRaisesRegex(ValueError,'formula'):validate(self.deck)

    def test_registry_and_tampered_binding(self):
        self.assertEqual(inspect(SKILL)['errors'],[])
        with tempfile.TemporaryDirectory() as folder:
            dest=Path(folder)
            shutil.copytree(SKILL/'design-system',dest/'design-system')
            shutil.copytree(SKILL/'assets/templates',dest/'assets/templates')
            p=dest/'design-system/layouts.json';d=json.loads(p.read_text());d['layouts'][0]['slots']['title']='999999';p.write_text(json.dumps(d))
            self.assertTrue(any('bound shape' in e for e in inspect(dest)['errors']))
            d['template_sha256']='0'*64;p.write_text(json.dumps(d))
            self.assertIn('Template SHA mismatch',inspect(dest)['errors'])

    def test_search_deduplicates_and_resolves_local_preview(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'catalog.json'
            p.write_text(json.dumps({'source_root':'/local','documents':[{'path':'sample.pdf','sha256':'hash','pages':[{'page':1,'text':'Карта процесса','patterns':['roadmap'],'preview':'a.jpg'},{'page':2,'text':'Карта процесса','preview':'b.jpg','same_pixels_as':'doc:1'}]}]}))
            found=search(p,'карта')
            self.assertEqual(len(found),1);self.assertEqual(found[0]['source'],'/local/sample.pdf')
            self.assertEqual(len(search(p,'roadmap')),1)
            self.assertEqual(search(p,'несуществующий'),[])

    @unittest.skipUnless(os.environ.get('CGU_LIBRARY_DECK'),'Set CGU_LIBRARY_DECK for library integration')
    def test_native_values_labels_and_roadmap_edges(self):
        source=Path(os.environ['CGU_LIBRARY_DECK'])
        self.assertEqual(verify(self.deck,source)['errors'],[])
        self.deck['slides'][0]['items'][0]['value']='999'
        self.assertTrue(any('native text mismatch' in e for e in verify(self.deck,source)['errors']))
        self.deck=json.loads((SKILL/'examples/library-demo.json').read_text())
        self.deck['slides'][3]['edges'][0]['label']='Несовпадение'
        self.assertTrue(any('edge label missing' in e for e in verify(self.deck,source)['errors']))
