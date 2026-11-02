"""Bounded Soup MCP and Colab CLI adapters. No shell strings are executed."""
import json
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import sys
import threading

def redact(value):
    value = re.sub(r'(?i)Bearer\s+[^\s\'"},]+', 'Bearer [REDACTED]', str(value))
    value = re.sub(r'ya29\.[^\s\'"},]+', '[REDACTED]', value)
    value = re.sub(r'(?i)((?:access_token|refresh_token|authorization|colab-runtime-proxy-token)[\s"\x27:=]+)[^\s,}"\x27]+', r'\1[REDACTED]', value)
    return value

def soup_command():
    if os.environ.get("KIRA_SOUP_COMMAND"):
        cmd = json.loads(os.environ["KIRA_SOUP_COMMAND"])
        if not isinstance(cmd, list) or not cmd or not all(isinstance(s, str) for s in cmd):
            raise ValueError("KIRA_SOUP_COMMAND must be a JSON argv array")
        return cmd
    if shutil.which("soup"):
        return [shutil.which("soup"), "mcp", "serve"]
    # Discover the user's existing Soup plugin without copying credentials/configuration.
    for manifest in sorted((Path.home()/".codex/plugins/cache/personal/soup-mcp").glob("*/.mcp.json"), reverse=True):
        conf = json.loads(manifest.read_text())["mcpServers"]["soup"]
        if Path(conf["command"]).is_file():
            return [conf["command"], *conf.get("args", [])]
    return None

def soup_call(workspace, name, args):
    allowed = {"data_inspect", "data_validate", "data_score", "data_doctor", "advise", "recipes_search", "recipes_show", "profile", "train_start", "runs_list", "runs_show"}
    if name not in allowed:
        raise ValueError("Unsupported Soup tool")
    cmd = soup_command()
    if not cmd:
        raise ValueError("Soup is not installed. Install soup-cli or set KIRA_SOUP_COMMAND to its MCP server argv.")
    proc = subprocess.Popen(cmd, cwd=workspace, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    messages = queue.Queue()
    def read():
        for line in proc.stdout:
            try: messages.put(json.loads(line))
            except json.JSONDecodeError: continue
        messages.put({"eof": True})
    threading.Thread(target=read, daemon=True).start()
    def send(obj):
        proc.stdin.write(json.dumps(obj) + "\n")
        proc.stdin.flush()
    def response(rid):
        import time
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            msg = messages.get(timeout=max(.01, deadline-time.monotonic()))
            if msg.get("eof"): raise ValueError("Soup MCP exited before returning a response")
            if msg.get("id") == rid:
                if "error" in msg: raise ValueError(str(msg["error"]))
                return msg["result"]
        raise ValueError("Soup inspection timed out")
    try:
        send({"jsonrpc":"2.0", "id":1, "method":"initialize", "params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"kira-training-space","version":"0.2.1"}}})
        response(1)
        send({"jsonrpc":"2.0", "method":"notifications/initialized"})
        send({"jsonrpc":"2.0", "id":2, "method":"tools/call", "params":{"name":name,"arguments":args}})
        return response(2)
    except queue.Empty:
        raise ValueError("Soup inspection timed out") from None
    finally:
        proc.terminate()
        try: proc.wait(timeout=3)
        except subprocess.TimeoutExpired: proc.kill(); proc.wait()
        proc.stdin.close(); proc.stdout.close()

def colab_command(project):
    if os.environ.get("KIRA_COLAB_PYTHON"):
        return [os.environ["KIRA_COLAB_PYTHON"], str(Path(__file__).with_name("safe_colab.py"))]
    candidate = Path(project)/".venv-colab-cli/bin/python"
    if candidate.is_file():
        return [str(candidate), str(Path(__file__).with_name("safe_colab.py"))]
    if shutil.which("colab"):
        # The console entry point's interpreter owns the installed module.
        first = Path(shutil.which("colab")).read_text().splitlines()[0]
        if first.startswith("#!/") and " " not in first[2:]:
            return [first[2:], str(Path(__file__).with_name("safe_colab.py"))]
    return None

def colab_call(project, args, timeout=30):
    cmd = colab_command(project)
    if not cmd: raise ValueError("Install google-colab-cli or set KIRA_COLAB_PYTHON to its Python interpreter.")
    try:
        result = subprocess.run(cmd + args, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        raise ValueError("Colab timed out. Check authentication in a terminal, then refresh the connection.") from None
    # Errors may carry signed runtime URLs or OAuth state. Expose a bounded generic failure.
    if result.returncode:
        return {"ok": False, "message": "Colab CLI could not complete the request. Check terminal authentication and permissions.", "exit_code": result.returncode}
    return {"ok": True, "output": redact(result.stdout)[-16000:]}
