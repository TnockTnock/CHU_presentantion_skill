#!/usr/bin/env python3
"""Inventory PPTX OOXML; not a renderer or complete inherited-style validator."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import posixpath
import re
from xml.etree import ElementTree as ET
from zipfile import ZipFile

NS = {
    'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
    'p': 'http://schemas.openxmlformats.org/presentationml/2006/main',
    'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
}
REL = '{http://schemas.openxmlformats.org/package/2006/relationships}Relationship'

def relationships(z, part):
    path = posixpath.join(posixpath.dirname(part), '_rels', posixpath.basename(part) + '.rels')
    if path not in z.namelist():
        return {}
    result = {}
    for r in ET.fromstring(z.read(path)).findall(REL):
        target = r.get('Target', '')
        external = r.get('TargetMode') == 'External'
        resolved = target if external else posixpath.normpath(posixpath.join(posixpath.dirname(part), target)).lstrip('/')
        result[r.get('Id')] = {'target': resolved, 'type': r.get('Type', '').rsplit('/', 1)[-1], 'external': external}
    return result

def inventory(z, part):
    root = ET.fromstring(z.read(part))
    fonts = Counter(e.get('typeface') for e in root.iter() if e.get('typeface'))
    colors = Counter(e.get('val') for e in root.findall('.//a:srgbClr', NS))
    fields = []
    for shape in root.findall('.//p:sp', NS):
        info = shape.find('p:nvSpPr/p:cNvPr', NS)
        ph = shape.find('p:nvSpPr/p:nvPr/p:ph', NS)
        xfrm = shape.find('p:spPr/a:xfrm', NS)
        box = None
        if xfrm is not None:
            off, ext = xfrm.find('a:off', NS), xfrm.find('a:ext', NS)
            if off is not None and ext is not None:
                box = [round(int(v) / 12700, 3) for v in [off.get('x'), off.get('y'), ext.get('cx'), ext.get('cy')]]
        fields.append({
            'shape_id': info.get('id') if info is not None else None,
            'name': info.get('name') if info is not None else None,
            'placeholder': dict(ph.attrib) if ph is not None else None,
            'local_box_pt': box,
            'text': '\n'.join(''.join(t.text or '' for t in p.findall('.//a:t', NS)) for p in shape.findall('.//a:p', NS)),
        })
    return {'part': part, 'name': root.find('p:cSld', NS).get('name') if root.find('p:cSld', NS) is not None else None,
            'fonts': dict(fonts), 'explicit_rgb_colors': dict(colors), 'fields': fields,
            'picture_count': len(root.findall('.//p:pic', NS)), 'relationships': relationships(z, part)}

def audit(path):
    path = Path(path)
    with ZipFile(path) as z:
        bad = z.testzip()
        if bad:
            raise ValueError('Corrupt ZIP member: ' + bad)
        presentation = ET.fromstring(z.read('ppt/presentation.xml'))
        size = presentation.find('p:sldSz', NS)
        rels = relationships(z, 'ppt/presentation.xml')
        slides = []
        for order, node in enumerate(presentation.findall('p:sldIdLst/p:sldId', NS), 1):
            rid = node.get('{' + NS['r'] + '}id')
            part = rels[rid]['target']
            entry = inventory(z, part)
            entry['slide_number'] = order
            slides.append(entry)
        groups = {}
        for label, folder in [('layouts', 'slideLayouts'), ('masters', 'slideMasters'), ('themes', 'theme')]:
            parts = sorted(n for n in z.namelist() if re.fullmatch(r'ppt/' + folder + r'/[^/]+\.xml', n))
            groups[label] = [inventory(z, n) for n in parts]
        # Count every XML part, including charts, notes and default text styles.
        fonts = Counter()
        broken = []
        names = set(z.namelist())
        for part in sorted(names):
            if part.endswith('.xml'):
                root = ET.fromstring(z.read(part))
                fonts.update(e.get('typeface') for e in root.iter() if e.get('typeface'))
                for r in relationships(z, part).values():
                    if not r['external'] and r['target'] not in names:
                        broken.append({'from': part, 'target': r['target']})
        return {
            'file': str(path.resolve()), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'size_pt': [int(size.get(k)) / 12700 for k in ('cx', 'cy')],
            'slide_count': len(slides), 'layout_count': len(groups['layouts']), 'master_count': len(groups['masters']),
            'font_declarations_all_xml': dict(fonts),
            'non_golos_explicit_declarations': {k: v for k, v in fonts.items() if not k.startswith('+') and not k.lower().startswith('golos')},
            'missing_internal_targets': broken, 'slides': slides, **groups,
            'limits': ['Style inheritance is not resolved.', 'Geometry is local to each shape/group, not absolute.',
                       'RGB inventory excludes scheme colors and image pixels.', 'No rendering, overflow or font-availability check.'],
        }

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pptx', type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    if args.out.resolve() == args.pptx.resolve():
        parser.error('--out must not overwrite the input PPTX')
    report = audit(args.pptx)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: report[k] for k in ['slide_count', 'layout_count', 'master_count', 'size_pt', 'non_golos_explicit_declarations']}, ensure_ascii=False))

if __name__ == '__main__':
    main()
