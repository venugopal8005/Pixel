import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { Workbook, SpreadsheetFile } from '@oai/artifact-tool';

try {
const root=path.dirname(fileURLToPath(import.meta.url));
const out=path.join(root,'outputs','01a0a689-ede0-7c41-b1be-363ef5cee270');
await fs.mkdir(out,{recursive:true});
const coverage=JSON.parse(await fs.readFile(path.join(root,'outputs/automatic-report/coverage.json'),'utf8'));
const reference=JSON.parse(await fs.readFile(path.join(root,'outputs/ocr-reference/reference.json'),'utf8'));
const wb=Workbook.create();
console.log('Created workbook');
const review=wb.worksheets.add('OCR comparison');
const accepted=wb.worksheets.add('Accepted Excel values');
const independent=wb.worksheets.add('Independent OCR');
const labels={agrees:'Numeric/literal agreement',exact_agreement:'Exact agreement',different:'Different',disagrees:'Different',needs_review:'Format or reading issue',unresolved:'Unresolved'};
const detail=coverage.results.map(r=>[r.record_id,r.field,r.prediction?.raw_ocr??null,r.excel_target,
    r.prediction?labels[r.prediction.comparison_status]??r.prediction.comparison_status:'Not implemented',
    r.coverage==='candidate_extracted'?'Candidate':r.coverage==='unresolved'?'Unresolved':'Not implemented']);
const last=detail.length+10;
review.getRange(`A1:F${last}`).format.font={name:'Arial',size:11,color:'#233345'};
review.getRange(`A1:F${last}`).format.verticalAlignment='center';
review.getRange('A2').values=[['OCR comparison']];
review.getRange('A2').format.font={size:16,bold:true};
review.getRange('A3').values=[['Excel values are authoritative. OCR candidates remain independent and may be wrong.']];
review.getRange('A4').values=[['Sources: manual.xlsx (Sheet1) and supplied image pages 159–160.']];
review.getRange('A5').values=[['Names use provisional splits. Text candidates collapse whitespace without correcting spelling.']];
review.getRange('A6').values=[['Amounts may agree numerically despite display differences. This is a saved development run.']];
review.getRange('A8:F8').values=[['Candidates',null,'Unresolved',null,'Not implemented',null]];
review.getRange('B8').formulas=[[`=COUNTIFS(F11:F${last},"Candidate")`]];
review.getRange('D8').formulas=[[`=COUNTIFS(F11:F${last},"Unresolved")`]];
review.getRange('F8').formulas=[[`=COUNTIFS(F11:F${last},"Not implemented")`]];
review.getRange('A10:F10').values=[['Record ID','Field','Independent OCR','Excel target','Comparison result','Extraction coverage']];
review.getRange(`A11:F${last}`).values=detail;
console.log('Wrote comparison');
review.getRange(`A11:A${last}`).setNumberFormat('@');
console.log('ID format');
review.getRange(`C11:D${last}`).setNumberFormat('@');
review.getRange(`A11:F${last}`).format.rowHeight=44;
review.getRange(`C11:F${last}`).format.wrapText=true;
console.log('Wrapped cells');
review.getRange('A:A').format.columnWidth=19;
review.getRange('B:B').format.columnWidth=9;
review.getRange('C:D').format.columnWidth=49;
review.getRange('E:E').format.columnWidth=30;
review.getRange('F:F').format.columnWidth=23;
console.log('Column widths');
review.getRange(`A11:F${last}`).format.rowHeight=54;
review.tables.add(`A10:F${last}`,true,'OcrComparison');
review.getRange(`E11:E${last}`).conditionalFormats.add('containsText',{text:'Different',format:{fill:'#FFF0D4'}});
review.getRange(`E11:F${last}`).conditionalFormats.add('containsText',{text:'Unresolved',format:{fill:'#FBE3E3'}});
review.freezePanes.freezeRows(10);review.freezePanes.freezeColumns(2);
console.log('Formatted comparison');

const headers=['ID',...Array.from({length:36},(_,i)=>String(i+1))];
const matrix=reference.records.map(r=>[r.record_id,...r.fields.map(f=>f.accepted_output)]);
accepted.getRange('A1:AK12').setNumberFormat('@');
accepted.getRange('A1:AK12').values=[headers,...matrix];
console.log('Wrote accepted values');
accepted.getRange('A1:AK12').format.font={name:'Arial',size:11,color:'#233345'};
accepted.getRange('A1:AK12').format.verticalAlignment='center';
accepted.getRange('A1:AK12').format.columnWidth=25;
accepted.getRange('D1:D12').format.columnWidth=40;
accepted.getRange('A2:AK12').format.wrapText=true;
accepted.getRange('A2:AK12').format.rowHeight=90;
accepted.freezePanes.freezeRows(1);accepted.freezePanes.freezeColumns(1);
accepted.getRange('A15').values=[['Source: manual.xlsx, Sheet1. These are accepted Excel values, not OCR predictions.']];
const predictionMap=new Map(coverage.results.map(r=>[`${r.record_id}:${r.field}`,r.prediction?.raw_ocr??null]));
const independentMatrix=reference.records.map(r=>[r.record_id,...Array.from({length:36},(_,i)=>predictionMap.get(`${r.record_id}:${i+1}`)??null)]);
independent.getRange('A1:AK12').setNumberFormat('@');
independent.getRange('A1:AK12').values=[headers,...independentMatrix];
independent.getRange('A1:AK12').format.font={name:'Arial',size:11,color:'#233345'};
independent.getRange('A1:AK12').format.columnWidth=25;
independent.getRange('D1:D12').format.columnWidth=40;
independent.getRange('A2:AK12').format.wrapText=true;
independent.getRange('A2:AK12').format.rowHeight=90;
independent.freezePanes.freezeRows(1);independent.freezePanes.freezeColumns(1);
independent.getRange('A15').values=[['Independent OCR candidates. Blank fields are unresolved or lack a source mapping. See OCR comparison.']];
independent.getRange('A16').values=[['Original column order. OCR strings preserved without inferred currency, date or spelling corrections.']];
for (const [sheet,header] of [[review,'A10:F10'],[accepted,'A1:AK1'],[independent,'A1:AK1']]) {
    sheet.showGridLines=false;
    sheet.getRange(header).format.fill='#243B53';
    sheet.getRange(header).format.font={name:'Arial',size:11,bold:true,color:'#FFFFFF'};
    sheet.getRange(header).format.horizontalAlignment='center';
    sheet.getRange(header).format.rowHeight=26;
}
wb.recalculate();
console.log('Recalculated workbook');
const checks=await wb.inspect({kind:'table',range:"'OCR comparison'!A8:F12",include:'values,formulas',tableMaxRows:5,tableMaxCols:6,maxChars:1600});
console.log(checks.ndjson);
const counts=review.getRange('A8:F8').values[0];
if(counts[1]!==coverage.counts.candidate_extracted||counts[3]!==coverage.counts.unresolved||counts[5]!==coverage.counts.not_implemented)throw Error('Summary mismatch');
if(JSON.stringify(accepted.getRange('A2:AK12').values)!==JSON.stringify(matrix))throw Error('Accepted values changed');
if(JSON.stringify(independent.getRange('A2:AK12').values)!==JSON.stringify(independentMatrix))throw Error('OCR export changed');
const errors=await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#NUM!|#SPILL!|#CALC!',options:{useRegex:true,maxResults:20},maxChars:1000});
console.log(errors.ndjson);
await (await SpreadsheetFile.exportXlsx(wb)).save(path.join(out,'OCR-comparison.xlsx'));
console.log('Exported OCR-comparison.xlsx');
if(process.argv.includes('--render')) {
for (const [sheet,range,name] of [[review,'A1:F15','comparison-preview'],[accepted,'A1:F6','accepted-preview'],[independent,'A1:F6','independent-preview']]) {
    const preview=await wb.render({sheetName:sheet.name,range,scale:1,format:'png'});
    await fs.writeFile(path.join(out,name+'.png'),new Uint8Array(await preview.arrayBuffer()));
}
}
} catch(error) { console.error(error.stack??String(error)); process.exitCode=1; }
