"""Normalize a working OOXML copy to shipped Golos fonts; originals untouched."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from xml.etree import ElementTree as ET
import argparse
P = '{http://schemas.openxmlformats.org/presentationml/2006/main}'
A = '{http://schemas.openxmlformats.org/drawingml/2006/main}'

def normalize(source, destination):
    source, destination = Path(source), Path(destination)
    if source.resolve() == destination.resolve():
        raise ValueError('Source and destination must differ')
    changed = 0
    with ZipFile(source) as zin, ZipFile(destination, 'w', ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            if item.filename.startswith('ppt/fonts/'):
                continue
            data = zin.read(item.filename)
            if item.filename.endswith('.rels') or item.filename == '[Content_Types].xml':
                root = ET.fromstring(data)
                ET.register_namespace('', root.tag.split('}')[0][1:])
                for child in list(root):
                    if child.get('Type', '').endswith('/font') or child.get('PartName', '').startswith('/ppt/fonts/') or child.get('Extension', '') in ('fntdata', 'odttf'):
                        root.remove(child)
                data = ET.tostring(root, encoding='utf-8', xml_declaration=True)
            if item.filename.startswith('ppt/') and item.filename.endswith('.xml'):
                root = ET.fromstring(data)
                for e in list(root):
                    if e.tag == P+'embeddedFontLst':
                        root.remove(e)
                for parent in root.iter():
                    # Preserve roles: DemiBold becomes the supplied SemiBold family.
                    for child in list(parent):
                        if child.get('typeface') is not None:
                            original = child.get('typeface')
                            if any(s in original.lower() for s in ('demi', 'semi', 'intro bold')):
                                target = 'Golos Text SemiBold'
                                if parent.tag in (A+'rPr', A+'defRPr', A+'endParaRPr'):
                                    parent.set('b', '0')
                            else:
                                target = 'Golos Text'
                            if original != target:
                                child.set('typeface', target)
                                changed += 1
                data = ET.tostring(root, encoding='utf-8', xml_declaration=True)
            zout.writestr(item, data)
    return changed

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source'); p.add_argument('destination')
    a = p.parse_args()
    print(normalize(a.source, a.destination))
