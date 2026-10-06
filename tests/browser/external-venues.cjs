const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
(async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || undefined, headless: true, args: ['--no-sandbox', '--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    const base = process.env.LOOM_TEST_URL || 'http://127.0.0.1:8433';
    await page.goto(base);
    await page.waitForFunction(() => typeof ROOMS !== 'undefined' && ROOMS.size === 2);
    const project = JSON.parse(fs.readFileSync('examples/night-tea.json', 'utf8'));
    const response = await page.request.post(base + '/api/venues', { data: project });
    assert.equal(response.status(), 201);
    const created = await response.json();
    await page.waitForFunction(() => ROOMS.has('night_tea') && snap.place_views.night_tea);
    const info = await page.evaluate(() => {
      const room = ROOMS.get('night_tea');
      return { theme: room.theme, objects: room.fields.statics.length, seats: room.layout.seats.length, actors: room.actors.size, paths: Object.keys(room.layout.paths).length };
    });
    assert.equal(info.theme, 'custom');
    assert.equal(info.objects, 7);
    assert.equal(info.seats, 2);
    assert.equal(info.actors, 1);
    assert.ok(info.paths >= 20);
    await page.evaluate(() => openPlace('night_tea'));
    assert.equal(await page.locator('#pc-name').innerText(), 'Ночная чайная');
    await page.locator('#placecard [data-tab="menu"]').click();
    assert.ok((await page.locator('#placecard').innerText()).includes('Травяной чай'));
    // Только тестовый снимок в браузере: серверный прогон не запускается.
    await page.evaluate(async () => {
      socket.onclose = null; socket.close();
      const data = JSON.parse(JSON.stringify(snap));
      data.run = { ...data.run, day: 1, status: 'paused', clock_min: 545, phase: '', thinking: 0 };
      const visit = { id: 9101, day: 1, clock: '08:40', start_min: 520, serve_min: 520, end_min: 530, stay_min: 30,
        status: 'served', client_id: 9101, client_name: 'Гость чайной', staff_id: 'night_tea:tea_master', staff_name: 'Лев', place_id: 'night_tea', is_return: 0, mood: 'бодрость', side: 0, price: 180 };
      data.place_views.night_tea.day_visits = [visit];
      data.clients.push({ id: 9101, name: visit.client_name, history: [visit] });
      data.current_visit = null;
      await applySnapshot(data);
    });
    const seated = await page.evaluate(() => withRoom(ROOMS.get('night_tea'), () => stateAt(lives[0], 545)));
    assert.equal(seated.pose, 'sit');
    assert.ok([2.5, 5].includes(seated.x));
    if (process.env.LOOM_SCREENSHOTS) await page.screenshot({ path: process.env.LOOM_SCREENSHOTS + '/external-venue.png' });
    await page.evaluate(() => withRoom(ROOMS.get('night_tea'), () => selectActor(9101)));
    assert.equal(await page.evaluate(() => selectedGuest), 9101);
    // Удаление после сброса должно освободить комнату и вывеску.
    await page.evaluate(async () => {
      const data = JSON.parse(JSON.stringify(snap));
      data.places = data.places.filter(p => p.id !== 'night_tea');
      delete data.place_views.night_tea;
      data.clients = data.clients.filter(p => p.id !== 9101);
      await applySnapshot(data);
    });
    assert.equal(await page.evaluate(() => ROOMS.has('night_tea')), false);
    assert.equal(await page.locator('#signs [data-place="night_tea"]').count(), 0);
    assert.deepEqual(errors, []);
    const headers = { Authorization: 'Bearer ' + created.agent_token };
    const stop = await page.request.post(base + '/api/venues/night_tea/status', { headers, data: { enabled: false } });
    assert.equal(stop.status(), 200);
    console.log('PASS: создание без перезагрузки, интерьер, каталог, агент, рассадка, выбор гостя, удаление комнаты.');
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exit(1); });
