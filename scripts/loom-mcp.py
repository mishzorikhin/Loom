#!/usr/bin/env python3
"""MCP stdio-мост к HTTP API Loom. Запускается на компьютере владельца, без SDK-зависимостей."""
import importlib.util
import json
import os
import sys
from pathlib import Path

spec=importlib.util.spec_from_file_location("venue_agent",Path(__file__).with_name("venue-agent.py"))
helper=importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)
ROOT=os.environ.get("LOOM_URL","http://192.168.0.16:8421").rstrip("/")


def tools():
    schema=helper.request(ROOT+"/api/venues/capabilities")["project_schema"]
    empty={"type":"object","properties":{},"additionalProperties":False}
    project={"type":"object","properties":{"project":schema},"required":["project"],"additionalProperties":False}
    # Pydantic refs относятся к корню самой схемы; переносим определения в корень инструмента.
    project["$defs"]=schema.pop("$defs",{})
    owned={"type":"object","properties":{"place_id":{"type":"string"},"agent_token":{"type":"string"}},"required":["place_id","agent_token"],"additionalProperties":False}
    return [
        {"name":"loom_capabilities","description":"Правила и каталог строительства Loom","inputSchema":empty},
        {"name":"loom_plots","description":"Свободные участки общего квартала","inputSchema":empty},
        {"name":"loom_validate_venue","description":"Проверить проект, пересечения и проходы","inputSchema":project},
        {"name":"loom_create_venue","description":"Открыть заведение. Возвращает секретный токен управления; сохраните его у владельца","inputSchema":project},
        {"name":"loom_observe","description":"Наблюдать общий мир и заведения","inputSchema":empty},
        {"name":"loom_agent_jobs","description":"Забрать задания сотрудников своего заведения","inputSchema":owned},
        {"name":"loom_agent_answer","description":"Ответить по response_schema задания","inputSchema":{**owned,"properties":{**owned["properties"],"request_id":{"type":"string"},"response":{"type":"object"}},"required":[*owned["required"],"request_id","response"]}},
        {"name":"loom_agent_enable","description":"Возобновить приём после отключения агента","inputSchema":owned},
    ]


def call(name,args):
    if name=="loom_capabilities": return helper.request(ROOT+"/api/venues/capabilities")
    if name=="loom_plots": return helper.request(ROOT+"/api/venues/plots")
    if name=="loom_observe": return helper.request(ROOT+"/api/snapshot")
    if name in ("loom_validate_venue","loom_create_venue"):
        return helper.request(ROOT+"/api/venues"+("/validate" if name=="loom_validate_venue" else ""),"POST",args["project"])
    from urllib.parse import quote
    base=ROOT+"/api/venues/"+quote(args["place_id"],safe="")
    token=args["agent_token"]
    if name=="loom_agent_jobs": return helper.request(base+"/jobs",token=token)
    if name=="loom_agent_answer": return helper.request(base+"/jobs/"+quote(args["request_id"],safe="")+"/answer","POST",{"response":args["response"]},token)
    if name=="loom_agent_enable": return helper.request(base+"/status","POST",{"enabled":True},token)
    raise ValueError("Неизвестный инструмент")


def handle(msg):
    method=msg.get("method")
    if "id" not in msg: return None
    if method=="initialize":
        version=msg.get("params",{}).get("protocolVersion")
        return {"protocolVersion":version if version in ("2024-11-05","2025-03-26","2025-06-18","2025-11-25") else "2025-11-25","capabilities":{"tools":{}},"serverInfo":{"name":"loom","version":"1.0.0"}}
    if method=="ping": return {}
    if method=="tools/list": return {"tools":tools()}
    if method=="tools/call":
        params=msg["params"]
        try:
            result=call(params["name"],params.get("arguments",{}))
            return {"content":[{"type":"text","text":json.dumps(result,ensure_ascii=False)}],"isError":False}
        except helper.urllib.error.HTTPError as exc:
            detail=json.loads(exc.read()).get("detail","Запрос не принят")
            return {"content":[{"type":"text","text":json.dumps({"status":exc.code,"detail":detail},ensure_ascii=False)}],"isError":True}
    raise ValueError("Метод не поддержан")


def main():
    for line in sys.stdin:
        msg={}
        try:
            msg=json.loads(line)
            result=handle(msg)
            if result is None: continue
            response={"jsonrpc":"2.0","id":msg["id"],"result":result}
        except Exception as exc:
            response={"jsonrpc":"2.0","id":msg.get("id"),"error":{"code":-32603,"message":"Ошибка MCP: "+type(exc).__name__}}
        print(json.dumps(response,ensure_ascii=False),flush=True)


if __name__=="__main__": main()
