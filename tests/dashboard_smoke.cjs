const fs=require('fs'),vm=require('vm');
const html=fs.readFileSync(process.argv[2],'utf8');
const json=html.match(/<script id="simulation" type="application\/json">([\s\S]*?)<\/script>/)[1];
const code=html.match(/<\/script><script>([\s\S]*?)<\/script>/)[1];
const elements={};
function element(id=''){
 const handlers={};
 return {id,style:{},children:[],value:({metric:'portfolio',units:'real',mode:'bands',scenario:'0',histStrategy:'0',age:'0'})[id]||'',
 textContent:id==='simulation'?json:'',selectedOptions:[{textContent:'Test measure'}],
 append(...items){this.children.push(...items)},replaceChildren(...items){this.children=items},
 addEventListener(name,fn){handlers[name]=fn},handlers,
 getBoundingClientRect(){return {width:800,height:360}},
 getContext(){return new Proxy({measureText(t){return {width:t.length*5}}},{get(obj,key){return key in obj?obj[key]:()=>{}}})},
 toDataURL(){return 'data:image/png;base64,'},click(){}};
}
const document={getElementById(id){return elements[id]??=(element(id))},createElement(){return element()},createTextNode(text){return text}};
const context={document,window:{devicePixelRatio:1,addEventListener(){}},console,Intl,setInterval(){return 1},clearInterval(){}};
vm.createContext(context);vm.runInContext(code,context);
for(const metric of ['portfolio','taxes','shortfall','roth_share'])for(const units of ['real','nominal'])for(const mode of ['bands','sample']){
 elements.metric.value=metric;elements.units.value=units;elements.mode.value=mode;
 elements.age.value=Math.min(10,JSON.parse(json).ages.length-1);vm.runInContext('draw();histogram()',context);
}
elements.export.onclick();elements.play.onclick();elements.play.onclick();
console.log('Dashboard initialization, all display modes, PNG export and play controls passed.');
