"""Allowlisted distribution files only; never archive a local workspace."""
import io
import json
from pathlib import Path
import zipfile

def plugin_archive():
    root=Path(__file__).parent.parent
    output=io.BytesIO()
    allowed=[root/p for p in ("plugin.json","mcp.json","README.md",".codex-plugin/plugin.json")]
    runtime_files=["soup_training.py","catalog.py","integrations.py","safe_colab.py","core.py","train_template.py","server.py","package_tools.py",
                   "web/index.html","web/style.css","web/app.js"]
    allowed.extend(root/"runtime"/p for p in runtime_files)
    allowed.extend(root/p for p in ["skills/training-space/SKILL.md","assets/icon.svg","assets/wordmark.svg"])
    if (root/"assets/preview.png").is_file(): allowed.append(root/"assets/preview.png")
    with zipfile.ZipFile(output,"w",zipfile.ZIP_DEFLATED) as archive:
        for file in allowed:
            if file.is_symlink() or not file.resolve().is_relative_to(root.resolve()): raise ValueError("Distribution files must remain inside the plugin")
            archive.write(file,"kira-training-space/"+str(file.relative_to(root)))
        archive.writestr("marketplace.json",json.dumps({"name":"kira-training-local","interface":{"displayName":"Kira Training"},"plugins":[{"name":"kira-training-space","source":{"source":"local","path":"./kira-training-space"},"policy":{"installation":"AVAILABLE","authentication":"ON_INSTALL"},"category":"Developer Tools"}]},indent=2))
    return output.getvalue()
