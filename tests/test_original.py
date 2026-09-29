import copy,json,sys,tempfile,unittest
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
from xml.etree import ElementTree as ET
ROOT=Path(__file__).resolve().parents[1];SKILL=ROOT/'skills/cgu-presentations';sys.path.insert(0,str(SKILL/'scripts'))
from original_template import load,SOURCE,NS,select
from original_build import build,verify,validate
from original_cli import diversity
from original_schema import generate

class OriginalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.folder=Path(cls.tmp.name)
        cls.deck=json.loads((SKILL/'examples/original-all.json').read_text(encoding='utf-8'));cls.out=cls.folder/'all.pptx';cls.report=build(cls.deck,cls.out,SKILL/'examples')
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def test_inventory_and_per_adapter_schema(self):
        cat=load();self.assertEqual(len(cat['slides']),82);self.assertEqual(len([p for p in cat['parts'] if p['kind']=='layouts']),77);self.assertEqual(len([p for p in cat['parts'] if p['kind']=='masters']),12)
        self.assertEqual([s['classification'] for s in cat['slides'][:5]],['instructions']*3+['icons']*2)
        self.assertEqual(len(generate()['$defs']),77)
        self.assertEqual(generate(),json.loads((SKILL/'schemas/original-deck.schema.json').read_text(encoding='utf-8')))
        self.assertLess(cat['counts']['families'],77)
    def test_every_adapter_preserves_editable_content_and_inheritance(self):
        self.assertEqual(self.report['errors'],[])
        with ZipFile(self.out) as z:
            for i,slide in enumerate(self.deck['slides'],1):
                with self.subTest(layout=slide['layout_id']):
                    root=ET.fromstring(z.read(f'ppt/slides/original{i}.xml'))
                    self.assertTrue(root.find('p:cSld/p:spTree',NS) is not None)
                    self.assertTrue(any(e.tag.endswith('}sp') for e in root.iter()))
            self.assertFalse(any(n.startswith('ppt/slides/slide') for n in z.namelist()))
    def test_reuse_reverse_order_and_inherited_field_independence(self):
        d=copy.deepcopy(self.deck);d['slides']=[copy.deepcopy(self.deck['slides'][68]),copy.deepcopy(self.deck['slides'][0]),copy.deepcopy(self.deck['slides'][68])];d['slides'][2]['id']='repeat';d['slides'][0]['fields']['layout-24']='Первый';d['slides'][2]['fields']['layout-24']='Второй'
        self.assertEqual(build(d,self.folder/'repeat.pptx',SKILL/'examples')['errors'],[])
        with ZipFile(self.folder/'repeat.pptx') as z:
            self.assertIn('Первый',z.read('ppt/slideLayouts/original1.xml').decode());self.assertNotIn('Второй',z.read('ppt/slideLayouts/original1.xml').decode());self.assertIn('Второй',z.read('ppt/slideLayouts/original3.xml').decode())
    def test_invalid_fields_overflow_and_source_slots_rejected(self):
        for mutation in ['protected','missing','overflow','instructions']:
            d=copy.deepcopy(self.deck);s=d['slides'][0]
            if mutation=='protected':s['fields']['ph-16']='Bad'
            if mutation=='missing':s['fields'].pop('ph-0')
            if mutation=='overflow':s['fields']['ph-0']='Очень длинно '*100
            if mutation=='instructions':s['layout_id']='original-03'
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):validate(d,SKILL/'examples')
    def test_native_tables_charts_and_workbooks(self):
        with ZipFile(self.out) as z:
            charts=[n for n in z.namelist() if n.startswith('ppt/charts/original') and n.endswith('.xml')];books=[n for n in z.namelist() if n.startswith('ppt/embeddings/original')]
            self.assertGreater(len(charts),7);self.assertEqual(len(charts),len(books))
            for n in charts:
                root=ET.fromstring(z.read(n));self.assertTrue(root.findall('.//{http://schemas.openxmlformats.org/drawingml/2006/chart}numCache'))
            for i in [61,62]:self.assertTrue(ET.fromstring(z.read(f'ppt/slides/original{i}.xml')).findall('.//a:tbl',NS))
    def test_reviewed_cards_are_native_rounded_surfaces(self):
        from original_style import verify_style
        record=load()['slides'][15]
        with ZipFile(self.out) as z:root=ET.fromstring(z.read('ppt/slides/original11.xml'))
        self.assertEqual(verify_style(root,record),[])
        cards=[s for s in root.findall('p:cSld/p:spTree/p:sp',NS) if s.find('p:nvSpPr/p:cNvPr',NS).get('name','').startswith('original-surface-ph-')]
        self.assertEqual(len(cards),4)
        cards[0].find('p:spPr/a:prstGeom',NS).set('prst','rect')
        self.assertTrue(verify_style(root,record))
    def test_surface_is_not_an_image_input_and_step_is_not_metric(self):
        d=copy.deepcopy(self.deck)
        d['slides'][10]['fields']['ph-34']={'path':'unused','sha256':'0'*64,'alt':'image'}
        with self.assertRaises(ValueError):validate(d,SKILL/'examples')
        self.assertEqual(load()['slides'][17]['intent'],'sequence')
    def test_step_numbers_follow_text_group(self):
        with ZipFile(self.out) as z:root=ET.fromstring(z.read('ppt/slides/original13.xml'))
        numbers=[s for s in root.findall('p:cSld/p:spTree/p:sp',NS) if s.find('.//p:ph',NS) is not None and s.find('.//p:ph',NS).get('idx') in ('14','17','20')]
        ys=[int(s.find('p:spPr/a:xfrm/a:off',NS).get('y'))/12700 for s in numbers]
        self.assertEqual(len(set(ys)),1)
        self.assertLess(ys[0],487)
    def test_photo_crop_and_source_mask(self):
        with ZipFile(self.out) as z:
            root=ET.fromstring(z.read('ppt/slides/original1.xml'))
            pic=root.find('.//p:pic',NS)
            self.assertIsNotNone(pic)
            fill=pic.find('p:blipFill/a:stretch/a:fillRect',NS)
            self.assertEqual(fill.attrib,dict(l='0',r='0',t='0',b='0'))
            self.assertIsNotNone(pic.find('p:spPr/a:custGeom',NS))
            self.assertIsNotNone(pic.find('p:blipFill/a:srcRect',NS))
    def test_detects_changed_chart_and_table_values(self):
        for role in ('chart','table'):
            d=copy.deepcopy(self.deck)
            cat={r['id']:r for r in load()['slides']}
            found=False
            for slide in d['slides']:
                for slot in cat[slide['layout_id']]['slots']:
                    if slot['role']==role and slot['id'] in slide['fields']:
                        value=slide['fields'][slot['id']]
                        if role=='chart':value['series'][0]['values'][0]=999
                        else:value['rows'][0][0]='Другое'
                        found=True;break
                if found:break
            self.assertTrue(found)
            self.assertTrue(verify(d,self.out)['errors'])
    def test_detects_inheritance_corruption(self):
        target=self.folder/'bad.pptx'
        with ZipFile(self.out) as src,ZipFile(target,'w',ZIP_DEFLATED) as out:
            for n in src.namelist():out.writestr(n,src.read(n).replace(b'F3F2F2',b'123456') if n=='ppt/slideLayouts/slideLayout1.xml' else src.read(n))
        with ZipFile(self.out) as src,ZipFile(target,'w',ZIP_DEFLATED) as out:
            for n in src.namelist():
                data=src.read(n)
                if n=='ppt/slideLayouts/slideLayout1.xml':
                    root=ET.fromstring(data);root.find('p:cSld',NS).set('name','mutation');data=ET.tostring(root)
                out.writestr(n,data)
        self.assertTrue(verify(self.deck,target)['errors'])
    def test_diversity_and_semantic_selection(self):
        s=copy.deepcopy(self.deck['slides'][0]);s.pop('repeat_reason',None);d={'slides':[dict(s,id=str(i)) for i in range(3)]};self.assertEqual(diversity(d)['warnings'],1)
        for s in d['slides']:s['repeat_reason']='Обоснованная серия'
        self.assertEqual(diversity(d)['warnings'],0)
        # Statuses become selectable only after implementation, never from inventory.
        choices=select('metrics',fields=1,allow_experimental=True);self.assertGreaterEqual(len(choices),2);self.assertTrue(all(x['status'] in ('implemented','tested') for x in choices))

