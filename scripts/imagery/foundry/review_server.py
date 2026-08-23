"""Card Review server — Mario paints corrections on a hole card; the server turns strokes into
per-class masks, re-renders the hole through the pipeline, and serves the new card back.

  GET  /                      the review app (review.html)
  GET  /api/state?hole=N      images available, approved flag, last result, corrections summary
  GET  /api/status?hole=N     {running, log tail, result}
  POST /api/marks             {hole, strokes:[{tool, width, points:[[x,y],...]}], notes} -> masks + re-render
  POST /api/approve           {hole, approved: true|false}
  GET  /img/<kind>/<NN>.jpg   kind in card|skeleton|aerial|original|previous

Strokes arrive in 900x1200 card pixels. Tools: clear (remove trees), addtree (points), fairway, rough,
dry, water, sand, erase (removes marks of all tools under the stroke).
"""
from __future__ import annotations

import io
import json
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import cv2
import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
REPO = Path.home() / "rex/peach-tree-golf-tracker"
PY = HERE / ".venv/bin/python"
MARKS = HERE / "marks"
MARKS.mkdir(exist_ok=True)
TOOLS_MASK = ["clear", "fairway", "rough", "dry", "water", "sand"]
RUNS: dict[int, dict] = {}
LOCK = threading.Lock()


def load_rgb(p: Path, size=(900, 1200)) -> Image.Image:
    im = Image.open(p).convert("RGB")
    return im if im.size == size else im.resize(size, Image.LANCZOS)


def img_path(kind: str, hole: int) -> Path | None:
    hh = f"{hole:02d}"
    cands = {
        "card": [HERE / "final" / f"hole-{hh}.png"],
        "previous": [HERE / "final-crowns-2026-08-22" / f"hole-{hh}.png"],
        "skeleton": [HERE / "cond" / f"hole-{hh}-base-v6.png"],
        "aerial": [REPO / "public/course/peach-tree" / f"hole-{hh}.webp"],
        "original": [HERE / "refs" / f"hole-{hh}-original.png"],
    }.get(kind, [])
    for c in cands:
        if c.exists():
            return c
    return None


