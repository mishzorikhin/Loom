const { chromium } = require('playwright');
const assert = require('node:assert/strict');
(async () => {
 const browser = await chromium.launch({executablePath:process.env.CHROMIUM_PATH || undefined,headless:true,args:['--no-sandbox','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
 const page = await browser.newPage({viewport:{width:1440,height:900},hasTouch:true});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 if (process.env.PHASER_RENDERER === 'canvas') await page.route('**/phaser-world.js', async route => { const response = await route.fetch(); await route.fulfill({ response, body: (await response.text()).replace('type: Phaser.AUTO', 'type: Phaser.CANVAS') }); });
 await page.goto(process.env.LOOM_TEST_URL || 'http://127.0.0.1:8422');await page.waitForFunction(()=>typeof scene !== 'undefined' && scene && actors.size===2);
 await page.evaluate(async()=>{await Promise.all([...textureAssets.values()].map(a=>a.promise));});
 await page.evaluate(()=>{
  snap.events=[{id:999,day:1,until_day:1,source:'director',headline:'Новый рецепт',story:'Горячий шоколад появился в меню.',effects:[],changes:[{op:'add_item',name:'Горячий шоколад',price:250}],proposals:['Найм повара пока не поддержан']}];
  renderEventbar();
 });
 assert.ok((await page.locator('[data-event-card="event:999"]').innerText()).includes('В меню: Горячий шоколад · 250 ₽'));
 await page.locator('[data-event-card="event:999"] .ev-toggle').click();
 assert.ok((await page.locator('[data-event-card="event:999"] .ev-detail').innerText()).includes('Пока не выполнено: Найм повара'));
 await page.evaluate(()=>{snap.events=[];renderEventbar();});
 assert.equal(await page.evaluate(()=>Phaser.VERSION),'3.90.0');
 assert.equal(await page.evaluate(()=>scene.signals.length),4);
 assert.equal(await page.evaluate(()=>outer.ambient.filter(c=>c.kind==='car').length),12);
 assert.equal(await page.evaluate(()=>phaserGame.renderer.type),process.env.PHASER_RENDERER === 'canvas' ? 1 : 2);
 await page.evaluate(async()=>{
  socket.close(); socket.onclose=null;
  const data=JSON.parse(JSON.stringify(snap));
  data.run={...data.run,day:1,status:'paused',clock_min:545,day_closed:false,phase:'',thinking:0};
  const base={day:1,clock:'09:00',start_min:540,is_return:0,mood:'бодрость',staff_id:'anya',staff_name:'Аня',wait_min:0};
  data.day_visits=[
   {...base,id:100,client_id:100,client_name:'Гость у стойки',status:'open',serve_min:540},
   {...base,id:101,client_id:101,client_name:'Гость в очереди',status:'waiting',start_min:538},
   {...base,id:102,client_id:102,client_name:'Гость за столом',status:'served',start_min:520,serve_min:520,end_min:530,stay_min:30,served_item_id:'espresso',price:150},
  ];
  data.clients=data.day_visits.map(v=>({id:v.client_id,name:v.client_name,history:[v]}));
  data.current_visit={...data.day_visits[0],lines:[{role:'client',text:'Доброе утро',action:'order'}]};
  await applySnapshot(data);
  visitCache.set(100,data.current_visit);
 });
 await page.waitForTimeout(500);
 let facts=await page.evaluate(()=>({actors:actors.size,queue:stateAt(lives.find(l=>l.visit.id===101),liveMinutes()),seated:stateAt(lives.find(l=>l.visit.id===102),liveMinutes()),cups:scene.cups.filter(c=>c.visible).length}));
 assert.equal(facts.actors,5);assert.equal(facts.queue.stage,'queue');assert.equal(facts.seated.pose,'sit');assert.equal(facts.cups,1);
 const coords=await page.evaluate(()=>{const a=actors.get('v100');const p={left:(a.g.x-view.x)*view.k,top:(a.g.y-35-view.y)*view.k};const r=document.getElementById('room').getBoundingClientRect();return {x:r.left+p.left,y:r.top+p.top};});
 await page.mouse.click(coords.x,coords.y);await page.waitForTimeout(200);
 assert.equal(await page.evaluate(()=>selectedGuest),100);
 assert.equal(await page.locator('#chats').isVisible(),true);
 await page.locator('#close-chats').click();
 await page.locator('#actor-access button[data-client="100"]').focus();await page.keyboard.press('Enter');
 assert.equal(await page.evaluate(()=>selectedGuest),100);
 await page.locator('#close-chats').click();
 await page.locator('#cam-traffic').click();assert.equal(await page.evaluate(()=>CAM.z),1.45);
 await page.locator('#cam-home').click();
 const z=await page.evaluate(()=>CAM.z);await page.locator('#cam-in').click();assert.ok(await page.evaluate(()=>CAM.z)>z);
 const c=await page.locator('#room').boundingBox();
 const before=await page.evaluate(()=>({cx:CAM.cx,cy:CAM.cy}));
 await page.mouse.move(c.x+100,c.y+100);await page.mouse.down();await page.mouse.move(c.x+180,c.y+130,{steps:5});await page.mouse.up();
 assert.notDeepEqual(await page.evaluate(()=>({cx:CAM.cx,cy:CAM.cy})),before);
 assert.equal(await page.evaluate(()=>selectedGuest),null);
 await page.locator('#cam-home').click();assert.equal(await page.evaluate(()=>CAM.z),1);
 await page.mouse.move(c.x+c.width/2,c.y+c.height/2);await page.mouse.wheel(0,-150);await page.waitForTimeout(150);
 assert.ok(await page.evaluate(()=>CAM.z)>1);
 await page.mouse.dblclick(c.x+30,c.y+30);assert.equal(await page.evaluate(()=>CAM.z),1);
 const cdp=await page.context().newCDPSession(page);
 const x=c.x+c.width/2,y=c.y+c.height/2;
 await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:x-40,y,id:1},{x:x+40,y,id:2}]});
 await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:x-80,y,id:1},{x:x+80,y,id:2}]});
 await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
 await page.waitForTimeout(150);assert.ok(await page.evaluate(()=>CAM.z)>1);
 await page.locator('#cam-home').click();
 await page.locator('#lay-life').uncheck();assert.equal(await page.evaluate(()=>outer.ambient.some(a=>a.el.visible)),false);
 await page.locator('#lay-names').uncheck();assert.equal(await page.evaluate(()=>[...actors.values()].some(a=>a.tag.label.visible)),false);
 await page.locator('#lay-life').check();await page.locator('#lay-names').check();
 const paused=await page.evaluate(()=>[...actors.values()].map(a=>[a.g.x,a.g.y]));await page.waitForTimeout(200);
 assert.deepEqual(await page.evaluate(()=>[...actors.values()].map(a=>[a.g.x,a.g.y])),paused);
 await page.evaluate(()=>{snap.run.status='running';snapAt=performance.now();});
