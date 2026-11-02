"""Loopback app and stdio MCP entry point, using only Python's standard library."""
import argparse
import json
import mimetypes
import os
from pathlib import Path
import secrets
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from core import MAX_DATA, Space
from integrations import colab_call
from package_tools import plugin_archive

WEB = Path(__file__).with_name("web")

def handler(space, token):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args): pass

        def send(self, data, content_type="application/json", status=200, filename=None):
            if not isinstance(data, bytes): data=json.dumps(data,ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type",content_type)
            self.send_header("Content-Length",str(len(data)))
            self.send_header("X-Content-Type-Options","nosniff")
            self.send_header("Cache-Control","no-store")
            self.send_header("Content-Security-Policy","default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            if filename: self.send_header("Content-Disposition",f'attachment; filename="{filename}"')
            self.end_headers(); self.wfile.write(data)

        def guard(self, mutation=False):
            host=self.headers.get("Host","")
            if host not in {f"127.0.0.1:{self.server.server_port}",f"localhost:{self.server.server_port}"}:
                self.send({"error":"Invalid loopback host"},status=403); return False
            if mutation:
                origin=self.headers.get("Origin")
                if origin and origin not in {"http://"+host}:
                    self.send({"error":"Cross-origin request rejected"},status=403); return False
                if not secrets.compare_digest(self.headers.get("X-Kira-Token",""),token):
                    self.send({"error":"Missing session token; reload the app"},status=403); return False
            return True

        def do_GET(self):
            if not self.guard(): return
            parsed=urlparse(self.path); path=parsed.path; q=parse_qs(parsed.query)
            try:
                if path=="/api/state": return self.send(space.state())
                if path=="/api/session": return self.send({"token":token})
                if path=="/api/history": return self.send(space.history(limit=5000),filename="kira-activity-history.json")
                if path=="/api/download":
                    identifier=q.get("id",[""])[0]
                    data=space.content(identifier).encode()
                    if q.get("preview",[""])[0]!="1":
                        space.record_event("downloads","Dataset JSONL served for download",identifier,{"file":"kira-dataset.jsonl"})
                    return self.send(data,"application/x-ndjson",filename="kira-dataset.jsonl")
                if path=="/api/bundle":
                    identifier=q.get("id",[""])[0];data=space.plan_bundle(identifier)
                    space.record_event("downloads","Training bundle served for download",identifier,{"file":"kira-training-plan.zip"})
                    return self.send(data,"application/zip",filename="kira-training-plan.zip")
                if path=="/api/plugin":
                    return self.send(plugin_archive(),"application/zip",filename="kira-training-space-plugin.zip")
                if path=="/icon.svg": return self.send((Path(__file__).parent.parent/"assets/icon.svg").read_bytes(),"image/svg+xml")
                static={"/":"index.html","/app.js":"app.js","/style.css":"style.css"}
                if path in static:
                    file=WEB/static[path]
                    return self.send(file.read_bytes(),mimetypes.guess_type(file)[0] or "text/plain")
                self.send({"error":"Not found"},status=404)
            except Exception as exc: self.send({"error":str(exc)},status=400)

        def do_POST(self):
            if not self.guard(mutation=True): return
            try:
                length=int(self.headers.get("Content-Length",0))
                if length<0 or length>MAX_DATA+1048576: raise ValueError("Request too large")
                body=json.loads(self.rfile.read(length))
                if not isinstance(body,dict): raise ValueError("Expected JSON object")
                path=urlparse(self.path).path
                if path=="/api/import": result=space.import_data(body.get("name",""),body.get("category",""),body.get("content",""))
                elif path=="/api/starter":
                    item=space.item(body["id"])
                    if item["kind"]!="starter": raise ValueError("Choose a starter dataset")
                    result=space.import_data(item["name"],item["category"],space.content(item["id"]))
                elif path=="/api/files": result=space.hub_files(body["id"])
                elif path=="/api/soup": result=space.soup(body["action"],body.get("dataset_id"),body.get("recipe"))
                elif path=="/api/plan": result=space.create_plan(body["dataset_id"],body["model"],body.get("name"),body.get("gpu","T4"))
                elif path=="/api/soup-plan": result=space.soup_training.prepare(body["dataset_id"],body["model"],body.get("name"),body.get("task","sft"))
                elif path=="/api/soup-start": result=space.soup_training.execute(body["id"],body.get("confirmed",False))
                elif path=="/api/soup-status": result=space.soup_training.status(body["id"])
                elif path=="/api/soup-export": result=space.soup_training.export(body["id"],body.get("format","gguf"),body.get("confirmed",False))
                elif path=="/api/start": result=space.start_plan(body["id"],body.get("confirmed",False))
                elif path=="/api/stop": result=space.stop_plan(body["id"],body.get("confirmed",False))
                elif path=="/api/artifact":
                    data=space.download_artifact(body["id"])
                    return self.send(data,"application/zip",filename="kira-adapter.zip")
                elif path=="/api/lesson": result=space.add_lesson(body.get("title"),body.get("body"),body.get("evidence"))
                elif path=="/api/source-download": result=space.record_source_download(body["id"],body["filename"])
                elif path=="/api/colab":
                    action=body.get("action")
                    if action not in {"sessions","usage"}: raise ValueError("Use sessions or usage")
                    result=colab_call(space.project,[action])
                else: return self.send({"error":"Not found"},status=404)
                self.send(result)
            except Exception as exc: self.send({"error":str(exc)},status=400)
    return Handler

TOOLS = [
    {"name":"training_catalog","description":"List categorized training datasets, local inspections, plans, activity history and project lessons.","inputSchema":{"type":"object","properties":{},"additionalProperties":False}},
    {"name":"inspect_dataset","description":"Inspect a JSON/JSONL file inside the configured training workspace. No training is executed.","inputSchema":{"type":"object","properties":{"path":{"type":"string"},"category":{"type":"string"}},"required":["path","category"]}},
    {"name":"dataset_download_files","description":"Resolve direct source download URLs pinned to an immutable Hub dataset revision.","inputSchema":{"type":"object","properties":{"dataset_id":{"type":"string"}},"required":["dataset_id"]}},
    {"name":"soup_inspect","description":"Run a read-only Soup inspection or retrieve a recipe. Does not execute training.","inputSchema":{"type":"object","properties":{"action":{"type":"string","enum":["data_inspect","data_validate","data_score","advise","recipes_search","recipes_show"]},"dataset_id":{"type":"string"},"recipe":{"type":"string"}},"required":["action"]}},
    {"name":"prepare_training","description":"Prepare a downloadable text QLoRA script and Colab command. This only prepares files; it does not use compute.","inputSchema":{"type":"object","properties":{"dataset_id":{"type":"string"},"model":{"type":"string"},"name":{"type":"string"},"gpu":{"type":"string","enum":["T4","L4","A100","H100"]}},"required":["dataset_id","model"]}},
    {"name":"colab_status","description":"Read existing Colab sessions or compute usage through the official installed CLI.","inputSchema":{"type":"object","properties":{"action":{"type":"string","enum":["sessions","usage"]}}}},
]

for name,description,properties,required in [
 ("prepare_soup_training","Prepare and validate optional full local Soup SFT/DPO training; no compute starts.",{"dataset_id":{"type":"string"},"model":{"type":"string"},"name":{"type":"string"},"task":{"type":"string","enum":["sft","dpo"]}},["dataset_id","model"]),
 ("execute_soup_training","Execute a reviewed Soup training plan. Requires explicit user authorization; may download weights and use local compute.",{"id":{"type":"string"},"confirmed":{"type":"boolean"}},["id","confirmed"]),
 ("soup_training_status","Read the recorded Soup run status and bounded logs.",{"id":{"type":"string"}},["id"]),
 ("soup_export","Prepare an export of a completed Soup model, then execute with confirmed=true only after review.",{"id":{"type":"string"},"format":{"type":"string"},"confirmed":{"type":"boolean"}},["id"])]:
    TOOLS.append({"name":name,"description":description,"inputSchema":{"type":"object","properties":properties,"required":required,"additionalProperties":False},"annotations":{"readOnlyHint":name=="soup_training_status","destructiveHint":name in {"execute_soup_training","soup_export"}}})

def mcp(space):
    for line in sys.stdin:
        request={}
        try:
            request=json.loads(line); method=request.get("method"); rid=request.get("id")
            if rid is None: continue
            if method=="initialize": result={"protocolVersion":"2024-11-05","capabilities":{"tools":{}},"serverInfo":{"name":"kira-training-space","version":"0.3.0"}}
            elif method=="ping": result={}
            elif method=="tools/list": result={"tools":TOOLS}
            elif method=="tools/call":
                params=request.get("params",{}); name=params.get("name"); a=params.get("arguments",{})
                try:
                    if name=="training_catalog": value=space.state()
                    elif name=="dataset_download_files": value=space.hub_files(a["dataset_id"])
                    elif name=="inspect_dataset":
                        file=(space.workspace/a["path"]).resolve()
                        if not file.is_relative_to(space.workspace) or file.stat().st_size>MAX_DATA: raise ValueError("Path must be within the training workspace and at most 20 MB")
                        value=space.import_data(file.name,a["category"],file.read_text())
                    elif name=="soup_inspect": value=space.soup(a["action"],a.get("dataset_id"),a.get("recipe"))
                    elif name=="prepare_training": value=space.create_plan(a["dataset_id"],a["model"],a.get("name"),a.get("gpu","T4"))
                    elif name=="prepare_soup_training": value=space.soup_training.prepare(a["dataset_id"],a["model"],a.get("name"),a.get("task","sft"))
                    elif name=="execute_soup_training": value=space.soup_training.execute(a["id"],a.get("confirmed",False))
                    elif name=="soup_training_status": value=space.soup_training.status(a["id"])
                    elif name=="soup_export": value=space.soup_training.export(a["id"],a.get("format","gguf"),a.get("confirmed",False))
                    elif name=="colab_status":
                        action=a.get("action","sessions")
                        if action not in {"sessions","usage"}: raise ValueError("Unsupported Colab action")
                        value=colab_call(space.project,[action])
                    else: raise ValueError("Unknown tool")
                    result={"content":[{"type":"text","text":json.dumps(value,ensure_ascii=False)}]}
                except Exception as exc: result={"isError":True,"content":[{"type":"text","text":str(exc)}]}
            else:
                print(json.dumps({"jsonrpc":"2.0","id":rid,"error":{"code":-32601,"message":"Method not found"}}),flush=True); continue
            print(json.dumps({"jsonrpc":"2.0","id":rid,"result":result}),flush=True)
        except Exception:
            print(json.dumps({"jsonrpc":"2.0","id":request.get("id") if isinstance(request,dict) else None,"error":{"code":-32600,"message":"Invalid request"}}),flush=True)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--mcp",action="store_true")
    parser.add_argument("--port",type=int,default=8765)
    parser.add_argument("--workspace",default=os.environ.get("KIRA_TRAINING_WORKSPACE",str(Path.cwd()/"training-space-data")))
    parser.add_argument("--project",default=os.environ.get("KIRA_PROJECT",str(Path.cwd())))
    args=parser.parse_args(); space=Space(args.workspace,args.project)
    if args.mcp: return mcp(space)
    server=ThreadingHTTPServer(("127.0.0.1",args.port),handler(space,secrets.token_urlsafe(32)))
    print(f"Kira Training Space: http://127.0.0.1:{server.server_port}",flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()

if __name__=="__main__": main()
