#!/usr/bin/env python3
"""Внешний агент: создаёт заведение из проекта и обслуживает задания своей моделью."""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


def request(url, method="GET", data=None, token="", timeout=30):
    body=json.dumps(data,ensure_ascii=False).encode() if data is not None else None
    headers={"Content-Type":"application/json"}
    if token: headers["Authorization"]="Bearer "+token
    req=urllib.request.Request(url,body,headers,method=method)
    with urllib.request.urlopen(req,timeout=timeout) as response:
        return json.load(response)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--loom",default=os.environ.get("LOOM_URL","http://192.168.0.16:8421"))
    parser.add_argument("--credentials",type=Path,required=True,help="Локальный файл id и токена заведения")
    parser.add_argument("--create",type=Path,help="Создать заведение по JSON-проекту и сохранить токен")
    parser.add_argument("--base-url",default=os.environ.get("VENUE_LLM_URL","http://127.0.0.1:8080/v1"))
    parser.add_argument("--model",default=os.environ.get("VENUE_LLM_MODEL",""))
    parser.add_argument("--poll",type=float,default=0.3)
    args=parser.parse_args()
    root=args.loom.rstrip("/")
    if args.create:
        if args.credentials.exists():
            parser.error("Файл credentials уже существует; выберите другой, чтобы не потерять токен")
        project=json.loads(args.create.read_text())
        result=request(root+"/api/venues","POST",project)
        credentials={"place_id":result["place"]["id"],"agent_token":result["agent_token"]}
        fd=os.open(args.credentials,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,"w") as out: json.dump(credentials,out)
        print("Заведение создано: "+credentials["place_id"],file=sys.stderr)
    credentials=json.loads(args.credentials.read_text())
    if not args.model:
        parser.error("Для работы нужен --model или VENUE_LLM_MODEL; токен созданного заведения сохранён")
    base=root+"/api/venues/"+credentials["place_id"]
    token=credentials["agent_token"]
    request(base+"/status","POST",{"enabled":True},token)
    print("Агент подключён. Ключ модели читается из VENUE_LLM_API_KEY.",file=sys.stderr)
    while True:
        try:
            for job in request(base+"/jobs",token=token)["jobs"]:
                remaining=job["deadline"]-time.time()
                if remaining<=0: continue
                response=request(args.base_url.rstrip("/")+"/chat/completions","POST",{
                    "model":args.model,
                    "messages":[{"role":"system","content":job["system"]},{"role":"user","content":job["user"]}],
                    "max_tokens":2048 if job["attempt"]==1 else 4096,
                    "response_format":{"type":"json_schema","json_schema":{"name":job["schema_key"],"strict":True,"schema":job["response_schema"]}},
                },os.environ.get("VENUE_LLM_API_KEY",""),timeout=max(0.1,remaining))
                choice=response["choices"][0]
                if choice.get("finish_reason") not in (None,"stop"):
                    raise ValueError("Ответ модели не завершён: "+str(choice.get("finish_reason")))
                answer=json.loads(choice["message"]["content"])
                request(base+"/jobs/"+job["request_id"]+"/answer","POST",{"response":answer},token)
        except (urllib.error.URLError,ValueError,KeyError,TimeoutError) as exc:
            # Не печатаем HTTP body, промпты, URL и ключи.
            print("Задание не выполнено: "+type(exc).__name__,file=sys.stderr)
        time.sleep(max(0.1,args.poll))


if __name__=="__main__":
    try: main()
    except KeyboardInterrupt: pass
