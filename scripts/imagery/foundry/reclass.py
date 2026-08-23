"""Annotate every sidecar in a directory with the class-aware drift (land vs water)."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from measure_drift_classed import measure_classed
d = Path(sys.argv[1]); hole = int(sys.argv[2]); classes = Path(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3] != "-" else Path(f"cond/hole-{hole:02d}-classes.png")
base = Path(sys.argv[4]) if len(sys.argv) > 4 else None
for js in sorted(d.glob(f"hole-{hole:02d}-styled-*.json")):
    png = js.with_suffix(".png")
    if not png.exists(): continue
    meta = json.loads(js.read_text())
    meta["driftClassed"] = measure_classed(hole, png, classes, 150)
    if base is not None:
        meta["driftVsSkeleton"] = measure_classed(hole, png, classes, 150, reference=base)
    js.write_text(json.dumps(meta, indent=2, default=float) + "\n")
    c = meta["driftClassed"]
    s = meta.get("driftVsSkeleton")
    extra = f" | vs skeleton land max {s['landMaxYards']:.2f} med {s['landMedianYards']:.2f}" if s else ""
    print(f"{png.name[-70:]}: land max {c['landMaxYards']:.2f} med {c['landMedianYards']:.2f} {'PASS' if c['pass'] else 'FAIL'} | water {c['tilesWater']} tiles up to {c['waterMaxYards']:.2f}{extra}")
