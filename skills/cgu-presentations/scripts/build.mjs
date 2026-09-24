import fs from 'node:fs/promises';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {createRequire} from 'node:module';
import {spawnSync} from 'node:child_process';
const skill=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const [specFile,outDir,runtimeDir,presentationSkill,python] = process.argv.slice(2);
if(!python) throw Error('Internal CLI: build.mjs spec out runtime presentation-skill python');
process.env.RUNTIME_NODE_MODULES=path.join(runtimeDir,'node/node_modules');
const requireRuntime=createRequire(path.join(runtimeDir,'node/node_modules/entry.cjs'));
const {GlobalFonts,createCanvas}=requireRuntime('@napi-rs/canvas');
GlobalFonts.registerFromPath(path.join(skill,'assets/fonts/GolosText_400Regular.ttf'),'Golos Text');
GlobalFonts.registerFromPath(path.join(skill,'assets/fonts/GolosText_600SemiBold.ttf'),'Golos Text SemiBold');
GlobalFonts.registerFromPath(path.join(skill,'assets/fonts/GolosText_700Bold.ttf'),'Golos Text');
const {FileBlob,Presentation,PresentationFile}=await import(pathToFileURL(requireRuntime.resolve('@oai/artifact-tool')).href);
const {finalizePresentation,applyPresentationChartFont}=await import(pathToFileURL(path.join(presentationSkill,'container_tools/artifact_tool_utils.mjs')).href);
const spec=JSON.parse(await fs.readFile(specFile,'utf8'));
const manifest=JSON.parse(await fs.readFile(path.join(skill,'assets/templates/manifest.json'),'utf8'));
const adapter=JSON.parse(await fs.readFile(path.join(skill,'design-system/layouts.json'),'utf8'));
const tokens=JSON.parse(await fs.readFile(path.join(skill,'design-system/tokens.json'),'utf8'));
const layouts=Object.fromEntries(adapter.layouts.map(x=>[x.kind,x]));
const template=path.join(skill,adapter.template);
const hash=createHash('sha256').update(await fs.readFile(template)).digest('hex');
if(hash!==adapter.template_sha256 || hash!==manifest.templates.find(x=>x.file===adapter.template).sha256) throw Error('Template hash mismatch: adapter must be revalidated');
const scratch=path.join(outDir,'build');
await fs.mkdir(scratch,{recursive:true});
await fs.mkdir(path.join(outDir,'output'),{recursive:true});
await fs.mkdir(path.join(outDir,'qa'),{recursive:true});
function normalize(src,dst){const r=spawnSync(python,[path.join(skill,'scripts/normalize_fonts.py'),src,dst],{encoding:'utf8'});if(r.status!==0) throw Error(r.stderr);}
const normalized=path.join(scratch,'template-golos.pptx');normalize(template,normalized);
const imported=await PresentationFile.importPptx(await FileBlob.load(normalized));
const inspection=await imported.inspect({kind:'slide,layout,textbox,image,shape',maxChars:300000});
await fs.writeFile(path.join(scratch,'template-inspection.ndjson'),inspection.ndjson);
const proto=imported.toProto();
// Verified against cgu-short.pptx hash in manifest. One slide-level adapter per role.
const templates=Object.fromEntries(adapter.layouts.map(x=>[x.kind,x.source_slide]));
const map=spec.slides.map((s,i)=>({id:s.id,kind:s.kind,source_slide:templates[s.kind],layout_key:layouts[s.kind].key,template_sha256:hash}));
proto.slides=spec.slides.map((s,i)=>{
 const p=structuredClone(proto.slides[templates[s.kind]-1]);p.id='cgu_'+i;p.index=i;
 const layout=layouts[s.kind];
 if(layout.keep_shape_ids)p.elements=p.elements.filter(e=>layout.keep_shape_ids.includes(e.id));
 p.elements=p.elements.filter(e=>!layout.remove_shape_ids.includes(e.id));
 return p;
});
const presentation=Presentation.load(proto);
const regular=tokens.fonts.body,semi=tokens.fonts.heading;
const red=tokens.colors.accent,black=tokens.colors.text,gray=tokens.colors.muted,surface=tokens.colors.surface;
const px=pt=>pt*4/3;
function style(pt=tokens.sizes_pt.body,bold=false,color=black,align='left',center=false){return {typeface:bold?semi:regular,fontSize:px(pt),bold:false,color,autoFit:'none',wrap:'square',alignment:align,verticalAlignment:center?'middle':'top',insets:{left:0,right:0,top:0,bottom:0}};}
const measure=createCanvas(1,1).getContext('2d');
function checkFit(text,w,h,pt,bold,name,pad=0){
 // Measure the same mixed weights applied to numeric runs in the final PPTX.
 const measured=value=>value.split(/([+−-]?\d+(?:[ \u00a0\u202f]\d{3})*(?:[.,:/–−-]\d+)*(?:[%‰+])?)/u).reduce((sum,part)=>{
  const numeric=/\d/u.test(part);measure.font=`${numeric?'bold ':''}${px(pt)}px "${numeric?regular:bold?semi:regular}"`;
  return sum+measure.measureText(part).width;
 },0);
 const width=w-pad*2;let lines=0;
 for(const paragraph of text.split('\n')){let line='';for(const word of paragraph.split(/\s+/)){if(measured(word)>width)throw Error(`${name}: word wider than text box`);const next=line?line+' '+word:word;if(line&&measured(next)>width){lines++;line=word;}else line=next;}lines++;}
 if(lines*px(pt)*1.18>h-pad*2+4)throw Error(`${name}: text needs ${Math.ceil(lines*px(pt)*1.18)} px, available ${h-pad*2}; shorten text`);
}
function edit(sl,id,text,pt=24,bold=false,frame=null,color=black,align='left',center=false){const s=sl.shapes.items.find(e=>e.id===id);if(!s)throw Error('Missing template shape '+id);if(frame)s.position=frame;checkFit(text,s.position.width,s.position.height,pt,bold,'slot '+id);s.text=text;s.text.style=style(pt,bold,color,align,center);return s;}
function label(sl,name,text,x,y,w,h,pt=24,bold=false,color=black,align='left',center=false){checkFit(text,w,h,pt,bold,name);const s=sl.shapes.add({name,geometry:'textbox',position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});s.text=text;s.text.style=style(pt,bold,color,align,center);return s;}
function node(sl,id,text,b,accent=false){const [x,y,w,h]=b;checkFit(text,w,h,26,true,id,22);const n=sl.shapes.add({name:'node-'+id,geometry:'roundRect',position:{left:x,top:y,width:w,height:h},fill:accent?red:surface,line:{fill:'none',width:0},borderRadius:24});n.text=text;n.text.style={...style(26,true,accent?tokens.colors.background:black,'center',true),insets:{left:22,right:22,top:18,bottom:18}};return n;}
function link(sl,a,b,from='right',to='left',kind='elbow'){return sl.shapes.connect(a,b,{kind,fromSide:from,toSide:to,line:{fill:red,width:3,style:'solid'},tail:{type:'triangle',width:'med',length:'med'}});}
for(let i=0;i<spec.slides.length;i++){
 const d=spec.slides[i],s=presentation.slides.items[i],slots=layouts[d.kind].slots;
 if(d.kind==='cover'){
  edit(s,slots.title,d.title,tokens.sizes_pt.cover_title,true,{left:170,top:470,width:820,height:220});
  edit(s,slots.subtitle,d.subtitle,24,false,{left:170,top:710,width:820,height:120});
  edit(s,slots.department,'ДИТ Москвы',14,false,null,gray,'center',true);
  edit(s,slots.year,spec.demo?'ДЕМО':String(new Date().getFullYear()),14,false,null,gray,'center',true);
 }else{
  const [left,top,width,height]=tokens.geometry.title_box_px;
  edit(s,slots.title,d.title,tokens.sizes_pt.title,true,{left,top,width,height});
 }
 if(d.kind==='text_blocks'){
  const panel=(name,x,y,w,h,fill=surface)=>s.shapes.add({name,geometry:'roundRect',position:{left:x,top:y,width:w,height:h},fill,line:{fill:'none',width:0},borderRadius:24});
  const content=(j,x,y,w,{number=false,accent=false,metric=false}={})=>{
   const item=d.items[j],ink=accent?tokens.colors.background:black;
   if(number)label(s,'block-number-'+j,String(j+1).padStart(2,'0'),x,y,w,65,36,true,accent?ink:red);
   if(metric)label(s,'block-value-'+j,item.value,x,y,w,80,44,true,red);
   const offset=number?78:metric?86:0;
   label(s,'block-title-'+j,item.title,x,y+offset,w,number?65:80,26,true,ink);
   label(s,'block-body-'+j,item.body,x,y+offset+(number?70:88),w,d.variant==='cards_grid'?105:d.variant==='text_columns'?390:260,22,false,accent?ink:gray);
  };
  if(d.variant==='numbered_columns'){
   d.items.forEach((item,j)=>{const x=100+j*590;
    label(s,'block-number-'+j,String(j+1).padStart(2,'0'),x,340,530,150,90,true,red);
    content(j,x,545,530);
   });
  }else if(d.variant==='cards_grid'){
   d.items.forEach((item,j)=>{const top=j<3,col=top?j:j-3,w=top?553.333:845,x=100+col*(w+30),y=top?300:620;
    panel('block-panel-'+j,x,y,w,290);content(j,x+28,y+22,w-56,{number:true});
   });
  }else if(d.variant==='columns_callout'){
   d.items.forEach((item,j)=>{const x=100+j*583.333;panel('block-panel-'+j,x,300,553.333,440);content(j,x+30,330,493.333,{number:true});});
  }else if(d.variant==='split_panel'){
   panel('block-panel-0',100,300,630,440);content(0,136,342,558);
   panel('block-panel-1',760,300,1060,440,red);content(1,804,342,972,{accent:true});
  }else if(d.variant==='metrics_band'){
   d.items.forEach((item,j)=>{const x=100+(j%2)*875,y=300+Math.floor(j/2)*225;
    panel('block-panel-'+j,x,y,845,200);
    label(s,'block-value-'+j,item.value,x+28,y+20,789,76,44,true,red);
    label(s,'block-title-'+j,item.title,x+28,y+101,789,46,24,true);
    label(s,'block-body-'+j,item.body,x+28,y+153,789,40,18,false,gray);
   });
  }else if(d.variant==='text_columns'){
   d.items.forEach((item,j)=>{const x=100+j*583.333;panel('block-panel-'+j,x,300,553.333,600);content(j,x+30,350,493.333);});
  }
  if(d.callout){
   panel('block-callout-panel',100,785,1720,125,d.variant==='split_panel'?tokens.colors.accent_soft:red);
   label(s,'block-callout',d.callout,136,817,1648,70,26,true,d.variant==='split_panel'?black:tokens.colors.background);
  }
 }else if(d.kind==='kpi_grid'){
  const gap=30,w=(1720-gap*(d.items.length-1))/d.items.length;
  d.items.forEach((item,j)=>{const x=100+j*(w+gap);
   s.shapes.add({name:'metric-background-'+j,geometry:'roundRect',position:{left:x,top:300,width:w,height:580},fill:surface,line:{fill:'none',width:0},borderRadius:24});
   label(s,'metric-value-'+j,item.value,x+28,355,w-56,120,52,true,red);
   label(s,'metric-label-'+j,item.label,x+28,510,w-56,135,24,true);
   label(s,'metric-detail-'+j,item.detail,x+28,690,w-56,155,20,false,gray);
  });
 }else if(d.kind==='comparison'){
  d.columns.forEach((col,j)=>{const x=100+j*890;
   s.shapes.add({name:'comparison-background-'+j,geometry:'roundRect',position:{left:x,top:290,width:830,height:610},fill:surface,line:{fill:'none',width:0},borderRadius:24});
   label(s,'comparison-title-'+j,col.title,x+32,320,766,115,30,true,j===1?red:black);
   col.items.forEach((text,k)=>{label(s,'comparison-item-'+j+'-'+k,text,x+32,465+k*100,766,90,23);});
  });
 }else if(d.kind==='roadmap'){
  const count=d.steps.length,perRow=count<=3?count:3,gap=65,w=(1720-gap*(perRow-1))/perRow,ns=[];
  d.steps.forEach((step,j)=>{const row=Math.floor(j/perRow),column=row===0?j:perRow-1-(j%perRow),x=100+column*(w+gap),y=300+row*340;
   label(s,'roadmap-period-'+j,step.period,x,y,w,50,20,true,red);
   ns.push(node(s,'roadmap-'+j,step.title,[x,y+62,w,105],j===0));
   label(s,'roadmap-body-'+j,step.body,x,y+190,w,105,21);
  });
  for(let j=0;j<count-1;j++){const turn=j===perRow-1;link(s,ns[j],ns[j+1],turn?'right':j<perRow?'right':'left',turn?'right':j<perRow?'left':'right',turn?'elbow':'straight');}
 }else if(d.kind==='cards'){
  slots.cards.forEach(({title:h,body:b,number:n},j)=>{edit(s,h,d.items[j].title,24,true);edit(s,b,d.items[j].body,24);edit(s,n,String(j+1).padStart(2,'0'),14,true,null,tokens.colors.background,'center',true);});
 }else if(d.kind==='kpi'){
  edit(s,slots.label,d.label,24,false,{left:100,top:285,width:790,height:135});
  edit(s,slots.value,d.value,190,true,{left:100,top:550,width:790,height:310},red);
  label(s,'kpi-detail-title',d.detail_title,1020,300,700,90,26,true);
  label(s,'kpi-detail',d.detail,1020,420,700,390,24);
 }else if(d.kind==='text'){
  label(s,'body',d.body,100,290,1630,620,30);
 }else if(d.kind==='process'){
  const n=d.steps.length,gap=90,w=(1720-gap*(n-1))/n,ns=[];
  d.steps.forEach((step,j)=>{const x=100+j*(w+gap);label(s,'step-number-'+j,String(j+1).padStart(2,'0'),x,350,w,90,44,true,red);ns.push(node(s,'step-'+j,step.title,[x,465,w,135],j===0));label(s,'step-body-'+j,step.body,x,645,w,200,22);});
  for(let j=0;j<n-1;j++)link(s,ns[j],ns[j+1],'right','left','straight');
 }else if(d.kind==='diagram'){
  const nodes=Object.fromEntries(d.nodes.map(n=>[n.id,node(s,n.id,n.text,n.box,n.accent)]));
  for(const [j,e] of d.edges.entries()){link(s,nodes[e.from],nodes[e.to],e.from_side??'right',e.to_side??'left');if(e.label){const [x,y,w,h]=e.label_box;label(s,'edge-label-'+j,e.label,x,y,w,h,18,false,gray,'center',true);}}
 }else if(d.kind==='chart'){
  label(s,'chart-unit',d.unit,100,250,1650,65,22,false,gray);
  const fills=[red,tokens.colors.chart_secondary,gray];
  const all=d.series.flatMap(x=>x.values);const min=Math.min(0,...all),max=Math.max(0,...all);
  const ch=s.charts.add(d.chart_type??'bar',{
   position:{left:100,top:340,width:1700,height:575},categories:d.categories,
   series:d.series.map((v,j)=>({name:v.name,values:v.values,fill:fills[j],line:{fill:fills[j],width:3},marker:{symbol:'circle',size:9}})),
   hasLegend:d.series.length>1,legend:{position:'bottom',overlay:false,textStyle:{typeface:regular,fontSize:28}},
   barOptions:{direction:'column',grouping:'clustered',gapWidth:95,overlap:0},lineOptions:{smooth:false},
   xAxis:{tickLabelPosition:'low',textStyle:{typeface:regular,fontSize:26},line:{fill:tokens.colors.axis,width:1},majorGridlines:null},
   yAxis:{min:min<0?min*1.2:0,max:max>0?max*1.2:1,numberFormatCode:'0.##',textStyle:{typeface:regular,fontSize:24},majorGridlines:{fill:tokens.colors.grid,width:1}},
   dataLabels:{showValue:true,position:'outEnd',textStyle:{typeface:regular,fontSize:24}},chartFill:tokens.colors.background,plotAreaFill:tokens.colors.background
  });applyPresentationChartFont(ch,{fontFamily:regular});
 }else if(d.kind==='table'){
  const nr=d.rows.length+1,nc=d.columns.length,h=Math.min(620,nr*100),w=1720;
  const t=s.tables.add({rows:nr,columns:nc,left:100,top:285,width:w,height:h,columnWidths:Array(nc).fill(w/nc),values:[d.columns,...d.rows]});
  t.borders.assign({outside:{fill:tokens.colors.background,width:0},insideHorizontal:{fill:tokens.colors.table_line,width:1},insideVertical:{fill:tokens.colors.background,width:0}});
  for(let r=0;r<nr;r++){t.rows[r].height=h/nr;for(let c=0;c<nc;c++){const value=[d.columns,...d.rows][r][c];checkFit(value,w/nc-40,h/nr-24,24,r===0,'table cell '+r+','+c);const cell=t.getCell(r,c);cell.fill=r===0?surface:tokens.colors.background;cell.text.style={...style(24,r===0),verticalAlignment:'middle',insets:{left:20,right:20,top:12,bottom:12}};}}
 }
 label(s,'footer',spec.demo?'ДЕМОНСТРАЦИОННЫЕ ДАННЫЕ':(d.footer??''),100,994,1600,38,12,false,gray);
 label(s,'page-number',String(i+1),1740,994,80,38,12,false,gray,'right');
 const sources=[...new Set([...(d.source_ids??[]),...Object.values(d.object_sources??{}).flat()])].map(id=>spec.sources.find(x=>x.id===id)?.location).filter(Boolean);
 s.speakerNotes.textFrame.setText([d.notes??'',spec.demo?'Все данные вымышлены. Презентация для тестирования скилла.':'',...sources.map(x=>'Источник: '+x),...Object.entries(d.object_sources??{}).map(([pointer,ids])=>'Данные '+pointer+': '+ids.join(', '))].filter(Boolean).join('\n\n'));
}
const raw=path.join(scratch,'raw.pptx'),candidate=path.join(scratch,'candidate.pptx');
// Explicit cell borders survive PPTX/LibreOffice better than table-level defaults.
const finalProto=presentation.toProto();
const border=(color)=>({widthEmu:9525,fill:{type:1,color:{type:1,value:color},gradientStops:[],pictureEffects:[]},style:0});
for(const slide of finalProto.slides)for(const element of slide.elements){if(element.table)element.table.rows.forEach((row,i,rows)=>row.cells.forEach(cell=>{cell.lines={left:border('FFFFFF'),right:border('FFFFFF'),top:border(i===0?'FFFFFF':'E4E4E4'),bottom:border(i===rows.length-1?'FFFFFF':'E4E4E4')};}));}
await (await PresentationFile.exportPptx(Presentation.load(finalProto))).save(raw);
const normalizedOutput=path.join(scratch,'normalized.pptx');normalize(raw,normalizedOutput);
const numericResult=spawnSync(python,[path.join(skill,'scripts/number_typography.py'),normalizedOutput,candidate],{encoding:'utf8'});
if(numericResult.status!==0)throw Error(numericResult.stderr);
await fs.writeFile(path.join(scratch,'template-map.json'),JSON.stringify(map,null,2));
const tables=spec.slides.flatMap((s,i)=>s.kind==='table'?[i+1]:[]),charts=spec.slides.flatMap((s,i)=>s.kind==='chart'?[i+1]:[]);
const final=path.join(outDir,'output/presentation.pptx');
const result=await finalizePresentation({workspaceDir:outDir,candidatePath:candidate,finalPath:final,
 pythonExecutable:python,integrityValidatorPath:path.join(presentationSkill,'container_tools/inspect_presentation_package_integrity.py'),
 layoutValidatorPath:path.join(presentationSkill,'container_tools/inspect_presentation_layout_geometry.py'),
 layoutArgs:['--expected-slide-size-emu','18288000,10287000','--validate-bullet-geometry','--validate-heading-fit',...tables.flatMap(n=>['--require-native-table-slide',String(n)])],
 explicitTotalSlideCount:spec.slides.length,requiredNativeTableOwnerSlides:tables,requiredNativeChartOwnerSlides:charts,
 materializeLiteralChartWorkbooks:charts.length>0,fontPolicy:{basis:'user_request',families:[regular,semi]},verifyArtifactToolImport:true,
 receiptPath:path.join(outDir,'qa/validation.json')});
await fs.writeFile(path.join(outDir,'qa/finalizer-result.json'),JSON.stringify(result,null,2));
console.log(JSON.stringify({pptx:final,slides:spec.slides.length}));
