import asyncio
import copy
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from starlette.testclient import TestClient
import httpx

from app import db
from app.city import City
from app.engine import Engine, venue_ids
from app.llm import LLM, SchemaError
from app.venue_api import Project, create, external, geometry
from app.view import snapshot, set_city
import app.main as main

EXAMPLE = Path(__file__).resolve().parents[1] / "examples/night-tea.json"


def project():
    return Project.model_validate(json.loads(EXAMPLE.read_text()))


async def fake_health():
    return {"ok": True, "detail": "тест"}


class ExternalTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=Path(self.temp.name)/"sim.db"
        db.connect(self.path)
        set_city(None)

    def tearDown(self):
        if db.CONN: db.CONN.close()
        self.temp.cleanup()

    def test_create_restart_and_snapshot_have_room_but_no_secrets(self):
        p=project()
        p.controller.api_key="secret-example-only"
        created=create(p)
        self.assertIn("night_tea",venue_ids())
        before=db.CONN
        db.connect(self.path)
        before.close()
        data=snapshot()
        place=next(p for p in data["places"] if p["id"]=="night_tea")
        self.assertEqual(len(place["room"]["seats"]),2)
        self.assertIn("door:counter",place["room"]["paths"])
        self.assertIn("night_tea",data["place_views"])
        self.assertNotIn("secret-example-only",json.dumps(data))
        self.assertNotIn(created["agent_token"],json.dumps(data))
        with db.at_place("night_tea"):
            self.assertEqual(db.items()[0]["load"],0)
            self.assertEqual(len(db.staff()),1)

    def test_duplicate_plot_and_id_are_rejected_without_partial_write(self):
        create(project())
        other=project(); other.id="other"
        from fastapi import HTTPException
        with self.assertRaises(HTTPException): create(other)
        self.assertIsNone(db.place("other"))
        self.assertEqual(db.one("SELECT COUNT(*) AS n FROM external_venues")["n"],1)

    def test_geometry_rejects_collision_and_blocked_door(self):
        p=project()
        p.interior.objects[0].x=0.6
        p.interior.objects[0].y=5.9
        with self.assertRaises(ValueError): geometry(p.interior)
        p=project();p.interior.objects[1].x=2.5;p.interior.objects[1].y=5.0
        with self.assertRaises(ValueError): geometry(p.interior)

    def test_city_arrives_at_external_door_and_can_leave(self):
        create(project())
        city=City(17);city.set_places(db.places())
        result=city.dispatch(991,"Посетитель","night_tea","walk")
        self.assertTrue(result["ok"])
        city.advance(1,480)
        arrived=False
        for minute in range(481,600):
            city.advance(1,minute)
            if any(e["kind"]=="arrived" and e["place"]=="night_tea" for e in city.events):
                arrived=True;break
        self.assertTrue(arrived)
        self.assertTrue(city.release(991))
        city.advance(1,minute+20)
        self.assertNotEqual(city.peds.get(result["ped"]).state if result["ped"] in city.peds else "gone","inside")

    def test_world_director_can_close_external_place_and_knows_its_door(self):
        create(project())
        city=City(2);city.set_places(db.places())
        class WorldLLM:
            prompt=""
            async def complete(self,**kwargs):
                self.prompt=kwargs["user"]
                return {"say":"Чайная закрыта событием.","ops":[{"op":"place","id":"night_tea","status":"closed","x":-22,"y":0}]}
        from app.mind import Mind
        model=WorldLLM()
        engine=Engine(model,lambda payload:None,city)
        ops=asyncio.run(Mind(engine).adjudicate("Закрой ночную чайную"))
        self.assertIn("night_tea",model.prompt)
        self.assertIn("Ночная чайная",model.prompt)
        self.assertEqual(ops[0]["id"],"night_tea")
        self.assertFalse(city.place_open("night_tea",500))
        city.set_places(db.places())
        self.assertFalse(city.place_open("night_tea",500))

    def test_agent_schema_timeout_and_cancellation(self):
        create(project())
        async def work():
            llm=LLM()
            try:
                with db.at_place("night_tea"):
                    task=asyncio.create_task(llm.complete(agent="staff",schema_key="staff",system="Сотрудник",user="Заказ",visit_id=None,week_day=None))
                    while not db.q("SELECT * FROM agent_jobs"): await asyncio.sleep(0.01)
                    row=db.one("SELECT * FROM agent_jobs")
                    payload=json.loads(row["payload_json"])
                    self.assertEqual(payload["role"],"staff")
                    self.assertEqual(payload["place_id"],"night_tea")
                    response={"say":"Травяной чай для вас.","action":"serve","item_id":"Травяной чай","mood":"спокойствие"}
                    db.execute("UPDATE agent_jobs SET status='answered',response_json=? WHERE id=?",(json.dumps(response),row["id"]))
                    self.assertEqual((await task)["action"],"serve")
                    self.assertTrue(db.recent_llm(1)[0]["parsed_json"])
                    task=asyncio.create_task(llm.complete(agent="manager",schema_key="manager",system="Управляющий",user="Неделя",visit_id=None,week_day=5))
                    await asyncio.sleep(0.05);task.cancel()
                    with self.assertRaises(asyncio.CancelledError): await task
                    self.assertFalse(db.q("SELECT * FROM agent_jobs WHERE status='pending'"))
                    ext=external();cfg=json.loads(ext["controller_json"]);cfg["timeout"]=0.02
                    db.execute("UPDATE external_venues SET controller_json=? WHERE place_id='night_tea'",(json.dumps(cfg),))
                    with self.assertRaises(SchemaError):
                        await llm.complete(agent="staff",schema_key="staff",system="Сотрудник",user="Заказ",visit_id=None,week_day=None)
                    self.assertEqual(external()["status"],"offline")
                    self.assertNotEqual(db.run()["status"],"error")
            finally: await llm.aclose()
        asyncio.run(work())

    def test_openai_controller_uses_own_credentials_shared_guest_uses_common_model(self):
        p=project();p.controller.mode="openai";p.controller.base_url="https://owner.example/v1";p.controller.api_key="owner-key"
        create(p)
        requests=[]
        def transport(req):
            requests.append(req)
            content={"say":"Травяной чай для вас.","action":"serve","item_id":"Травяной чай","mood":"спокойствие"}
            if req.url.host != "owner.example":
                content={"say":"Травяной чай, пожалуйста.","item_id":"Травяной чай","request":"","willing_to_wait":True}
            return httpx.Response(200,json={"choices":[{"message":{"content":json.dumps(content)},"finish_reason":"stop"}]})
        async def work():
            llm=LLM();await llm.client.aclose();llm.client=httpx.AsyncClient(transport=httpx.MockTransport(transport))
            try:
                with db.at_place("night_tea"):
                    await llm.complete(agent="staff",schema_key="staff",system="",user="",visit_id=None,week_day=None)
                    await llm.complete(agent="client",schema_key="client",system="",user="",visit_id=None,week_day=None)
            finally: await llm.aclose()
        asyncio.run(work())
        self.assertEqual(requests[0].url.host,"owner.example")
        self.assertEqual(requests[0].headers["authorization"],"Bearer owner-key")
        self.assertNotEqual(requests[1].url.host,"owner.example")
        self.assertNotEqual(requests[1].headers.get("authorization"),"Bearer owner-key")

    def test_visit_shared_guest_external_staff_shared_verdict(self):
        p=project();p.controller.mode="openai";p.controller.base_url="https://owner.example/v1"
        create(p)
        def transport(req):
            data={"say":"Травяной чай для вас.","action":"serve","item_id":"Травяной чай","mood":"спокойствие"}
            return httpx.Response(200,json={"choices":[{"message":{"content":json.dumps(data)},"finish_reason":"stop"}]})
        class SplitLLM(LLM):
            shared=[]
            async def complete(self,**kwargs):
                role=kwargs["agent"]
                if role=="staff": return await super().complete(**kwargs)
                self.shared.append(role)
                if role=="client": return {"say":"Травяной чай, пожалуйста.","item_id":"Травяной чай","request":"","willing_to_wait":True}
                if role=="verdict": return {"say":"Хороший чай.","liked":5,"return":"yes","return_in_days":2,"recommend":True,"review":"Приятное место.","mood":"радость"}
                if role=="critic": return {"score":5,"issues":[]}
                return {"say":"Без изменений.","changes":[]}
        async def work():
            llm=SplitLLM();await llm.client.aclose();llm.client=httpx.AsyncClient(transport=httpx.MockTransport(transport))
            engine=Engine(llm,lambda payload:None)
            try:
                db.set_run(day=1,clock_min=500,clock_real=0)
                with db.at_place("night_tea"):
                    db.add_arrivals(1,[490]);visit=engine._admit(db.next_arrival(1))
                    await engine._serve(visit)
                    row=db.visit(visit)
                    self.assertEqual(row["status"],"served")
                    self.assertEqual(row["price"],180)
                    self.assertEqual(row["review"],"Приятное место.")
                    self.assertEqual(row["served_item_id"],"night_tea:herbal")
                    self.assertEqual(llm.shared,["client","verdict","critic"])
            finally: await llm.aclose()
        asyncio.run(work())

    def test_external_demographer_uses_supported_shared_schema(self):
        p=project();p.controller.mode="openai";p.controller.base_url="https://owner.example/v1"
        create(p)
        hosts=[]
        def transport(req):
            hosts.append(req.url.host)
            return httpx.Response(200,json={"choices":[{"message":{"content":"{\"guests\":[]}"},"finish_reason":"stop"}]})
        async def work():
            llm=LLM();await llm.client.aclose();llm.client=httpx.AsyncClient(transport=httpx.MockTransport(transport))
            try:
                db.set_run(day=1)
                with db.at_place("night_tea"):
                    await Engine(llm,lambda payload:None)._demographer()
            finally: await llm.aclose()
        asyncio.run(work())
        self.assertEqual(len(hosts),1)
        self.assertNotEqual(hosts[0],"owner.example")

    def test_external_manager_adds_item_in_own_namespace_without_gpu_load(self):
        p=project();p.controller.mode="openai";p.controller.base_url="https://owner.example/v1"
        create(p)
        change={"op":"add_item","item_id":"","name":"Мятный чай","price":190,"minutes":2,"available":True}
        def transport(req):
            data={"say":"Гости хотят мятный чай.","changes":[change]}
            return httpx.Response(200,json={"choices":[{"message":{"content":json.dumps(data)},"finish_reason":"stop"}]})
        async def work():
            llm=LLM();await llm.client.aclose();llm.client=httpx.AsyncClient(transport=httpx.MockTransport(transport))
            try:
                db.set_run(day=5)
                engine=Engine(llm,lambda payload:None)
                with db.at_place("night_tea"):
                    self.assertTrue(await engine._manager())
                    added=next(i for i in db.items() if i["name"]=="Мятный чай")
                    self.assertTrue(added["id"].startswith("night_tea:new"))
                    self.assertEqual(added["load"],0)
                with db.at_place("cafe"):
                    self.assertFalse(any(i["name"]=="Мятный чай" for i in db.items()))
            finally: await llm.aclose()
        asyncio.run(work())

    def test_http_permissions_response_schema_duplicates_expiry_and_status(self):
        original=db.connect
        with patch.object(db,"connect",side_effect=lambda:original(self.path)),patch.object(main,"llm_health",fake_health):
            with TestClient(main.app) as client:
                caps=client.get("/api/venues/capabilities")
                self.assertEqual(caps.status_code,200)
                raw=json.loads(EXAMPLE.read_text())
                self.assertTrue(client.post("/api/venues/validate",json=raw).json()["ok"])
                result=client.post("/api/venues",json=raw)
                self.assertEqual(result.status_code,201)
                token=result.json()["agent_token"]
                headers={"Authorization":"Bearer "+token}
                base="/api/venues/night_tea"
                self.assertEqual(client.get(base+"/jobs").status_code,403)
                self.assertEqual(client.get(base+"/jobs",headers=headers).status_code,200)
                from app.llm import SCHEMAS
                payload={"role":"staff","response_schema":SCHEMAS["staff"]["schema"],"final_staff":False}
                with db.tx() as conn:
                    conn.execute("INSERT INTO agent_jobs VALUES(?,?,?,'pending',?,NULL,?)",("job","night_tea",json.dumps(payload),time.time()+10,time.time()))
                url=base+"/jobs/job/answer"
                self.assertEqual(client.post(url,json={"response":{}},headers=headers).status_code,422)
                reply={"say":"Травяной чай для вас.","action":"serve","item_id":"Травяной чай","mood":"спокойствие"}
                self.assertEqual(client.post(url,json={"response":reply},headers=headers).status_code,200)
                self.assertTrue(client.post(url,json={"response":reply},headers=headers).json()["duplicate"])
                reply["say"]="Другая реплика."
                self.assertEqual(client.post(url,json={"response":reply},headers=headers).status_code,409)
                db.execute("UPDATE agent_jobs SET status='pending',deadline=? WHERE id='job'",(time.time()-1,))
                self.assertEqual(client.post(url,json={"response":reply},headers=headers).status_code,409)
                self.assertEqual(client.post(base+"/status",json={"enabled":False},headers=headers).status_code,200)
                self.assertFalse(main.app.state.engine.city.place_open("night_tea",500))
                db.set_run(day=1,day_closed=0,clock_min=500,clock_real=0)
                self.assertEqual(client.post(base+"/status",json={"enabled":True},headers=headers).status_code,200)
                with db.at_place("night_tea"):
                    self.assertEqual(db.scheduled_left(1),1)
                self.assertNotIn(token,client.get("/api/snapshot").text)
                self.assertEqual(client.post("/api/venues",json=raw).status_code,409)
                bad=copy.deepcopy(raw);bad["id"]="invalid";bad["items"][0]["price"]=True
                self.assertEqual(client.post("/api/venues/validate",json=bad).status_code,422)
