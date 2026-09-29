import copy,json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'skills/cgu-presentations/scripts'))
from original_starter import initialize
from original_build import validate

class ReleaseTests(unittest.TestCase):
    def test_starter_portable_assets_and_original_contract(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'starter';initialize(out)
            deck=json.loads((out/'deck.json').read_text());validate(deck,out)
            self.assertEqual([s['layout_id'] for s in deck['slides']],['original-12','original-14','original-16','original-18'])
            for s in deck['slides']:
                for v in s['fields'].values():
                    if isinstance(v,dict) and 'path' in v:self.assertTrue((out/v['path']).is_file())
            with self.assertRaisesRegex(ValueError,'empty'):initialize(out)
    def test_explicit_experimental_and_production_gate(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'starter'
            with self.assertRaisesRegex(ValueError,'Experimental'):initialize(out,['original-06'])
            initialize(out,['original-06'],True)
            deck=json.loads((out/'deck.json').read_text());validate(deck,out)
            for policy in ('usable','production','typo'):
                with self.subTest(policy=policy):
                    invalid=copy.deepcopy(deck);invalid['readiness_policy']=policy
                    with self.assertRaises(ValueError):validate(invalid,out)
