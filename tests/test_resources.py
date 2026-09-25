import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile, ZIP_DEFLATED
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'skills/cgu-presentations'
spec = importlib.util.spec_from_file_location('audit_template', SKILL / 'scripts/audit_template.py')
audit_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit_module)

class TemplateTests(unittest.TestCase):
    def test_templates_match_manifest_and_inventory(self):
        manifest = json.loads((SKILL / 'assets/templates/manifest.json').read_text(encoding="utf-8"))
        counts = {'cgu-full.pptx': 82, 'cgu-short.pptx': 19}
        for item in manifest['templates']:
            path = SKILL / item['file']
            with self.subTest(template=path.name):
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), item['sha256'])
                result = audit_module.audit(path)
                self.assertEqual(result['slide_count'], counts[path.name])
                self.assertEqual(result['size_pt'], [1440, 810])
                self.assertEqual(result['missing_internal_targets'], [])
                self.assertEqual(result['layout_count'], 77)

    def test_slide_order_comes_from_presentation_relationships(self):
        source = SKILL / 'assets/templates/cgu-short.pptx'
        baseline = audit_module.audit(source)
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'reordered.pptx'
            with ZipFile(source) as zin, ZipFile(target, 'w', ZIP_DEFLATED) as zout:
                for item in zin.infolist():
                    data = zin.read(item.filename)
                    if item.filename == 'ppt/presentation.xml':
                        xml = ET.fromstring(data)
                        order = xml.find('p:sldIdLst', audit_module.NS)
                        first = order[0]
                        order.remove(first)
                        order.append(first)
                        data = ET.tostring(xml, encoding='utf-8', xml_declaration=True)
                    zout.writestr(item, data)
            result = audit_module.audit(target)
            self.assertEqual(result['slides'][0]['part'], baseline['slides'][1]['part'])
            self.assertEqual(result['slides'][-1]['part'], baseline['slides'][0]['part'])
            self.assertEqual(result['slides'][0]['slide_number'], 1)

    def test_missing_image_is_reported(self):
        source = SKILL / 'assets/templates/cgu-short.pptx'
        baseline = audit_module.audit(source)
        rel = next(r for s in baseline['slides'] for r in s['relationships'].values() if r['type'] == 'image' and not r['external'])
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'missing-image.pptx'
            with ZipFile(source) as zin, ZipFile(target, 'w', ZIP_DEFLATED) as zout:
                for item in zin.infolist():
                    if item.filename != rel['target']:
                        zout.writestr(item, zin.read(item.filename))
            result = audit_module.audit(target)
            self.assertIn(rel['target'], [r['target'] for r in result['missing_internal_targets']])

if __name__ == '__main__':
    unittest.main()
