#!/usr/bin/env python3
"""Regenerate docs/statusline.png — a screenshot of the codeArbiter statusline with
mock values, rendered ANSI -> styled HTML -> Chromium (Playwright).

Maintenance tool, not part of the shipped plugin. Usage:

    pip install playwright && python -m playwright install chromium
    python tools/statusline-screenshot.py                 # -> docs/statusline.png
    SHOT_OUT=docs/foo.png python tools/statusline-screenshot.py

The bar reads the REAL repo for the git branch and `.codearbiter/` state, so run it
from a clean tree for a tidy shot. Token counts come from the mock transcript below;
the cost is the mock `cost.total_cost_usd`; session age falls back to the mock
transcript's first timestamp (no session metadata exists for the mock id).
"""
import datetime
import html
import json
import os
import re
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SL = os.path.join(ROOT, "plugins", "ca", "hooks", "statusline.py")
now = time.time()


def iso(ts):
    return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S.000Z")


scratch = tempfile.mkdtemp(prefix="ca-shot-")
tx = os.path.join(scratch, "tx.jsonl")
turns = [  # (offset_min, input, cache_write_5m, cache_read, output)
    (62, 800, 6000, 20000, 1800),
    (44, 1500, 10000, 35000, 2800),
    (20, 2000, 16000, 48000, 4200),
    (3, 1200, 13000, 60000, 4400),
]
with open(tx, "w", encoding="utf-8") as f:
    for k, (off, i, cw, cr, out) in enumerate(turns):
        f.write(json.dumps({
            "type": "assistant", "timestamp": iso(now - off * 60), "requestId": f"r{k}",
            "message": {"model": "claude-opus-4-8", "usage": {
                "input_tokens": i, "cache_read_input_tokens": cr,
                "cache_creation_input_tokens": cw,
                "cache_creation": {"ephemeral_5m_input_tokens": cw, "ephemeral_1h_input_tokens": 0},
                "output_tokens": out}}}) + "\n")

# Pre-seed the ledger with an earlier session today so "Today" > "Session".
today = datetime.datetime.now().strftime("%Y-%m-%d")
ledp = os.path.join(scratch, "ledger.json")
with open(ledp, "w", encoding="utf-8") as f:
    json.dump({"sessions": {"earlier-am": {
        "first_ts": now - 6 * 3600, "last_ts": now - 3600, "last_day": today,
        "host_cost": 7.60, "today": {"date": today, "in": 165000, "out": 25000, "cost": 7.60},
        "reqs": {}, "burn": []}}}, f)

payload = {
    "session_id": "demo-shot", "transcript_path": tx,
    "model": {"display_name": "Opus 4.8", "id": "claude-opus-4-8"},
    "effort": {"level": "high"},
    "context_window": {"used_percentage": 41, "context_window_size": 1000000},
    "cost": {"total_cost_usd": 4.20, "total_lines_added": 312, "total_lines_removed": 47},
    "workspace": {"current_dir": ROOT.replace("\\", "/"),
                  "repo": {"owner": "SUaDtL", "name": "codeArbiter"}},
    "rate_limits": {"five_hour": {"used_percentage": 22, "resets_at": int((now + 1.8 * 3600) * 1000)},
                    "seven_day": {"used_percentage": 31, "resets_at": int((now + 3.2 * 86400) * 1000)}},
}
env = dict(os.environ, CODEARBITER_LEDGER=ledp, CODEARBITER_WIDTH="118", PYTHONUTF8="1")
ansi = subprocess.run([sys.executable, SL], input=json.dumps(payload).encode(),
                      capture_output=True, env=env).stdout.decode("utf-8", "replace")

# --- ANSI (truecolor SGR) -> HTML spans ---
SGR = re.compile(r"\033\[([0-9;]*)m")


def line_html(s):
    cur = {"fg": None, "bg": None, "b": False, "d": False}
    out, buf = [], ""

    def style():
        st = []
        if cur["fg"]: st.append(f"color:{cur['fg']}")
        if cur["bg"]: st.append(f"background:{cur['bg']}")
        if cur["b"]: st.append("font-weight:700")
        if cur["d"]: st.append("opacity:.62")
        return ";".join(st)

    def flush():
        nonlocal buf
        if buf:
            out.append(f'<span style="{style()}">{html.escape(buf)}</span>')
            buf = ""

    i, n = 0, len(s)
    while i < n:
        m = SGR.match(s, i)
        if m:
            flush()
            parts = (m.group(1) or "0").split(";")
            j = 0
            while j < len(parts):
                p = parts[j] or "0"
                if p == "0": cur = {"fg": None, "bg": None, "b": False, "d": False}
                elif p == "1": cur["b"] = True
                elif p == "2": cur["d"] = True
                elif p == "38" and parts[j+1:j+2] == ["2"]:
                    cur["fg"] = f"rgb({parts[j+2]},{parts[j+3]},{parts[j+4]})"; j += 4
                elif p == "48" and parts[j+1:j+2] == ["2"]:
                    cur["bg"] = f"rgb({parts[j+2]},{parts[j+3]},{parts[j+4]})"; j += 4
                j += 1
            i = m.end()
        else:
            buf += s[i]; i += 1
    flush()
    return "".join(out)


body = "\n".join(line_html(ln) for ln in ansi.splitlines())
doc = f"""<!doctype html><html><head><meta charset="utf-8"><style>
 html,body{{margin:0;background:#08080c}}
 .wrap{{display:inline-block;padding:22px 24px;background:#0d0d13;border-radius:10px}}
 pre{{margin:0;white-space:pre;font-size:15px;line-height:1.32;letter-spacing:0;
   font-family:'Cascadia Mono','Cascadia Code','Consolas','DejaVu Sans Mono',monospace;
   color:#e8e8f0;-webkit-font-smoothing:antialiased}}
</style></head><body><div class="wrap"><pre>{body}</pre></div></body></html>"""
htmlp = os.path.join(scratch, "shot.html")
open(htmlp, "w", encoding="utf-8").write(doc)

os.makedirs(os.path.join(ROOT, "docs"), exist_ok=True)
outp = os.environ.get("SHOT_OUT", os.path.join(ROOT, "docs", "statusline.png"))
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_context(device_scale_factor=2).new_page()
    pg.goto("file:///" + htmlp.replace("\\", "/"))
    pg.wait_for_timeout(250)
    pg.query_selector(".wrap").screenshot(path=outp)
    b.close()

for f in (tx, ledp, htmlp):
    try: os.remove(f)
    except OSError: pass
try: os.rmdir(scratch)
except OSError: pass
print(f"wrote {os.path.relpath(outp, ROOT)}")