def rasterize(hole: int, strokes: list[dict]) -> dict:
    """Accumulate strokes into per-tool masks (persisted PNGs) + add-tree points (JSON)."""
    hh = f"{hole:02d}"
    masks = {}
    for t in TOOLS_MASK:
        p = MARKS / f"hole-{hh}-{t}.png"
        masks[t] = (np.array(Image.open(p).convert("L")) > 127).astype(np.uint8) if p.exists() else np.zeros((1200, 900), np.uint8)
    pts_p = MARKS / f"hole-{hh}-addtree.json"
    adds = json.loads(pts_p.read_text()) if pts_p.exists() else []
    for s in strokes:
        tool = s.get("tool")
        w = max(2, int(s.get("width", 20)))
        pts = np.array([[int(round(x)), int(round(y))] for x, y in s.get("points", [])], np.int32)
        if tool == "addtree":
            for x, y in pts[:1] if len(pts) else []:
                adds.append([int(x), int(y), int(max(13, w // 2))])
            continue
        if len(pts) == 0:
            continue
        layer = np.zeros((1200, 900), np.uint8)
        if len(pts) == 1:
            cv2.circle(layer, tuple(pts[0]), w // 2, 1, -1)
        else:
            cv2.polylines(layer, [pts], False, 1, thickness=w, lineType=cv2.LINE_AA)
        if tool == "erase":
            for t in TOOLS_MASK:
                masks[t][layer > 0] = 0
            adds = [a for a in adds if layer[min(1199, max(0, a[1])), min(899, max(0, a[0]))] == 0]
        elif tool in masks:
            masks[tool][layer > 0] = 1
            # a class stroke also clears competing class marks under it
            for t in TOOLS_MASK:
                if t != tool and t != "clear":
                    masks[t][layer > 0] = 0
    for t, m in masks.items():
        Image.fromarray(m * 255).save(MARKS / f"hole-{hh}-{t}.png")
    pts_p.write_text(json.dumps(adds))
    return {"masks": {t: int(m.sum()) for t, m in masks.items()}, "addTrees": len(adds)}


def run_pipeline(hole: int, note: str) -> None:
    hh = f"{hole:02d}"
    with LOCK:
        RUNS[hole] = {"running": True, "started": time.time(), "log": "", "result": None}
    log_p = HERE / "logs" / f"review-hole-{hh}.log"
    with open(log_p, "w") as lf:
        proc = subprocess.Popen([str(PY), "pipeline_hole.py", "--hole", str(hole), "--attempts", "3"], cwd=HERE, stdout=lf, stderr=subprocess.STDOUT)
        proc.wait()
    res = None
    jp = HERE / "final" / f"hole-{hh}.json"
    if jp.exists():
        m = json.loads(jp.read_text())
        b = m["best"]["vsSkeleton150"]
        qw = m["best"].get("qwen", {})
        res = {"pass": m["pass"], "max": b["landMaxYards"], "median": b["landMedianYards"], "attempt": m["best"]["attempt"], "seconds": m["secondsTotal"],
               "qwen": (("OK" if qw.get("pass") else "issues: " + ", ".join(qw.get("issues", []))) if qw.get("available") else None)}
    with LOCK:
        RUNS[hole] = {"running": False, "finished": time.time(), "log": log_p.read_text()[-2000:], "result": res}


class H(BaseHTTPRequestHandler):
    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(body)

    def _bytes(self, data: bytes, ctype: str):
        self.send_response(200); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(data)

    def log_message(self, *a):  # quiet
        pass

    def do_GET(self):
        u = urlparse(self.path); q = parse_qs(u.query)
        if u.path in ("/", "/index.html", "/review.html"):
            self._bytes((HERE / "review.html").read_bytes(), "text/html; charset=utf-8"); return
        if u.path.startswith("/img/"):
            _, _, kind, name = u.path.split("/", 3)
            hole = int(name.split(".")[0])
            p = img_path(kind, hole)
            if not p:
                self.send_response(404); self.end_headers(); return
            buf = io.BytesIO(); load_rgb(p).save(buf, "JPEG", quality=88); self._bytes(buf.getvalue(), "image/jpeg"); return
        if u.path == "/api/state":
            hole = int(q.get("hole", ["7"])[0]); hh = f"{hole:02d}"
            appr = json.loads((HERE / "approved.json").read_text()) if (HERE / "approved.json").exists() else {}
            res = None
            jp = HERE / "final" / f"hole-{hh}.json"
            if jp.exists():
                m = json.loads(jp.read_text()); b = m["best"]["vsSkeleton150"]; qw = m["best"].get("qwen", {})
                res = {"pass": m["pass"], "max": b["landMaxYards"], "median": b["landMedianYards"], "attempt": m["best"].get("attempt"),
                       "qwen": (("OK" if qw.get("pass") else "issues: " + ", ".join(qw.get("issues", []))) if qw.get("available") else None)}
            marks = {t: (MARKS / f"hole-{hh}-{t}.png").exists() for t in TOOLS_MASK}
            self._json({"hole": hole, "images": {k: bool(img_path(k, hole)) for k in ("card", "previous", "skeleton", "aerial", "original")},
                        "approved": appr.get(str(hole), False), "result": res, "marks": marks, "running": RUNS.get(hole, {}).get("running", False)}); return
        if u.path == "/api/status":
            hole = int(q.get("hole", ["7"])[0]); self._json(RUNS.get(hole, {"running": False, "result": None, "log": ""})); return
        if u.path == "/api/marks":
            hole = int(q.get("hole", ["7"])[0]); hh = f"{hole:02d}"
            # return the current masks as one RGBA overlay so the page can show what is already marked
            ov = np.zeros((1200, 900, 4), np.uint8)
            colors = {"clear": (230, 60, 60), "fairway": (120, 220, 80), "rough": (40, 140, 60), "dry": (220, 180, 110), "water": (60, 140, 230), "sand": (245, 235, 200)}
            for t, c in colors.items():
                p = MARKS / f"hole-{hh}-{t}.png"
                if p.exists():
                    m = np.array(Image.open(p).convert("L")) > 127
                    ov[m] = (*c, 110)
            pts_p = MARKS / f"hole-{hh}-addtree.json"
            for x, y, r in (json.loads(pts_p.read_text()) if pts_p.exists() else []):
                cv2.circle(ov, (int(x), int(y)), int(r), (90, 60, 30, 200), 3)
            buf = io.BytesIO(); Image.fromarray(ov, "RGBA").save(buf, "PNG"); self._bytes(buf.getvalue(), "image/png"); return
        self.send_response(404); self.end_headers()

    def do_POST(self):
        u = urlparse(self.path)
        n = int(self.headers.get("Content-Length", "0")); data = json.loads(self.rfile.read(n) or b"{}")
        if u.path == "/api/marks":
            hole = int(data["hole"])
            if RUNS.get(hole, {}).get("running"):
                self._json({"ok": False, "error": "already rendering this hole"}, 409); return
            summary = rasterize(hole, data.get("strokes", []))
            note = (data.get("notes") or "").strip()
            if note:
                with open(HERE / "marks" / "notes.log", "a") as nf:
                    nf.write(f"{time.strftime('%Y-%m-%d %H:%M')} hole {hole}: {note}\n")
            if data.get("render", True):
                threading.Thread(target=run_pipeline, args=(hole, note), daemon=True).start()
            self._json({"ok": True, "summary": summary, "rendering": bool(data.get("render", True))}); return
        if u.path == "/api/clear-marks":
            hole = int(data["hole"]); hh = f"{hole:02d}"
            for t in TOOLS_MASK:
                p = MARKS / f"hole-{hh}-{t}.png"; p.unlink(missing_ok=True)
            (MARKS / f"hole-{hh}-addtree.json").unlink(missing_ok=True)
            self._json({"ok": True}); return
        if u.path == "/api/approve":
            hole = int(data["hole"]); p = HERE / "approved.json"
            appr = json.loads(p.read_text()) if p.exists() else {}
            appr[str(hole)] = bool(data.get("approved", True)); p.write_text(json.dumps(appr, indent=1))
            self._json({"ok": True, "approved": appr}); return
        self.send_response(404); self.end_headers()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8792
    print(f"Card Review on http://localhost:{port}/", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
