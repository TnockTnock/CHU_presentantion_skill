import copy,json,sys,tempfile,unittest
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
ROOT=Path(__file__).resolve().parents[1];SKILL=ROOT/'skills/cgu-presentations';sys.path.insert(0,str(SKILL/'scripts'))
from content_model import validate_model,validate_deck
from image_adapter import crop,validate as validate_image
from planning import rank,fingerprint,similarity,record_feedback
from original_build import build,example
from original_template import load
from provenance_notes import verify as verify_notes


def fixture():
    values=dict(value='10 трлн',unit='капитализация',currency='$',sign='',period='2026',comparison_base='оценка участников')
    sources=[dict(id='S01',location='report.pdf p14',snapshot=values)]
    item=dict(id='K01',kind='kpi',claim_type='source_report',value='$10 трлн',source_ids=['S01'],kpi=values.copy(),source_components={k:dict(source_id='S01',pointer='/snapshot/'+k) for k in values})
    return dict(schema_version='cgu-content/1',sources=sources,items=[item])

class ContentModelTests(unittest.TestCase):
    def test_model_valid_before_layout_exists(self):self.assertEqual(set(validate_model(fixture())),{'K01'})
    def test_each_kpi_component_mutation_rejected(self):
        for field in ('value','unit','currency','sign','period','comparison_base'):
            with self.subTest(field=field):
                m=fixture();m['items'][0]['kpi'][field]+='x'
                with self.assertRaises(ValueError):validate_model(m)
    def test_kpi_source_mutation_rejected(self):
        m=fixture();m['items'][0]['source_ids']=['missing']
        with self.assertRaisesRegex(ValueError,'source'):validate_model(m)
    def test_kpi_atomic_ranges_and_signs(self):
        for value,currency,sign in [('10 трлн','$',''),('36 млн','','−'),('17%','','+'),('2025–2026','',''),('4–8 октября','','')]:
            m=fixture();k=m['items'][0]['kpi'];k.update(value=value,currency=currency,sign=sign);m['sources'][0]['snapshot']=k.copy();m['items'][0]['value']=sign+currency+value
            validate_model(m);m['items'][0]['value']=value+'\n'
            with self.assertRaises(ValueError):validate_model(m)
    def test_original_provenance_notes_and_corruption(self):
        r=load()['slides'][5];s=example(r);s['source_ids']=['S01'];s['notes']='Пояснение докладчика'
        deck=dict(schema_version='cgu-original-deck/1',title='Тест',sources=fixture()['sources'],slides=[s])
        with tempfile.TemporaryDirectory() as folder:
            out=Path(folder)/'deck.pptx';self.assertEqual(build(deck,out)['errors'],[]);verify_notes(deck,out)
            altered=copy.deepcopy(deck);altered['slides'][0]['notes']='Подмена'
            with self.assertRaisesRegex(ValueError,'provenance'):verify_notes(altered,out)
    def test_original_object_evidence_missing_and_bad_pointer(self):
        s=example(load()['slides'][5]);d=dict(schema_version='cgu-original-deck/1',sources=fixture()['sources'],slides=[s],evidence_policy='object');s['source_ids']=['S01']
        with self.assertRaisesRegex(ValueError,'evidence missing'):validate_deck(d)
        s['object_sources']={('/fields/'+k):['S01'] for k in s['fields']};validate_deck(d)
        s['object_sources']['/notes']=['S01']
        with self.assertRaisesRegex(ValueError,'visible'):validate_deck(d)
    def test_changed_model_binding_rejected(self):
        m=fixture();s=dict(id='s',source_ids=['S01'],kind='text',body='$10 трлн',object_sources={'/body':['S01']},model_bindings=[dict(pointer='/body',content_id='K01')])
        d=dict(content_model=m,sources=m['sources'],slides=[s]);s['body']='10'
        with self.assertRaisesRegex(ValueError,'differs'):validate_deck(d)
    def test_focus_and_aspect_crop(self):
        self.assertEqual(crop(200,100,100,100,[1,.5]),dict(l=50000,r=0,t=0,b=0))
        self.assertEqual(crop(100,200,100,100,[.5,0]),dict(l=0,r=0,t=0,b=50000))
        self.assertEqual(crop(100,100,100,100),dict(l=0,r=0,t=0,b=0))
        for f in ([2,0],[float('nan'),0],[True,.5]):
            with self.assertRaises(ValueError):validate_image(dict(alt='test',focus=f))
    def test_experimental_not_selected_and_explainable_score(self):
        request=dict(intent='metrics',fields=1)
        self.assertTrue(all(x['production_status']!='experimental' for x in rank(request)))
        exploratory=rank(request,allow_experimental=True);self.assertTrue(exploratory)
        for x in exploratory:self.assertAlmostEqual(x['score'],sum(x['score_components'].values()),places=3)
    def test_cross_kind_visual_similarity(self):
        a=fingerprint(dict(kind='cards',items=[{}]*3));b=fingerprint(dict(kind='text_blocks',variant='text_columns',items=[{}]*3))
        self.assertGreaterEqual(similarity(a,b),.9)
    def test_feedback_rejects_corporate_text(self):
        with tempfile.TemporaryDirectory() as d:
            entry=dict(layout_id='original-42',intent='comparison',density='medium',feedback='approved');record_feedback(entry,Path(d)/'feedback.jsonl')
            entry['content']='internal'
            with self.assertRaises(ValueError):record_feedback(entry,Path(d)/'feedback.jsonl')