class OriginalVisualTests(unittest.TestCase):
    @unittest.skipUnless(__import__('os').environ.get('CGU_ORIGINAL_RENDER_ROOT'),'Original render fixtures are opt-in')
    def test_all_source_pixels_and_regression_detection(self):
        from original_cli import compare_images
        from PIL import Image
        import os
        base=Path(os.environ['CGU_ORIGINAL_RENDER_ROOT'])
        for n in range(6,83):
            with self.subTest(source_slide=n):self.assertTrue(compare_images(base/f'source-render/preview/slide-{n:02d}.png',base/f'raw-render/preview/slide-{n-5:02d}.png')['passed'])
        src=base/'source-render/preview/slide-06.png'
        with tempfile.TemporaryDirectory() as folder:
            changed=Path(folder)/'changed.png';im=Image.open(src).convert('RGB');pixel=im.getpixel((100,100));im.putpixel((100,100),tuple(255-v for v in pixel));im.save(changed)
            self.assertFalse(compare_images(src,changed)['passed'])

    @unittest.skipUnless(__import__('os').environ.get('CGU_ORIGINAL_RENDER_ROOT'),'Original render fixtures are opt-in')
    def test_independent_diverse_render_against_filled_baseline(self):
        import os
        from original_cli import compare_images
        base=Path(os.environ.get('CGU_ORIGINAL_FILLED_ROOT',os.environ['CGU_ORIGINAL_RENDER_ROOT']))
        deck=json.loads((SKILL/'examples/original-diverse.json').read_text())
        self.assertEqual(len(deck['slides']),18)
        for i,slide in enumerate(deck['slides'],1):
            source=int(slide['layout_id'].split('-')[1])-5
            with self.subTest(layout=slide['layout_id']):
                self.assertTrue(compare_images(SKILL/f'assets/catalog/original/examples/slide-{source:02d}.png',base/f'diverse-control/output/preview/slide-{i:02d}.png')['passed'])

    @unittest.skipUnless(__import__('os').environ.get('CGU_ORIGINAL_FILLED_ROOT'),'Updated style render fixtures are opt-in')
    def test_reviewed_four_and_visible_round_corners(self):
        import os
        from PIL import Image
        from original_cli import compare_images
        base=Path(os.environ['CGU_ORIGINAL_FILLED_ROOT'])
        for i,number in enumerate([7,9,11,13],1):
            self.assertTrue(compare_images(base/f'review-final/output/preview/slide-{i}.png',base/f'all-77/output/preview/slide-{number:02d}.png')['passed'])
        im=Image.open(base/'review-final/output/preview/slide-3.png').convert('RGB')
        # The top-left bounding-box corner is gray background, the card center white.
        self.assertEqual(im.getpixel((76,196)),im.getpixel((50,196)))
        self.assertEqual(im.getpixel((200,205)),(255,255,255))
