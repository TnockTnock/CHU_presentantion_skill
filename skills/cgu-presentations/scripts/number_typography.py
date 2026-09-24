"""Apply numeric Bold to an authored working PPTX, preserving text and geometry."""
import copy
import re
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from xml.etree import ElementTree as ET

A = '{http://schemas.openxmlformats.org/drawingml/2006/main}'
C = '{http://schemas.openxmlformats.org/drawingml/2006/chart}'
NUMBER = re.compile(r'[+−-]?\d+(?:[ \u00a0\u202f]\d{3})*(?:[.,:/–−-]\d+)*(?:[%‰+])?')

def bold(props):
    props.set('b', '1')
    for tag in ('latin', 'ea', 'cs'):
        font = props.find(A+tag)
        if font is None:
            font = ET.SubElement(props, A+tag)
        font.set('typeface', 'Golos Text')

def transform(root):
    for paragraph in root.iter(A+'p'):
        for run in list(paragraph):
            if run.tag != A+'r':
                continue
            text = run.find(A+'t')
            if text is None or not text.text or not NUMBER.search(text.text):
                continue
            original = text.text
            index = list(paragraph).index(run)
            segments = []; last = 0
            for match in NUMBER.finditer(original):
                if match.start() > last:
                    segments.append((original[last:match.start()], False))
                segments.append((match.group(), True)); last = match.end()
            if last < len(original):
                segments.append((original[last:], False))
            paragraph.remove(run)
            for offset, (value, numeric) in enumerate(segments):
                clone = copy.deepcopy(run)
                clone.find(A+'t').text = value
                if numeric:
                    props = clone.find(A+'rPr')
                    if props is None:
                        props = ET.Element(A+'rPr'); clone.insert(0, props)
                    bold(props)
                paragraph.insert(index+offset, clone)
    # Cached chart numbers are data, not text runs. Style the native labels/axis.
    owners = list(root.iter(C+'valAx')) + list(root.iter(C+'dLbls'))
    categories = root.findall('.//'+C+'cat//'+C+'v')
    if any(re.search(r'\d', e.text or '') for e in categories):
        owners += list(root.iter(C+'catAx'))
    for owner in owners:
        tx = owner.find(C+'txPr')
        if tx is None:
            tx = ET.SubElement(owner, C+'txPr')
            ET.SubElement(tx, A+'bodyPr'); ET.SubElement(tx, A+'lstStyle')
        para = tx.find(A+'p')
        if para is None: para = ET.SubElement(tx, A+'p')
        ppr = para.find(A+'pPr')
        if ppr is None: ppr = ET.Element(A+'pPr'); para.insert(0, ppr)
        props = ppr.find(A+'defRPr')
        if props is None: props = ET.SubElement(ppr, A+'defRPr')
        bold(props)
        for props in tx.iter():
            if props.tag in (A+'rPr', A+'endParaRPr'): bold(props)

def apply(source, destination):
    if Path(source).resolve() == Path(destination).resolve():
        raise ValueError('Source and destination must differ')
    with ZipFile(source) as zin, ZipFile(destination, 'w', ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if re.fullmatch(r'ppt/(slides/slide\d+|(?:slides/)?charts/chart\d+)\.xml', item.filename):
                root = ET.fromstring(data); transform(root)
                data = ET.tostring(root, encoding='utf-8', xml_declaration=True)
            zout.writestr(item, data)

def numeric_errors(root):
    errors = []
    for run in root.iter(A+'r'):
        value = run.find(A+'t')
        if value is None or not re.search(r'\d', value.text or ''): continue
        props = run.find(A+'rPr')
        font = props.find(A+'latin') if props is not None else None
        if props is None or props.get('b') != '1' or font is None or font.get('typeface') != 'Golos Text':
            errors.append('number must use Golos Text Bold: '+(value.text or ''))
    for tag in ('valAx', 'dLbls'):
        for owner in root.iter(C+tag):
            props = owner.find(C+'txPr/'+A+'p/'+A+'pPr/'+A+'defRPr')
            if props is None or props.get('b') != '1': errors.append('native chart numeric style missing: '+tag)
    return errors

if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source'); p.add_argument('destination'); a = p.parse_args()
    apply(a.source, a.destination)
