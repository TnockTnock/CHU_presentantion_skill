"""Validate the executable layout registry against immutable template resources."""
import hashlib
import json
from pathlib import Path
import re
from zipfile import ZipFile
from xml.etree import ElementTree as ET
from audit_template import NS, relationships
from spec import KINDS

def inspect(skill):
    skill=Path(skill);errors=[]
    registry=json.loads((skill/'design-system/layouts.json').read_text(encoding="utf-8"))
    tokens=json.loads((skill/'design-system/tokens.json').read_text(encoding="utf-8"))
    manifest=json.loads((skill/'assets/templates/manifest.json').read_text(encoding="utf-8"))
    template=skill/registry['template']
    digest=hashlib.sha256(template.read_bytes()).hexdigest()
    declared=next(t['sha256'] for t in manifest['templates'] if t['file']==registry['template'])
    if digest!=registry['template_sha256'] or digest!=declared:errors.append('Template SHA mismatch')
    layouts=registry['layouts']
    if {x['kind'] for x in layouts}!=KINDS or len(layouts)!=len(KINDS):errors.append('Registry kinds mismatch')
    if len({x['key'] for x in layouts})!=len(layouts):errors.append('Duplicate layout key')
    if any(not re.fullmatch(r'#[0-9A-Fa-f]{6}',v) for v in tokens['colors'].values()):errors.append('Invalid color token')
    with ZipFile(template) as z:
        if z.testzip():errors.append('Template ZIP CRC failure')
        for layout in layouts:
            part=layout['source_part'];root=ET.fromstring(z.read(part))
            ids={x.get('id') for x in root.findall('.//p:cNvPr',NS)}
            def leaves(value):
                if isinstance(value,dict):return [s for v in value.values() for s in leaves(v)]
                if isinstance(value,list):return [s for v in value for s in leaves(v)]
                return [value]
            targets=leaves(layout['slots'])+layout['logo_shape_ids']+(layout['keep_shape_ids'] or [])+layout['remove_shape_ids']
            if not set(targets)<=ids:errors.append(layout['key']+': missing bound shape')
            if not any(x['type']=='slideLayout' for x in relationships(z,part).values()):errors.append(layout['key']+': layout relationship missing')
            if layout['binding_status']!='implemented':errors.append(layout['key']+': adapter not implemented')
    return {'errors':errors,'layout_count':len(layouts),'template_sha256':digest,'visual_review':'not performed by preflight','powerpoint':'not tested'}

if __name__=='__main__':
    result=inspect(Path(__file__).resolve().parents[1]);print(json.dumps(result,ensure_ascii=False,indent=2));raise SystemExit(bool(result['errors']))
