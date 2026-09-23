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
const adapter=JSON.parse(await fs.readFile(path.join(skill,'references/template-adapter.json'),'utf8'));
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
const templates=adapter.roles;
const map=spec.slides.map((s,i)=>({id:s.id,kind:s.kind,source_slide:templates[s.kind],template_sha256:hash}));
proto.slides=spec.slides.map((s,i)=>{
 const p=structuredClone(proto.slides[templates[s.kind]-1]);p.id='cgu_'+i;p.index=i;
 if(s.kind==='kpi')p.elements=p.elements.filter(e=>['33','48','49','2','3','4'].includes(e.id));
 else if(!['cover','cards'].includes(s.kind))p.elements=p.elements.filter(e=>['33','48','49'].includes(e.id));
 if(s.kind==='cover')p.elements=p.elements.filter(e=>e.id!=='42');
 return p;
});
const presentation=Presentation.load(proto);
const regular='Golos Text',semi='Golos Text SemiBold';
const red='#FF254A',black='#000000',gray='#5B5B5B',surface='#F3F2F2';
const px=pt=>pt*4/3;
function style(pt=24,bold=false,color=black,align='left',center=false){return {typeface:bold?semi:regular,fontSize:px(pt),bold:false,color,autoFit:'none',wrap:'square',alignment:align,verticalAlignment:center?'middle':'top',insets:{left:0,right:0,top:0,bottom:0}};}
const measure=createCanvas(1,1).getContext('2d');
function checkFit(text,w,h,pt,bold,name,pad=0){
 measure.font=`${px(pt)}px "${bold?semi:regular}"`;
 const width=w-pad*2;let lines=0;
 for(const paragraph of text.split('\n')){let line='';for(const word of paragraph.split(/\s+/)){if(measure.measureText(word).width>width)throw Error(`${name}: word wider than text box`);const next=line?line+' '+word:word;if(line&&measure.measureText(next).width>width){lines++;line=word;}else line=next;}lines++;}
 if(lines*px(pt)*1.18>h-pad*2+4)throw Error(`${name}: text needs ${Math.ceil(lines*px(pt)*1.18)} px, available ${h-pad*2}; shorten text`);
}
function edit(sl,id,text,pt=24,bold=false,frame=null,color=black,align='left',center=false){const s=sl.shapes.items.find(e=>e.id===id);if(!s)throw Error('Missing template shape '+id);if(frame)s.position=frame;checkFit(text,s.position.width,s.position.height,pt,bold,'slot '+id);s.text=text;s.text.style=style(pt,bold,color,align,center);return s;}
function label(sl,name,text,x,y,w,h,pt=24,bold=false,color=black,align='left',center=false){checkFit(text,w,h,pt,bold,name);const s=sl.shapes.add({name,geometry:'textbox',position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});s.text=text;s.text.style=style(pt,bold,color,align,center);return s;}
function node(sl,id,text,b,accent=false){const [x,y,w,h]=b;checkFit(text,w,h,26,true,id,22);const n=sl.shapes.add({name:'node-'+id,geometry:'roundRect',position:{left:x,top:y,width:w,height:h},fill:accent?red:surface,line:{fill:'none',width:0},borderRadius:24});n.text=text;n.text.style={...style(26,true,accent?'#FFFFFF':black,'center',true),insets:{left:22,right:22,top:18,bottom:18}};return n;}
function link(sl,a,b,from='right',to='left',kind='elbow'){return sl.shapes.connect(a,b,{kind,fromSide:from,toSide:to,line:{fill:red,width:3,style:'solid'},tail:{type:'triangle',width:'med',length:'med'}});}
for(let i=0;i<spec.slides.length;i++){
 const d=spec.slides[i],s=presentation.slides.items[i];
 if(d.kind==='cover'){
  edit(s,'40',d.title,60,true,{left:170,top:470,width:820,height:220});
  edit(s,'41',d.subtitle,24,false,{left:170,top:710,width:820,height:120});
  edit(s,'38','ДИТ Москвы',14,false,null,gray,'center',true);
  edit(s,'39',spec.demo?'ДЕМО':String(new Date().getFullYear()),14,false,null,gray,'center',true);
 }else{
  edit(s,d.kind==='cards'?'6':'33',d.title,44,true,{left:100,top:80,width:1260,height:145});
 }
 if(d.kind==='cards'){
  [['8','10','9'],['12','14','13'],['16','18','17'],['20','22','21']].forEach(([h,b,n],j)=>{edit(s,h,d.items[j].title,24,true);edit(s,b,d.items[j].body,24);edit(s,n,String(j+1).padStart(2,'0'),14,true,null,'#FFFFFF','center',true);});
 }else if(d.kind==='kpi'){
  edit(s,'3',d.label,24,false,{left:100,top:285,width:790,height:135});
  edit(s,'4',d.value,190,true,{left:100,top:550,width:790,height:310},red);
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
  for(const e of d.edges)link(s,nodes[e.from],nodes[e.to],e.from_side??'right',e.to_side??'left');
 }else if(d.kind==='chart'){
  label(s,'chart-unit',d.unit,100,250,1650,65,22,false,gray);
  const fills=[red,'#F7849B','#5B5B5B'];
  const all=d.series.flatMap(x=>x.values);const min=Math.min(0,...all),max=Math.max(0,...all);
  const ch=s.charts.add(d.chart_type??'bar',{
   position:{left:100,top:340,width:1700,height:575},categories:d.categories,
   series:d.series.map((v,j)=>({name:v.name,values:v.values,fill:fills[j],line:{fill:fills[j],width:3},marker:{symbol:'circle',size:9}})),
   hasLegend:d.series.length>1,legend:{position:'bottom',overlay:false,textStyle:{typeface:regular,fontSize:28}},
   barOptions:{direction:'column',grouping:'clustered',gapWidth:95,overlap:0},lineOptions:{smooth:false},
   xAxis:{tickLabelPosition:'low',textStyle:{typeface:regular,fontSize:26},line:{fill:'#D0D0D0',width:1},majorGridlines:null},
   yAxis:{min:min<0?min*1.2:0,max:max>0?max*1.2:1,numberFormatCode:'0.##',textStyle:{typeface:regular,fontSize:24},majorGridlines:{fill:'#E4E4E4',width:1}},
   dataLabels:{showValue:true,position:'outEnd',textStyle:{typeface:regular,fontSize:24}},chartFill:'#FFFFFF',plotAreaFill:'#FFFFFF'
  });applyPresentationChartFont(ch,{fontFamily:regular});
 }else if(d.kind==='table'){
  const nr=d.rows.length+1,nc=d.columns.length,h=Math.min(620,nr*100),w=1720;
  const t=s.tables.add({rows:nr,columns:nc,left:100,top:285,width:w,height:h,columnWidths:Array(nc).fill(w/nc),values:[d.columns,...d.rows]});
  t.borders.assign({outside:{fill:'#FFFFFF',width:0},insideHorizontal:{fill:'#DDDDDD',width:1},insideVertical:{fill:'#FFFFFF',width:0}});
  for(let r=0;r<nr;r++){t.rows[r].height=h/nr;for(let c=0;c<nc;c++){const value=[d.columns,...d.rows][r][c];checkFit(value,w/nc-40,h/nr-24,24,r===0,'table cell '+r+','+c);const cell=t.getCell(r,c);cell.fill=r===0?surface:'#FFFFFF';cell.text.style={...style(24,r===0),verticalAlignment:'middle',insets:{left:20,right:20,top:12,bottom:12}};}}
 }
 label(s,'footer',spec.demo?'ДЕМОНСТРАЦИОННЫЕ ДАННЫЕ':(d.footer??''),100,994,1600,38,12,false,gray);
 label(s,'page-number',String(i+1),1740,994,80,38,12,false,gray,'right');
 const sources=(d.source_ids??[]).map(id=>spec.sources.find(x=>x.id===id)?.location).filter(Boolean);
 s.speakerNotes.textFrame.setText([d.notes??'',spec.demo?'Все данные вымышлены. Презентация для тестирования скилла.':'',...sources.map(x=>'Источник: '+x)].filter(Boolean).join('\n\n'));
}
const raw=path.join(scratch,'raw.pptx'),candidate=path.join(scratch,'candidate.pptx');
// Explicit cell borders survive PPTX/LibreOffice better than table-level defaults.
const finalProto=presentation.toProto();
const border=(color)=>({widthEmu:9525,fill:{type:1,color:{type:1,value:color},gradientStops:[],pictureEffects:[]},style:0});
for(const slide of finalProto.slides)for(const element of slide.elements){if(element.table)element.table.rows.forEach((row,i,rows)=>row.cells.forEach(cell=>{cell.lines={left:border('FFFFFF'),right:border('FFFFFF'),top:border(i===0?'FFFFFF':'E4E4E4'),bottom:border(i===rows.length-1?'FFFFFF':'E4E4E4')};}));}
await (await PresentationFile.exportPptx(Presentation.load(finalProto))).save(raw);normalize(raw,candidate);
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
