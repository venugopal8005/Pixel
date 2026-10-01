import fs from 'node:fs/promises';
import {Workbook,SpreadsheetFile,FileBlob} from '@oai/artifact-tool';
if(process.argv.includes('--help-render')){
 console.log(Workbook.create().help('workbook.render',{include:'index,examples,notes',maxChars:3500}).ndjson);
}else{
 const wb=await SpreadsheetFile.importXlsx(await FileBlob.load(process.argv[2]));
 console.log((await wb.inspect({kind:'table',range:'Converted records!R1:Y4',include:'values,formulas',tableMaxRows:4,tableMaxCols:8})).ndjson);
 const preview=await wb.render({sheetName:'Converted records',range:'R1:Y4',format:'png',scale:1.4});
 await fs.writeFile('outputs/pilot-testing/export-preview.png',new Uint8Array(await preview.arrayBuffer()));
}
