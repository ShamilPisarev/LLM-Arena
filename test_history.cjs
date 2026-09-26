const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const {randomUUID} = require('node:crypto');
const source = fs.readFileSync('index.html','utf8').match(/<script>([\s\S]*?)<\/script>/)[1].replace(/init\(\);\s*$/, '');
function environment(storage = new Map()) {
  const elements = new Map();
  function element() { return {value:'',textContent:'',innerHTML:'',style:{},children:[],classList:{add(){},remove(){}},append(...items){this.children.push(...items)},replaceChildren(...items){this.children=items},setAttribute(){},addEventListener(){}}; }
  const context = vm.createContext({console,crypto:{randomUUID},setTimeout,clearTimeout,confirm:()=>true,navigator:{clipboard:{writeText(){}}},window:{addEventListener(){}},document:{getElementById(id){if(!elements.has(id))elements.set(id,element());return elements.get(id)},createElement:element,addEventListener(){}},localStorage:{get length(){return storage.size},key(i){return [...storage.keys()][i]},getItem(k){return storage.get(k)??null},setItem(k,v){storage.set(k,v)},removeItem(k){storage.delete(k)}}});
  vm.runInContext(source,context);
  return {run:s=>vm.runInContext(s,context),storage,elements,context};
}
test('save/reload retains responses, system prompt, draft, model selection and settings',()=>{
 const e=environment();
 e.run(`historyReady=true; selected=new Set(['m']); generationSettings={m:{temperature:0}}; turns=[{id:1,userMessage:'Hello',models:[{id:'m',name:'Model'}],responses:{m:{text:'Saved answer',status:'done'}}}]; document.getElementById('sys-prompt').value='Be brief';document.getElementById('prompt').value='Follow up';saveChat();`);
 const restored=environment(e.storage);restored.run('restoreChats()');
 assert.equal(restored.run('turns[0].responses.m.text'),'Saved answer');
 assert.equal(restored.run("document.getElementById('sys-prompt').value"),'Be brief');
 assert.equal(restored.run("document.getElementById('prompt').value"),'Follow up');
 assert.equal(restored.run('generationSettings.m.temperature'),0);
 assert.equal(restored.run("selected.has('m')"),true);
});
test('new chat preserves old chat; deleting one chat preserves another and API key',()=>{
 const e=environment();e.run("historyReady=true;localStorage.setItem('or_key','test-key');document.getElementById('prompt').value='First';saveChat();newConversation();document.getElementById('prompt').value='Second';saveChat();");
 assert.equal(e.run('savedChats().length'),2);
 e.run('deleteConversation()');assert.equal(e.run('savedChats().length'),1);
 assert.equal(e.run('savedChats()[0].title'),'First');assert.equal(e.storage.get('or_key'),'test-key');
 const restored=environment(e.storage);restored.run('restoreChats()');assert.equal(restored.run('savedChats().length'),1);
});
test('partial streams survive reload and chat changes are locked during streaming',()=>{
 const e=environment();e.run("historyReady=true; turns=[{id:1,userMessage:'Hello',models:[{id:'m',name:'Model'}],responses:{m:{text:'Partial',status:'streaming'}}}];saveChat();running=true;newConversation();deleteConversation();");
 assert.equal(e.run('turns.length'),1);
 const restored=environment(e.storage);restored.run('restoreChats()');
 assert.equal(restored.run('turns[0].responses.m.status'),'interrupted');
 assert.equal(restored.run('turns[0].responses.m.text'),'Partial');
});
test('storage failure preserves current conversation and reports it',()=>{
 const e=environment();e.run("historyReady=true;document.getElementById('prompt').value='Keep me';localStorage.setItem=()=>{throw new Error('Quota')};newConversation();");
 assert.equal(e.run("document.getElementById('prompt').value"),'Keep me');
 assert.match(e.run("document.getElementById('chat-status').textContent"),/not saved/);
});
