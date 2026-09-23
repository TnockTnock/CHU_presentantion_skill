"""Check authored semantic invariants in a generated PPTX against its input spec."""
import json
import hashlib
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET
from audit_template import audit, relationships, NS

NS = dict(NS, c='http://schemas.openxmlformats.org/drawingml/2006/chart')

def verify(spec, pptx):
    report=audit(pptx)
    errors=[]
    if report['slide_count']!=len(spec['slides']):errors.append('Slide count mismatch')
    if report['missing_internal_targets']:errors.append('Broken package relationships')
    if report['non_golos_explicit_declarations']:errors.append('Unexpected fonts')
    checks=[]
    skill=Path(__file__).resolve().parents[1]
    adapter=json.loads((skill/'references/template-adapter.json').read_text())
    expected_logos={}
    with ZipFile(skill/adapter['template']) as source:
        for kind,page in adapter['roles'].items():
            part=f'ppt/slides/slide{page}.xml'; rels=relationships(source,part)
            root=ET.fromstring(source.read(part)); ids={'cover':['43','44'],'cards':['24','25']}.get(kind,['48','49'])
            hashes=set()
            for shape in root.findall('.//p:sp',NS):
                info=shape.find('.//p:cNvPr',NS)
                if info is not None and info.get('id') in ids:
                    for e in shape.iter():
                        rid=e.get('{'+NS['r']+'}embed')
                        if rid:hashes.add(hashlib.sha256(source.read(rels[rid]['target'])).hexdigest())
            expected_logos[kind]=hashes
    with ZipFile(pptx) as z:
        for item,desc in zip(report['slides'],spec['slides']):
            root=ET.fromstring(z.read(item['part']))
            rels=relationships(z,item['part'])
            visible_assets=set()
            for e in root.iter():
                rid=e.get('{'+NS['r']+'}embed')
                if rid and rid in rels and not rels[rid]['external']:
                    visible_assets.add(hashlib.sha256(z.read(rels[rid]['target'])).hexdigest())
            if not expected_logos[desc['kind']].issubset(visible_assets):errors.append(desc['id']+': template logo asset missing')
            names={e.get('id'):e.get('name') for e in root.findall('.//p:cNvPr',NS)}
            text=' '.join(t.text or '' for t in root.findall('.//a:t',NS))
            if spec.get('demo') and 'ДЕМОНСТРАЦИОННЫЕ ДАННЫЕ' not in text:errors.append(desc['id']+': demo disclosure missing')
            if desc['kind'] in ('process','diagram'):
                expected=[('node-step-'+str(i),'node-step-'+str(i+1)) for i in range(len(desc['steps'])-1)] if desc['kind']=='process' else [('node-'+e['from'],'node-'+e['to']) for e in desc['edges']]
                actual=[]
                for conn in root.findall('.//p:cxnSp',NS):
                    start,end=conn.find('.//a:stCxn',NS),conn.find('.//a:endCxn',NS)
                    if start is None or end is None:
                        errors.append(desc['id']+': detached connector');continue
                    actual.append((names.get(start.get('id')),names.get(end.get('id'))))
                    tail=conn.find('.//a:tailEnd',NS)
                    if tail is None or tail.get('type')!='triangle':errors.append(desc['id']+': target arrowhead missing')
                if sorted(actual)!=sorted(expected):errors.append(desc['id']+': node/edge mismatch')
                checks.append({'slide':desc['id'],'native_connectors':len(actual)})
            elif desc['kind']=='chart':
                rels=relationships(z,item['part'])
                chartparts=[r['target'] for r in rels.values() if r['type']=='chart']
                if len(chartparts)!=1:errors.append(desc['id']+': expected one native chart');continue
                chart=ET.fromstring(z.read(chartparts[0]))
                series=chart.findall('.//c:ser',NS)
                if len(series)!=len(desc['series']):errors.append(desc['id']+': series count mismatch')
                for xml,source in zip(series,desc['series']):
                    vals=[float(e.text) for e in xml.findall('c:val//c:pt/c:v',NS)]
                    cats=[e.text for e in xml.findall('c:cat//c:pt/c:v',NS)]
                    if vals!=source['values'] or cats!=desc['categories']:errors.append(desc['id']+': chart data mismatch')
                if chart.find('c:externalData',NS) is None:errors.append(desc['id']+': chart workbook missing')
                checks.append({'slide':desc['id'],'native_chart':True,'series':len(series)})
            elif desc['kind']=='table':
                table=root.find('.//a:tbl',NS)
                if table is None:errors.append(desc['id']+': native table missing');continue
                values=[[''.join(t.text or '' for t in cell.findall('.//a:t',NS)) for cell in row.findall('a:tc',NS)] for row in table.findall('a:tr',NS)]
                if values!=[desc['columns']]+desc['rows']:errors.append(desc['id']+': table values mismatch')
                checks.append({'slide':desc['id'],'native_table':True})
    return {'errors':errors,'checks':checks,'pptx_sha256':report['sha256']}

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('spec');p.add_argument('pptx');p.add_argument('--out');a=p.parse_args()
    result=verify(json.loads(Path(a.spec).read_text()),a.pptx)
    if a.out:Path(a.out).write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result,ensure_ascii=False,indent=2))
    raise SystemExit(bool(result['errors']))
