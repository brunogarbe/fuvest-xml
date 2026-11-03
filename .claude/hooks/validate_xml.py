"""PostToolUse hook: validate any exam XML that Claude just edited."""
import json
import subprocess
import sys

data = json.load(sys.stdin)
path = (data.get("tool_input") or {}).get("file_path", "").replace("\\", "/")
if "/exams/xml" not in path or not path.endswith(".xml"):
    sys.exit(0)

result = subprocess.run(
    ["uv", "run", "fuvest-xml-validate", path, "--summary"],
    capture_output=True, text=True, encoding="utf-8", errors="replace",
)
if result.returncode != 0:
    print(f"XML validation failed for {path}:\n{result.stdout.strip()}", file=sys.stderr)
    sys.exit(2)
