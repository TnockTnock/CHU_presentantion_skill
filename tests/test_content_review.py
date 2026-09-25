import contextlib,copy,hashlib,json,tempfile,sys,unittest
from io import StringIO
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
from xml.etree import ElementTree as ET
ROOT=Path(__file__).resolve().parents[1];SKILL=ROOT/'skills/cgu-presentations';sys.path.insert(0,str(SKILL/'scripts'))
from content_review import ledger_report,validate_metric,validate_editorial
from layout_selector import diversity,candidates,catalog
from spec import validate
from verify_output import verify
from compositions import scene
from visual_qa import inspect
import run

class ContentReviewTests(unittest.TestCase):
    def metric(self):return dict(number='10',sign='',currency='$',scale='трлн',suffix='',unit='оценка',period='2026',explanation='участников',source_id='src',source_text='$10 трлн',display='$10 трлн')
    def test_kpi_preserves_sign_currency_scale_and_context(self):
        m=self.metric();validate_metric(m)
        for key,value in [('display','$10'),('display','10 трлн'),('scale','млн'),('period','')]:
            broken=dict(m,**{key:value})
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):validate_metric(broken)
        m.update(number='36',sign='−',currency='',scale='млн',display='−36 млн',source_text='−36 млн');validate_metric(m)
        m['display']='36 млн'
        with self.assertRaises(ValueError):validate_metric(m)
    def test_ledger_rejects_loss_changed_text_notes_and_fake_appendix(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'inventory.json';p.write_text(json.dumps({'facts':[{'id':'f1','text':'$10 трлн','location':'slide 1'}]}),encoding='utf-8')
            deck={'slides':[{'id':'s1','kind':'text','body':'$10 трлн','notes':'$10 трлн','section':'appendix'}],'content_ledger':{'inventory':'inventory.json','inventory_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'entries':[{'fact_id':'f1','status':'appendix','reason':'Подробности','statement_type':'source_report','targets':[{'slide_id':'s1','pointer':'/body','text':'$10 трлн'}]}]}}
            self.assertEqual(ledger_report(deck,folder)['total'],1)
            for mutation in ['missing','changed','notes','section','hash']:
                d=copy.deepcopy(deck)
                if mutation=='missing':d['content_ledger']['entries']=[]
                if mutation=='changed':d['slides'][0]['body']='$10'
                if mutation=='notes':d['content_ledger']['entries'][0]['targets'][0]['pointer']='/notes'
                if mutation=='section':d['slides'][0]['section']='main'
                if mutation=='hash':d['content_ledger']['inventory_sha256']='0'*64
                with self.subTest(mutation=mutation),self.assertRaises(ValueError):ledger_report(d,folder)
    def test_verified_claims_require_verification(self):
        d={'sources':[{'id':'s'}],'slides':[{'id':'a','statement_type':'verified','source_ids':['s']}]}
        with self.assertRaises(ValueError):validate_editorial(d)
        d['sources'][0].update(verified_at='2026-09-25',verification_url='https://example.org/source');validate_editorial(d)
    def test_diversity_respects_justified_series(self):
        d={'slides':[{'id':str(i),'kind':'table'} for i in range(4)]}
        self.assertEqual(diversity(d)['warnings'],1)
        for s in d['slides']:s['repeat_reason']='Полная программа в приложении'
        self.assertEqual(diversity(d)['warnings'],0)
        s={'intent':'metrics','items':[{},{}]};self.assertEqual(len(candidates(s)),3)
        self.assertTrue(all(c['layout'] in ('hero_kpi','metric_scale','kpi_grid','kpi') for c in candidates(s)))
    def test_selector_considers_neighbor_and_text_capacity(self):
        slide={'intent':'sequence','items':[{'heading':'Шаг','body':'Кратко'}]*3}
        self.assertEqual(candidates(slide,'linear-3')[0]['layout'],'timeline_vertical')
        slide['items'][0]['body']='Т'*1000
        self.assertFalse(any(x['layout'].startswith('timeline_') for x in candidates(slide)))
    def test_all_semantic_layouts_are_editable_and_reusable(self):
        deck=json.loads((SKILL/'examples/semantic-demo.json').read_text(encoding='utf-8'));deck['slides'].append(dict(deck['slides'][0],id='repeat'))
        validate(deck)
        with tempfile.TemporaryDirectory() as folder,contextlib.redirect_stdout(StringIO()):
            p=Path(folder);spec=p/'deck.json';spec.write_text(json.dumps(deck,ensure_ascii=False),encoding='utf-8');out=p/'build';run.build(spec,out,backend='portable',render=False)
            self.assertEqual(verify(deck,out/'output/presentation.pptx')['errors'],[])
            self.assertEqual(inspect(out/'output/presentation.pptx')['errors'],[])
            saved=json.loads((out/'content/deck-spec.json').read_text(encoding='utf-8'));validate(saved)
            self.assertEqual(saved,deck)
            self.assertNotIn('```json',(out/'output/scenario.md').read_text(encoding='utf-8'))
    def test_scene_preserves_required_fields(self):
        deck=json.loads((SKILL/'examples/semantic-demo.json').read_text(encoding='utf-8'))
        for s in deck['slides']:
            values=json.dumps(scene(s),ensure_ascii=False)
            for item in s['items']:
                for v in item.values():self.assertIn(v,values)
    def test_composition_capacity_and_dangling_edge_rejected(self):
        d=json.loads((SKILL/'examples/semantic-demo.json').read_text(encoding='utf-8'));s=next(s for s in d['slides'] if s['layout']=='decision_tree');s['connections'][0]['to']=99
        with self.assertRaises(ValueError):validate(d)
        s['connections'][0]['to']=1;s['items']*=3
        with self.assertRaises(ValueError):validate(d)
    def test_registry_references_resolve(self):
        refs={p['key'] for p in json.loads((SKILL/'design-system/reference-patterns.json').read_text(encoding='utf-8'))['patterns']}
        for c in catalog().values():self.assertIn(c['reference_key'],refs);self.assertTrue((SKILL/c['example']).is_file())

if __name__=='__main__':unittest.main()
