"""Native DrawingML primitives and chart workbooks. Standard library only."""
from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED
from xml.etree import ElementTree as ET
from number_typography import transform

NS={'a':'http://schemas.openxmlformats.org/drawingml/2006/main','p':'http://schemas.openxmlformats.org/presentationml/2006/main','r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships','c':'http://schemas.openxmlformats.org/drawingml/2006/chart','rel':'http://schemas.openxmlformats.org/package/2006/relationships','ct':'http://schemas.openxmlformats.org/package/2006/content-types','s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
def tag(t):
    prefix,name=t.split(':');return '{'+NS[prefix]+'}'+name

def el(qname,parent=None,**attrs):
    element=ET.Element(tag(qname),{k:str(v) for k,v in attrs.items()})
    if parent is not None:parent.append(element)
    return element

def xml(e):
    if e.tag==tag('ct:Types'):ET.register_namespace('',NS['ct'])
    elif e.tag==tag('rel:Relationships'):ET.register_namespace('',NS['rel'])
    return ET.tostring(e,encoding='utf-8',xml_declaration=True)
def fill(parent,color):el('a:srgbClr',el('a:solidFill',parent),val=color.lstrip('#'))
def pos(parent,b,**attrs):
    x,y,w,h=b;xf=el('a:xfrm',parent,**attrs);el('a:off',xf,x=round(x*9525),y=round(y*9525));el('a:ext',xf,cx=round(w*9525),cy=round(h*9525));return xf

def props(parent,pt,heading,color,kind='a:rPr'):
    r=el(kind,parent,lang='ru-RU',sz=round(pt*100),b=0);fill(r,color)
    for t in ('latin','ea','cs'):el('a:'+t,r,typeface='Golos Text SemiBold' if heading else 'Golos Text')
    return r

def textbody(parent,text,pt=24,heading=False,color='#000000',align='left',center=False,pad=0,kind='p:txBody'):
    tx=el(kind,parent);bp=el('a:bodyPr',tx,wrap='square',anchor='ctr' if center else 't',lIns=round(pad*9525),rIns=round(pad*9525),tIns=round(pad*9525),bIns=round(pad*9525));el('a:noAutofit',bp);el('a:lstStyle',tx)
    for line in text.split('\n'):
        p=el('a:p',tx);pr=el('a:pPr',p,algn={'left':'l','center':'ctr','right':'r'}[align]);el('a:spcPts',el('a:lnSpc',pr),val=round(pt*118));el('a:spcPts',el('a:spcAft',pr),val=0)
        run=el('a:r',p);props(run,pt,heading,color);el('a:t',run).text=line
        props(p,pt,heading,color,'a:endParaRPr')
        if kind=='c:txPr':props(pr,pt,heading,color,'a:defRPr')
    transform(tx)
    return tx

def shape(tree,id,name,b,text=None,pt=24,heading=False,color='#000000',background=None,align='left',center=False,pad=0):
    s=el('p:sp',tree);nv=el('p:nvSpPr',s);el('p:cNvPr',nv,id=id,name=name);el('p:cNvSpPr',nv,txBox=1 if background is None else 0);el('p:nvPr',nv)
    sp=el('p:spPr',s);pos(sp,b);av=el('a:avLst',el('a:prstGeom',sp,prst='roundRect' if background else 'rect'))
    if background:el('a:gd',av,name='adj',fmla='val '+str(min(50000,round(24/min(b[2:])*100000))))
    fill(sp,background) if background else el('a:noFill',sp)
    el('a:noFill',el('a:ln',sp,w=0))
    if text is not None:textbody(s,text,pt,heading,color,align,center,pad)
    return s

def connector(tree,id,a,b,boxes,start='right',end='left',color='#FF254A'):
    def point(box,side):
        x,y,w,h=box;return {'left':(x,y+h/2),'right':(x+w,y+h/2),'top':(x+w/2,y),'bottom':(x+w/2,y+h)}[side]
    x,y=point(boxes[a],start);xx,yy=point(boxes[b],end)
    s=el('p:cxnSp',tree);nv=el('p:nvCxnSpPr',s);el('p:cNvPr',nv,id=id,name='connector-'+str(id));cn=el('p:cNvCxnSpPr',nv)
    sites={'top':0,'left':1,'bottom':2,'right':3};el('a:stCxn',cn,id=a,idx=sites[start]);el('a:endCxn',cn,id=b,idx=sites[end]);el('p:nvPr',nv)
    sp=el('p:spPr',s)
    if start==end=='top' and y==yy:
        # Native U-return above both nodes; endpoint bindings remain attached.
        w=max(1,round(abs(xx-x)*9525));h=round(50*9525)
        pos(sp,[min(x,xx),y-50,abs(xx-x),50],flipH=int(xx<x))
        geom=el('a:custGeom',sp);el('a:avLst',geom);el('a:gdLst',geom);el('a:ahLst',geom);el('a:cxnLst',geom);el('a:rect',geom,l=0,t=0,r='r',b='b')
        path=el('a:path',el('a:pathLst',geom),w=w,h=h,fill='none')
        for command,px,py in [('moveTo',0,h),('lnTo',0,0),('lnTo',w,0),('lnTo',w,h)]:el('a:pt',el('a:'+command,path),x=px,y=py)
    else:
        pos(sp,[min(x,xx),min(y,yy),abs(xx-x),abs(yy-y)],flipH=int(xx<x),flipV=int(yy<y));el('a:avLst',el('a:prstGeom',sp,prst='line' if x==xx or y==yy else 'bentConnector3'))
    ln=el('a:ln',sp,w=28575);fill(ln,color);el('a:tailEnd',ln,type='triangle',w='med',len='med')

def frame(tree,id,name,b,uri):
    f=el('p:graphicFrame',tree);nv=el('p:nvGraphicFramePr',f);el('p:cNvPr',nv,id=id,name=name);el('p:cNvGraphicFramePr',nv);el('p:nvPr',nv)
    x,y,w,h=b;xf=el('p:xfrm',f);el('a:off',xf,x=round(x*9525),y=round(y*9525));el('a:ext',xf,cx=round(w*9525),cy=round(h*9525))
    return el('a:graphicData',el('a:graphic',f),uri=uri)

def table(tree,id,columns,rows,metrics,y=285,max_height=620,pt=24,row_height=100):
    values=[columns]+rows;n=len(values);nc=len(columns);h=min(max_height,n*row_height);w=1720/nc
    tbl=el('a:tbl',frame(tree,id,'native-table',[100,y,1720,h],NS['a'].rsplit('/',1)[0]+'/table'));el('a:tblPr',tbl,firstRow=1,bandRow=0);grid=el('a:tblGrid',tbl)
    for _ in columns:el('a:gridCol',grid,w=round(w*9525))
    for i,row in enumerate(values):
        tr=el('a:tr',tbl,h=round(h/n*9525))
        for value in row:
            metrics.check(value,w-40,h/n-24,pt,i==0,'table cell')
            tc=el('a:tc',tr);textbody(tc,value,pt,i==0,center=True,kind='a:txBody');pr=el('a:tcPr',tc,marL=190500,marR=190500,marT=114300,marB=114300,anchor='ctr')
            for side in ('L','R','T','B'):
                ln=el('a:ln'+side,pr,w=9525);fill(ln,'#E4E4E4' if side=='T' and i else '#FFFFFF');el('a:prstDash',ln,val='solid')
            fill(pr,'#F3F2F2' if i==0 else '#FFFFFF')

def workbook(categories,series):
    out=BytesIO();sheet=el('s:worksheet');data=el('s:sheetData',sheet)
    values=[['Category']+[s['name'] for s in series]]+[[c]+[s['values'][i] for s in series] for i,c in enumerate(categories)]
    for i,row in enumerate(values,1):
        r=el('s:row',data,r=i)
        for j,value in enumerate(row):
            c=el('s:c',r,r=chr(65+j)+str(i),t='inlineStr' if isinstance(value,str) else 'n')
            if isinstance(value,str):el('s:t',el('s:is',c)).text=value
            else:el('s:v',c).text=str(value)
    wb=el('s:workbook');el('s:sheet',el('s:sheets',wb),name='Data',sheetId=1,**{tag('r:id'):'rId1'})
    rel=el('rel:Relationships');el('rel:Relationship',rel,Id='rId1',Type=NS['r']+'/worksheet',Target='worksheets/sheet1.xml')
    rootrel=el('rel:Relationships');el('rel:Relationship',rootrel,Id='rId1',Type=NS['r']+'/officeDocument',Target='xl/workbook.xml')
    ct=el('ct:Types');el('ct:Default',ct,Extension='rels',ContentType='application/vnd.openxmlformats-package.relationships+xml');el('ct:Default',ct,Extension='xml',ContentType='application/xml')
    for part,kind in [('workbook','sheet.main'),('worksheets/sheet1','worksheet')]:el('ct:Override',ct,PartName='/xl/'+part+'.xml',ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.'+kind+'+xml')
    with ZipFile(out,'w',ZIP_DEFLATED) as z:
        for name,root in {'[Content_Types].xml':ct,'_rels/.rels':rootrel,'xl/workbook.xml':wb,'xl/_rels/workbook.xml.rels':rel,'xl/worksheets/sheet1.xml':sheet}.items():z.writestr(name,xml(root))
    return out.getvalue()

def chart_xml(d,colors):
    root=el('c:chartSpace');el('c:lang',root,val='ru-RU');chart=el('c:chart',root);el('c:autoTitleDeleted',chart,val=1);plot=el('c:plotArea',chart);el('c:layout',plot)
    bar=d.get('chart_type','bar')=='bar';typ=el('c:barChart' if bar else 'c:lineChart',plot)
    if bar:el('c:barDir',typ,val='col')
    el('c:grouping',typ,val='clustered' if bar else 'standard');el('c:varyColors',typ,val=0)
    def cache(parent,values,numeric,formula):
        ref=el('c:numRef' if numeric else 'c:strRef',parent);el('c:f',ref).text=formula;cc=el('c:numCache' if numeric else 'c:strCache',ref)
        if numeric:el('c:formatCode',cc).text='General'
        el('c:ptCount',cc,val=len(values))
        for i,value in enumerate(values):el('c:v',el('c:pt',cc,idx=i)).text=str(value)
    for i,series in enumerate(d['series']):
        ser=el('c:ser',typ);el('c:idx',ser,val=i);el('c:order',ser,val=i);cache(el('c:tx',ser),[series['name']],False,f'Data!${chr(66+i)}$1')
        sp=el('c:spPr',ser);fill(sp,colors[i]);ln=el('a:ln',sp,w=28575);fill(ln,colors[i])
        if bar:el('c:invertIfNegative',ser,val=0)
        if not bar:
            marker=el('c:marker',ser);el('c:symbol',marker,val='circle');el('c:size',marker,val=7)
        n=len(d['categories'])+1;cache(el('c:cat',ser),d['categories'],False,f'Data!$A$2:$A${n}');cache(el('c:val',ser),series['values'],True,f'Data!${chr(66+i)}$2:${chr(66+i)}${n}')
        if not bar:el('c:smooth',ser,val=0)
    labels=el('c:dLbls',typ);textbody(labels,'',18,kind='c:txPr');el('c:dLblPos',labels,val='outEnd' if bar else 't')
    for option in ('showLegendKey','showVal','showCatName','showSerName','showPercent','showBubbleSize'):el('c:'+option,labels,val=int(option=='showVal'))
    if bar:el('c:gapWidth',typ,val=95);el('c:overlap',typ,val=0)
    for i in (123,456):el('c:axId',typ,val=i)
    vals=[v for s in d['series'] for v in s['values']]
    for numeric,id,other,side in [(False,123,456,'b'),(True,456,123,'l')]:
        ax=el('c:valAx' if numeric else 'c:catAx',plot);el('c:axId',ax,val=id);scale=el('c:scaling',ax);el('c:orientation',scale,val='minMax')
        if numeric:
            el('c:max',scale,val=max(vals)*1.2 if max(vals)>0 else 1);el('c:min',scale,val=min(vals)*1.2 if min(vals)<0 else 0)
        el('c:delete',ax,val=0);el('c:axPos',ax,val=side)
        if numeric:fill(el('a:ln',el('c:spPr',el('c:majorGridlines',ax)),w=9525),'#E4E4E4')
        el('c:numFmt',ax,formatCode='0.##' if numeric else 'General',sourceLinked=0);el('c:majorTickMark',ax,val='none');el('c:minorTickMark',ax,val='none');el('c:tickLblPos',ax,val='low' if not numeric else 'nextTo');textbody(ax,'',18,kind='c:txPr');el('c:crossAx',ax,val=other);el('c:crosses',ax,val='autoZero')
        if numeric:el('c:crossBetween',ax,val='between')
        else:el('c:lblAlgn',ax,val='ctr');el('c:lblOffset',ax,val=100)
    if len(d['series'])>1:
        legend=el('c:legend',chart);el('c:legendPos',legend,val='b');el('c:overlay',legend,val=0);textbody(legend,'',20,kind='c:txPr')
    el('c:plotVisOnly',chart,val=1);el('c:dispBlanksAs',chart,val='gap');textbody(root,'',18,kind='c:txPr');external=el('c:externalData',root,**{tag('r:id'):'rIdWorkbook'});el('c:autoUpdate',external,val=0)
    transform(root);return root


def picture(tree,id,rid,box,width,height,alt):
    x,y,w,h=box;scale=min(w/width,h/height);nw,nh=width*scale,height*scale
    pic=el('p:pic',tree);nv=el('p:nvPicPr',pic);el('p:cNvPr',nv,id=id,name='profile-image',descr=alt);el('a:picLocks',el('p:cNvPicPr',nv),noChangeAspect=1);el('p:nvPr',nv)
    bf=el('p:blipFill',pic);el('a:blip',bf,**{tag('r:embed'):rid});el('a:fillRect',el('a:stretch',bf))
    sp=el('p:spPr',pic);pos(sp,[x+(w-nw)/2,y+(h-nh)/2,nw,nh]);el('a:avLst',el('a:prstGeom',sp,prst='rect'))

def image_size(data):
    import struct
    if data.startswith(b'\x89PNG'):return struct.unpack('>II',data[16:24])
    if data.startswith(b'\xff\xd8'):
        i=2
        while i<len(data):
            if data[i]!=255:i+=1;continue
            marker=data[i+1];i+=2
            if marker in (216,217):continue
            size=int.from_bytes(data[i:i+2],'big')
            if marker in (192,193,194):return (int.from_bytes(data[i+5:i+7],'big'),int.from_bytes(data[i+3:i+5],'big'))
            i+=size
    raise ValueError('Only PNG/JPEG profile images are supported')
