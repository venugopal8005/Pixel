import fs from 'node:fs/promises';
import path from 'node:path';
import {Workbook,SpreadsheetFile} from '@oai/artifact-tool';
try{
const input=path.resolve(process.argv[2]);const data=JSON.parse(await fs.readFile(input,'utf8'));const wb=Workbook.create();
const tables=[['Converted records',data.headers||['ID',...Array.from({length:36},(_,i)=>String(i+1))],data.rows],['Text regions',['Record key','Source image','Region','Transcription with markers'],data.lines],['Review status',['Record key','Field or review ID','Category','Original reading or issue','Confirmed text / explanation','Status'],data.review]];
if(data.fragments)tables.push(['Source fragments',['Record key','Source image','Fragment','Assignment','Source coordinates','Layout notes'],data.fragments]);
for(const [name,headers,rows] of tables){const sheet=wb.worksheets.add(name);const safe=value=>typeof value==='string'&&value.startsWith('=')?"'"+value:value;const matrix=[headers,...rows].map(r=>r.map(safe));const range=sheet.getRangeByIndexes(0,0,matrix.length,headers.length);range.setNumberFormat('@');range.values=matrix;range.format.font={name:'Arial',size:11};range.format.columnWidth=25;range.format.rowHeight=60;range.format.wrapText=true;sheet.showGridLines=false;sheet.freezePanes.freezeRows(1);sheet.freezePanes.freezeColumns(1);const header=sheet.getRangeByIndexes(0,0,1,headers.length);header.format.fill='#243B53';header.format.font={name:'Arial',size:11,bold:true,color:'#ffffff'};header.format.rowHeight=28;}
if(data.schema_version===2){
  const sheet=wb.worksheets.getItem('Converted records');
  const colors={uncertain:'#FFF0CC',unmapped:'#FDE2DE',confirmed:'#E2F2E8',generated:'#EDF2F8'};
  const currency=new Set([18,21,23,24]);
  sheet.freezePanes.freezeColumns(2);
  sheet.getRangeByIndexes(0,0,data.rows.length+1,37).format.verticalAlignment='top';
  sheet.getRangeByIndexes(0,0,data.rows.length+1,37).format.borders={insideVertical:{style:'thin',color:'#DFE5EB'}};
  sheet.getRangeByIndexes(0,0,1,37).format.rowHeight=42;
  sheet.getRangeByIndexes(0,0,data.rows.length+1,1).format.columnWidth=42;
  for(const column of [13,25,36])sheet.getRangeByIndexes(0,column,data.rows.length+1,1).format.columnWidth=55;
  for(let r=0;r<data.rows.length;r++)for(let c=0;c<37;c++){
    const cell=sheet.getRangeByIndexes(r+1,c,1,1),value=data.rows[r][c],status=data.statuses?.[r]?.[c];
    if(colors[status])cell.format.fill=colors[status];
    if(typeof value!=='string'||value.includes('['))continue;
    let numeric=null,format=null;
    if(currency.has(c)&&/^\$\d[\d,]*\.\d{2}$/.test(value)){numeric=Number(value.replace(/[$,]/g,''));format='"$"#,##0.00';}
    if(c===19&&/^\d+ Months$/.test(value)){numeric=Number(value.slice(0,-7));format='0" Months"';}
    if(c===20&&/^\d+(\.\d+)?%$/.test(value)){numeric=Number(value.slice(0,-1))/100;format='0.########%';}
    if((c===2||c===9)&&/^\d{2}\/\d{2}\/\d{4}$/.test(value)){
      const [m,d,y]=value.split('/').map(Number),date=new Date(Date.UTC(y,m-1,d));
      if(date.getUTCMonth()===m-1&&date.getUTCDate()===d){cell.values=[[date]];cell.setNumberFormat('mm/dd/yyyy');}
    }
    if(numeric!==null&&Number.isFinite(numeric)&&Math.abs(numeric)<1e14){cell.values=[[numeric]];cell.setNumberFormat(format);}
  }
  const review=wb.worksheets.getItem('Review status'),row=data.review.length+3;
  const legend=[['Legend','Amber: character ambiguity or field rule needs review.'],['Legend','Red: field not located. Green: user-confirmed field; retained rule warnings appear in Review status.'],['Legend','Blue-grey: generated metadata or remarks. White: unreviewed OCR.'],['Markers','[i/l] = alternatives; [?] = unreadable or unlocated text.'],['Source','Text regions preserve marked OCR. Source fragments retain detected blocks and their pages.'],['Rules','Formatting does not verify recognition. Full property identifiers are retained when the manual example conflicts.']];
  review.getRangeByIndexes(row,0,legend.length,2).values=legend;
  review.getRangeByIndexes(row,1,legend.length,1).format.columnWidth=70;
  review.getRangeByIndexes(row,0,legend.length,2).format.wrapText=true;
  review.getRangeByIndexes(row,0,legend.length,2).format.rowHeight=36;
}
wb.recalculate();
const inspected=await wb.inspect({kind:'table',range:'Converted records!A1:F3',include:'values,formulas',tableMaxRows:3,tableMaxCols:6});
await fs.writeFile(path.join(path.dirname(input),'export-inspection.jsonl'),inspected.ndjson);
await(await SpreadsheetFile.exportXlsx(wb)).save(path.join(path.dirname(input),'converted.xlsx'));console.log('Exported');
}catch(error){console.error(String(error));process.exitCode=1}