await page.waitForTimeout(400);
 // Стойка уже достигнута, проверяем часы и уличный поток.
 assert.ok(await page.evaluate(()=>liveMinutes())>545);
 await page.evaluate(()=>{snap.run.status='paused';snap.run.clock_min=546;renderWorld();});
 if (process.env.LOOM_SCREENSHOTS) await page.screenshot({path:`${process.env.LOOM_SCREENSHOTS}/phaser-guests.png`});
 await page.setViewportSize({width:390,height:844});await page.waitForTimeout(350);
 assert.equal(await page.evaluate(()=>document.documentElement.scrollHeight<=innerHeight+1),true);
 assert.ok(await page.evaluate(()=>phaserGame.canvas.width)>0);
 if (process.env.LOOM_SCREENSHOTS) await page.screenshot({path:`${process.env.LOOM_SCREENSHOTS}/phaser-mobile.png`});
 await page.evaluate(async()=>{
  snap.run.clock_min=1200;renderWorld();
  if (!scene.windowGlows.some(g=>g.alpha>0) || !scene.glows.some(g=>g.alpha>0)) throw new Error("Нет вечернего света");
  for (let i=0;i<40;i++) {
    const a=makeActor(`test:${i}`,looksOf(`Тестовый гость ${i}`),"Тест",null,false,null);
    setPose(a,i%2 ? "sit" : "walk",i%3===0);
    await Promise.all([...textureAssets.values()].map(asset=>asset.promise));
    dropActor(a);
  }
  if (textureAssets.size>256) throw new Error(`Кеш текстур вырос до ${textureAssets.size}`);
 });
 assert.deepEqual(errors,[]);
 console.log('PASS: Phaser, textures, guests, queue, seats, clicks, keyboard, zoom, drag, layers, pause, clock, mobile.');
 await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
