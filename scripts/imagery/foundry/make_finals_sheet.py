"""Contact sheet of all finished cards (final/hole-NN.png) with their gate verdicts, 6 per row."""
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
f = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 20)
fs = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 15)
W, H, pad, lab, cols = 300, 400, 10, 48, 6
rows = 3
sheet = Image.new("RGB", (pad + cols * (W + pad), 44 + rows * (H + lab + pad)), "#14261c")
d = ImageDraw.Draw(sheet)
d.text((pad, 10), "Peach Tree — all 18 finished cards (skeleton > gpt-image-2 > snap > gate). Number = worst land tile vs skeleton, yards.", fill="#efe7d2", font=f)
n_pass = 0
for h in range(1, 19):
    r, c = divmod(h - 1, cols)
    x = pad + c * (W + pad)
    y = 44 + r * (H + lab + pad)
    p = HERE / "final" / f"hole-{h:02d}.png"
    j = HERE / "final" / f"hole-{h:02d}.json"
    if p.exists() and j.exists():
        m = json.loads(j.read_text())
        s = m["best"]["vsSkeleton150"]
        ok = m["pass"]
        n_pass += ok
        d.text((x, y + 4), f"Hole {h}", fill="#efe7d2", font=f)
        d.text((x, y + 28), f"{s['landMaxYards']:.2f} yd max · {s['landMedianYards']:.2f} med · {'PASS' if ok else 'FAIL'}", fill="#9fe29f" if ok else "#ff9d8c", font=fs)
        sheet.paste(Image.open(p).convert("RGB").resize((W, H), Image.LANCZOS), (x, y + lab))
    else:
        d.text((x, y + 4), f"Hole {h} — not rendered", fill="#8a9a8b", font=f)
out = HERE / "sheets" / "all-18-finals.jpg"
sheet.save(out, quality=88)
print("saved", out, "pass:", n_pass)
