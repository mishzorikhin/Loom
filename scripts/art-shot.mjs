// Снимок страницы headless-хромом для проверки графики (docs/graphics.md).
// Запуск: node scripts/art-shot.mjs out.png W H "js перед снимком" [url]; браузер — CHROME_BIN или puppeteer chrome-headless-shell.
// Печатает ошибки консоли страницы.
import { spawn } from 'node:child_process';
import fs from 'node:fs';
const [out, W='1600', H='900', js='', url='http://localhost:8431'] = process.argv.slice(2);
const C = process.env.CHROME_BIN || process.env.HOME + '/.cache/puppeteer/chrome-headless-shell/linux-153.0.8010.36/chrome-headless-shell-linux64/chrome-headless-shell';
const port = 9300 + Math.floor(Math.random()*500);
const p = spawn(C, ['--no-sandbox','--disable-gpu','--enable-unsafe-swiftshader',`--remote-debugging-port=${port}`,`--window-size=${W},${H}`,'about:blank'],{stdio:'ignore'});
const sleep = ms => new Promise(r=>setTimeout(r,ms));
let targets;
for (let i=0;i<50;i++){ try{ targets = await (await fetch(`http://127.0.0.1:${port}/json`)).json(); if(targets.length) break;}catch{} await sleep(200); }
const ws = new WebSocket(targets.find(t=>t.type==='page').webSocketDebuggerUrl);
await new Promise(r=>ws.onopen=r);
let id=0; const pend=new Map(); const logs=[];
ws.onmessage = m => { const d=JSON.parse(m.data); if(d.id&&pend.has(d.id)){pend.get(d.id)(d.result);pend.delete(d.id);} else if(d.method==='Runtime.exceptionThrown') logs.push('EXC '+JSON.stringify(d.params.exceptionDetails.exception?.description||d.params.exceptionDetails.text)); else if(d.method==='Runtime.consoleAPICalled'&&d.params.type==='error') logs.push('ERR '+d.params.args.map(a=>a.value||a.description).join(' ')); };
const send=(method,params={})=>new Promise(r=>{const i=++id;pend.set(i,r);ws.send(JSON.stringify({id:i,method,params}));});
await send('Runtime.enable'); await send('Page.enable');
await send('Emulation.setDeviceMetricsOverride',{width:+W,height:+H,deviceScaleFactor:1,mobile:+W<700});
await send('Page.navigate',{url});
await sleep(5000);
if (js) { const r = await send('Runtime.evaluate',{expression:js,awaitPromise:true,returnByValue:true}); if(r.result?.value!==undefined) console.log('eval:',JSON.stringify(r.result.value)); await sleep(1200); }
const shot = await send('Page.captureScreenshot',{format:'png'});
fs.writeFileSync(out, Buffer.from(shot.data,'base64'));
console.log(logs.join('\n')||'no console errors');
p.kill(); process.exit(0);
