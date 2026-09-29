import copy,json,os,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'skills/cgu-presentations/scripts'))
from benchmark_decks import synthetic,PLANS
from spec import validate
from content_review import ledger_report
from planning import storyboard
from stress_original import generate
from original_template import load
from original_build import validate as original_validate

class BenchmarkTests(unittest.TestCase):
    def test_four_narratives_preserve_inventory(self):
        with tempfile.TemporaryDirectory() as folder:
            for name in PLANS:
                with self.subTest(name=name):
                    d=synthetic(name,Path(folder));validate(d);self.assertEqual(ledger_report(d,folder)['status'],'passed');plan=storyboard(d)
                    self.assertEqual(plan['slides'][-1]['narrative_role'],'closing')
                    del d['content_ledger']['entries'][0]
                    with self.assertRaisesRegex(ValueError,'Unaccounted'):ledger_report(d,folder)
    def test_all_original_adapters_accept_minimum_and_normal(self):
        for record in load()['slides'][5:]:
            for case in ('minimum','normal','missing-optional'):
                with self.subTest(layout=record['id'],case=case):
                    s=generate(record,case,Path('.'));original_validate(dict(schema_version='cgu-original-deck/1',title='Тест',demo=True,slides=[s]))
    @unittest.skipUnless(os.environ.get('CGU_BENCHMARK_ROOT'),'Set CGU_BENCHMARK_ROOT for rendered deck checks')
    def test_five_rendered_benchmarks(self):
        from provenance_notes import verify
        from audit_template import audit
        root=Path(os.environ['CGU_BENCHMARK_ROOT'])
        for name in list(PLANS)+['event-briefing']:
            with self.subTest(deck=name):
                folder=root/name/('readable' if name=='event-briefing' else 'result');d=json.loads((folder/'content/deck-spec.json').read_text());verify(d,folder/'output/presentation.pptx')
                self.assertEqual(audit(folder/'output/presentation.pptx')['missing_internal_targets'],[])
                self.assertEqual(len(list((folder/'preview').glob('slide-*.png'))),len(d['slides']))
                self.assertTrue((folder/'output/presentation.pdf').is_file());self.assertEqual(json.loads((folder/'qa/content-ledger.json').read_text())['status'],'passed')
                if name=='event-briefing':
                    text=json.dumps(d,ensure_ascii=False);self.assertIn('$10 трлн',text);self.assertIn('−36 млн',text)
                    self.assertEqual(sum(s.get('section')!='appendix' for s in d['slides']),18)
