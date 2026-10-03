/* Exercise the actual editor functions with field-local backend evidence. */
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('review_sheet.js','utf8');
const elements={charEditor:{classList:{toggle(){}}},options:{children:[],replaceChildren(){this.children=[];},append(v){this.children.push(v);}},charInput:{},charReason:{},onlyUnsure:{checked:true}};
const sourceSegment={id:'s',text:'O',options:['O','0'],category:'ambiguous',reason:'Readings disagree'};
const cell={manual:false,candidate:false,segments:[{id:'s',line:'l',editable:true}],rule_segments:{s:{text:'0',options:['0'],category:'single',resolved:true,original_options:['O','0'],reason:'Numeric field rule'}}};
const state={decisions:{}};
const sandbox={state,active:{row:0,field:0},chosen:'s',rows:[{cells:Array.from({length:37},()=>({manual:false,status:'read'}))}],
  record:()=>({lines:[{id:'l',segments:[sourceSegment]}]}),current:()=>cell,has:(o,k)=>Object.hasOwn(o,k),
  $:id=>elements[id],document:{createElement:()=>({})},saveCharacter(){}};
vm.createContext(sandbox);
for(const name of ['entry','entries','pendingEntry','renderCharacter','candidate']){
 const line=source.split('\n').find(l=>l.startsWith('function '+name+'('));
 assert(line,'Missing editor function '+name);vm.runInContext(line,sandbox);
}
vm.runInContext(source.split('\n').find(l=>l.startsWith('const unsure=')),sandbox);
vm.runInContext('renderCharacter()',sandbox);
assert.equal(elements.charInput.value,'0');assert.deepEqual(elements.options.children.map(b=>b.textContent),['0']);
assert(elements.charReason.textContent.includes('Original OCR alternatives: O / 0'));
assert.equal(vm.runInContext('entries().some(pendingEntry)',sandbox),false);
assert.equal(sourceSegment.text,'O','Rule projection must not modify raw OCR');
cell.rule_segments.s={text:'1',options:['1','7'],category:'ambiguous',resolved:false,original_options:['1','7','I'],reason:'Numeric field rule'};
vm.runInContext('renderCharacter()',sandbox);
assert.deepEqual(elements.options.children.map(b=>b.textContent),['1','7']);
assert.equal(vm.runInContext('entries().some(pendingEntry)',sandbox),true);
cell.candidate=true;
assert.equal(vm.runInContext('entry(current().segments[0]).seg.text',sandbox),'O','Proposed crops cannot inherit filters');
cell.candidate=false;cell.manual=true;
vm.runInContext('renderCharacter()',sandbox);assert(elements.options.children.every(b=>b.disabled));
sandbox.rows[0].cells[1]={manual:true,status:'uncertain'};
sandbox.rows[0].cells[2]={manual:false,status:'uncertain'};
assert.equal(vm.runInContext('candidate(1).field',sandbox),2);
console.log('Field-rule editor checks passed: filtered options, original evidence, pending navigation, proposed crop isolation, manual override.');
