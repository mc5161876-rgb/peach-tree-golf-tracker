"""Content QA with the local Qwen 3.8 (vision) via Ollama: does the finished card still show what the
skeleton says? Catches class errors the drift gate cannot see (fairway over the green, missing tee box,
a tree on the fairway, water where there is none). Soft gate: returns flags; never blocks on failure.
"""
from __future__ import annotations
import base64, io, json, os, time, urllib.request
from pathlib import Path
from PIL import Image

HOST = os.environ.get("OLLAMA_HOST", "100.120.28.101:11434")
MODEL = "qwen3.8:27b"
CHECKS = [
    ("teeBox", "Is there a distinct mown tee pad at the bottom end of the gold line? (yes = good)"),
    ("fairwayStopsShortOfGreen", "Does the light mown fairway strip stop short of the putting green at the top, i.e. the green is a separate, rounder, lighter area with its own edge? (yes = good)"),
    ("noTreeOnFairway", "Is the mown fairway strip free of trees standing inside it? (yes = good)"),
    ("noTreeOnGreen", "Is the putting green free of trees standing on it? (yes = good)"),
    ("waterMatches", "Looking at both images: does water appear in the second image ONLY where the first image shows blue water? (yes = good)"),
    ("bunkersMatch", "Do the sand bunkers in the second image sit where the first image shows sand, with none added or missing? (yes = good)"),
]

def _b64(p: Path, size=(450, 600)) -> str:
    im = Image.open(p).convert("RGB").resize(size)
    buf = io.BytesIO(); im.save(buf, "JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()

def _ask(images, checks, timeout):
    q = ("Answer each numbered question about the image(s) with exactly 'yes' or 'no' followed by one short reason, "
         "one per line, in order. Be strict and literal.\n" + "\n".join(f"{i+1}. {text}" for i, (_, text) in enumerate(checks)))
    payload = {"model": MODEL, "stream": False, "think": False,
               "messages": [{"role": "user", "content": q, "images": images}],
               "options": {"num_predict": 500, "temperature": 0.1}}
    req = urllib.request.Request(f"http://{HOST}/api/chat", data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    r = json.load(urllib.request.urlopen(req, timeout=timeout))
    return r["message"]["content"]


def qa(skeleton: Path, card: Path, timeout: int = 300) -> dict:
    """Two passes: the card alone for the geometry-class checks (tee box, fairway/green, trees), then
    skeleton+card for the 'matches the map' checks (water, bunkers). Asking about the card alone proved
    stricter than asking 'does image 2 match image 1'."""
    t0 = time.time()
    solo = [c for c in CHECKS if c[0] in ("teeBox", "fairwayStopsShortOfGreen", "noTreeOnFairway", "noTreeOnGreen")]
    pair = [c for c in CHECKS if c[0] in ("waterMatches", "bunkersMatch")]
    try:
        text1 = _ask([_b64(card)], [(k, v.replace("Looking at both images: ", "")) for k, v in solo], timeout)
        text2 = _ask([_b64(skeleton), _b64(card)], [(k, "Image 1 is the map (truth), image 2 the rendering. " + v) for k, v in pair], timeout)
    except Exception as exc:
        return {"available": False, "error": str(exc)[:200]}
    text = text1 + "\n---\n" + text2
    flags = {}
    for checks_, txt in ((solo, text1), (pair, text2)):
        lines = [l.strip() for l in txt.splitlines() if l.strip()]
        for i, (key, _) in enumerate(checks_):
            line = next((l for l in lines if l.lstrip("*- ").startswith(f"{i+1}")), "")
            low = line.lower()
            body = low.split(".", 1)[-1].strip() if "." in low[:3] else low
            verdict = "yes" if body.startswith("yes") else ("no" if body.startswith("no") else ("yes" if " yes" in body[:8] else "?"))
            flags[key] = {"ok": verdict == "yes", "answer": line[:160]}
    issues = [k for k, v in flags.items() if not v["ok"]]
    return {"available": True, "seconds": round(time.time() - t0, 1), "flags": flags, "issues": issues, "pass": not issues, "raw": text[:1500]}


def _unused(skeleton, card, timeout=300):
    lines = []
    flags = {}
    for i, (key, _) in enumerate(CHECKS):
        line = next((l for l in lines if l.lstrip("*- ").startswith(f"{i+1}")), "")
        low = line.lower()
        verdict = "yes" if ("yes" in low and "no" not in low.split("yes")[0][-4:]) or low.split(".", 1)[-1].strip().startswith("yes") else ("no" if "no" in low else "?")
        flags[key] = {"ok": verdict == "yes", "answer": line[:160]}
    issues = [k for k, v in flags.items() if not v["ok"]]
    return {"available": True, "seconds": round(time.time() - t0, 1), "flags": flags, "issues": issues, "pass": not issues, "raw": text[:1200]}

if __name__ == "__main__":
    import sys
    print(json.dumps(qa(Path(sys.argv[1]), Path(sys.argv[2])), indent=1)[:2000])
