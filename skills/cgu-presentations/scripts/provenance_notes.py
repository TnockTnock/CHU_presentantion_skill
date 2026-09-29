"""Write and verify addressable provenance in native PowerPoint notes."""
import posixpath
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
from xml.etree import ElementTree as ET
from audit_template import audit,NS
from portable_ooxml import el,xml,shape
from content_model import notes_text


def write(deck,pptx):
    pptx=Path(pptx);slides=audit(pptx)['slides']
    if len(slides)!=len(deck['slides']):raise ValueError('Notes slide count mismatch')
    with ZipFile(pptx) as z:parts={n:z.read(n) for n in z.namelist()}
    ct=ET.fromstring(parts['[Content_Types].xml'])
    for i,(slide,content) in enumerate(zip(slides,deck['slides']),1):
        part=slide['part'];rp=posixpath.dirname(part)+'/_rels/'+posixpath.basename(part)+'.rels';rels=ET.fromstring(parts[rp])
        old=next((r for r in rels if r.get('Type','').endswith('/notesSlide')),None)
        if old is not None:
            np=posixpath.normpath(posixpath.join(posixpath.dirname(part),old.get('Target')))
        else:
            np=f'ppt/notesSlides/provenance{i}.xml';rid='rIdProvenance'
            while any(r.get('Id')==rid for r in rels):rid+='X'
            el('rel:Relationship',rels,Id=rid,Type=NS['r']+'/notesSlide',Target='../notesSlides/'+posixpath.basename(np))
        notes=el('p:notes');tree=el('p:spTree',el('p:cSld',notes));group=el('p:nvGrpSpPr',tree);el('p:cNvPr',group,id=1,name='');el('p:cNvGrpSpPr',group);el('p:nvPr',group);el('p:grpSpPr',tree)
        body=shape(tree,2,'Provenance',[40,40,640,900],notes_text(deck,content),12)
        el('p:ph',body.find('p:nvSpPr/p:nvPr',NS),type='body',idx=1)
        nr=el('rel:Relationships');el('rel:Relationship',nr,Id='rIdSlide',Type=NS['r']+'/slide',Target='../slides/'+posixpath.basename(part))
        # Reuse the source notes master when present, without changing it.
        master=next((n for n in parts if n.startswith('ppt/notesMasters/') and n.endswith('.xml') and '/_rels/' not in n),None)
        if master:el('rel:Relationship',nr,Id='rIdMaster',Type=NS['r']+'/notesMaster',Target='../notesMasters/'+posixpath.basename(master))
        parts[np]=xml(notes);parts[rp]=xml(rels);parts[posixpath.dirname(np)+'/_rels/'+posixpath.basename(np)+'.rels']=xml(nr)
        if not any(e.get('PartName')=='/'+np for e in ct):el('ct:Override',ct,PartName='/'+np,ContentType='application/vnd.openxmlformats-officedocument.presentationml.notesSlide+xml')
    parts['[Content_Types].xml']=xml(ct)
    temporary=pptx.with_suffix('.notes.tmp')
    try:
        with ZipFile(temporary,'w',ZIP_DEFLATED) as z:
            for n,data in parts.items():z.writestr(n,data)
        temporary.replace(pptx)
    finally:
        if temporary.exists():temporary.unlink()
    verify(deck,pptx)


def verify(deck,pptx):
    report=audit(pptx)
    with ZipFile(pptx) as z:
        for content,slide in zip(deck['slides'],report['slides']):
            notes=[r['target'] for r in slide['relationships'].values() if r['type']=='notesSlide']
            if len(notes)!=1:raise ValueError('Missing or ambiguous notes')
            root=ET.fromstring(z.read(notes[0]));actual='\n'.join(''.join(t.text or '' for t in p.findall('.//a:t',NS)) for p in root.findall('.//a:p',NS))
            if actual!=notes_text(deck,content):raise ValueError('Notes provenance changed: '+content['id'])
    return {'status':'passed','slides':len(deck['slides']),'powerpoint':'not-tested'}
