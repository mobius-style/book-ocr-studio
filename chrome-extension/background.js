importScripts('config.js');
const endpoint='http://127.0.0.1:8508';
let target=null,polling=false;
async function post(path,data){const r=await fetch(endpoint+path,{method:'POST',headers:{'Content-Type':'application/json','X-Book-OCR-Key':BOOK_OCR_KEY},body:JSON.stringify(data)});if(!r.ok)throw Error('Local bridge HTTP '+r.status);return r.json()}
const allowed=url=>{try{let u=new URL(url);return u.protocol==='https:'&&['read.amazon.co.jp','read.amazon.com'].includes(u.hostname)&&!!u.searchParams.get('asin')}catch{return false}};
async function cdp(method,params={}){if(!target)throw Error('Not connected to Kindle');let tab=await chrome.tabs.get(target.tabId);if(!allowed(tab.url))throw Error('Only Kindle tabs can be controlled');return chrome.debugger.sendCommand(target,method,params)}
async function execute(req){
 if(req.action==='connect'){
  if(target){try{await chrome.debugger.detach(target)}catch{}target=null}
  const tabs=(await chrome.tabs.query({})).filter(t=>allowed(t.url));
  const active=tabs.filter(t=>t.active);const selected=active.length===1?active[0]:tabs.length===1?tabs[0]:null;
  if(!selected)throw Error('Open and select one Kindle book. Multiple candidate tabs will not be selected automatically.');
  const next={tabId:selected.id};await chrome.debugger.attach(next,'1.3');target=next;
  return execute({action:'evaluate',script:'() => ({width:innerWidth,height:innerHeight,url:location.href,title:document.title})'});
 }
 if(req.action==='disconnect'){if(target)await chrome.debugger.detach(target);target=null;return true}
 if(req.action==='evaluate'){
  const r=await cdp('Runtime.evaluate',{expression:'('+req.script+')('+JSON.stringify(req.arg??null)+')',returnByValue:true,awaitPromise:true});
  if(r.exceptionDetails)throw Error('Page inspection failed');return r.result.value;
 }
 if(req.action==='screenshot'){const params={format:'png',captureBeyondViewport:false};if(req.clip)params.clip={...req.clip,scale:1};return (await cdp('Page.captureScreenshot',params)).data}
 if(req.action==='move')return cdp('Input.dispatchMouseEvent',{type:'mouseMoved',x:req.x,y:req.y});
 if(req.action==='click'){await cdp('Input.dispatchMouseEvent',{type:'mousePressed',x:req.x,y:req.y,button:'left',clickCount:1});return cdp('Input.dispatchMouseEvent',{type:'mouseReleased',x:req.x,y:req.y,button:'left',clickCount:1})}
 throw Error('Unknown action');
}
async function poll(){if(polling)return;polling=true;try{const req=await post('/poll',{});if(req&&req.deadline>Date.now()/1000){let reply={id:req.id};try{reply.result=await execute(req)}catch(e){reply.error=e.message}await post('/reply',reply)}}catch{}finally{polling=false}}
chrome.debugger.onDetach.addListener(source=>{if(target?.tabId===source.tabId)target=null});
chrome.action.onClicked.addListener(()=>chrome.tabs.create({url:'http://127.0.0.1:8507/'}));
chrome.alarms.create('bridge',{periodInMinutes:.5});chrome.alarms.onAlarm.addListener(poll);setInterval(poll,1000);poll();
