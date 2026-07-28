"""Repaint a hole card without moving anything on it.

The illustrated cards this replaces were made by free-form image generation:
the model was shown a hole and asked for a prettier one, so it drew a new hole.
Measured against their own aerials they sit up to 38 yards out, which is why no
yardage can be read off them.

This does the opposite. The real aerial is fed in as both the starting image
and a ControlNet conditioning signal, and the denoise strength — the one dial
that matters — decides how far the model may depart from it. Low strength
repaints texture and light while fairway edges, bunker lips, tree trunks, and
cart paths stay where they are. Push it too far and the model starts inventing,
which is exactly the failure being measured for.

Nothing here is authoritative course data. It is a repaint of a 2022 aerial,
and `measure_drift.py` is what decides whether it earned the right to carry a
number.

Runs entirely locally. No hosted API, no gated checkpoint, no token.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import torch
from diffusers import (
    ControlNetModel,
    StableDiffusionXLControlNetImg2ImgPipeline,
)
from PIL import Image

# SDXL wants its dimensions on a 64-pixel grid, and the card is 900x1200 — 900
# is not even a multiple of 8. Working at 960x1280 keeps the card's exact 3:4
# ratio, so the trip out and back is a uniform scale and introduces no
# geometric distortion of its own. Anything with a different aspect would
# stretch one axis and register as drift that the model never caused.
WORK_SIZE = (960, 1280)
CARD_SIZE = (900, 1200)

BASE_MODEL = "stabilityai/stable-diffusion-xl-base-1.0"
# Ungated. Tile conditioning holds local structure while allowing a repaint,
# which is the behaviour wanted here; canny would pin edges harder but throws
# away everything between them.
CONTROLNET_MODEL = "xinsir/controlnet-tile-sdxl-1.0"

PROMPT = (
    "aerial photograph of a golf hole at a private country club, "
    "manicured fairway and rough, mown grass banding, bunkers with clean sand, "
    "mature valley oak canopies casting soft shadows, golden hour light, "
    "rich natural colour, crisp detail, photographic, top-down"
)
NEGATIVE_PROMPT = (
    "illustration, cartoon, painting, cgi render, map, diagram, text, labels, "
    "watermark, buildings added, roads added, distorted, warped, blurry"
)

# The "photo" style above asks for a photograph and its negative prompt bans
# painterly output — which is why the locked set reads as an enhanced aerial.
# "painted" asks for the premium yardage-book look instead and stops banning
# it; whether any grip setting keeps that pretty AND under the 5-yard bar is
# exactly what a sweep has to answer.
PAINTED_PROMPT = (
    "premium hand-painted yardage book illustration of a golf hole, aerial "
    "view, stylized manicured fairway and green with elegant mow lines, "
    "painterly valley oak canopies with soft depth, clean sculpted sand "
    "bunkers, warm golden hour glow, rich saturated colour, refined detail, "
    "top-down"
)
PAINTED_NEGATIVE_PROMPT = (
    "photograph, satellite image, map, diagram, text, labels, watermark, "
    "buildings added, roads added, distorted, warped, blurry"
)

STYLES = {
    "photo": (PROMPT, NEGATIVE_PROMPT),
    "painted": (PAINTED_PROMPT, PAINTED_NEGATIVE_PROMPT),
}


def load_pipeline(controlnet_model: str, cache_dir: Path, low_vram: bool = False):
    controlnet = ControlNetModel.from_pretrained(
        controlnet_model, torch_dtype=torch.float16, cache_dir=cache_dir
    )
    pipeline = StableDiffusionXLControlNetImg2ImgPipeline.from_pretrained(
        BASE_MODEL,
        controlnet=controlnet,
        torch_dtype=torch.float16,
        variant="fp16",
        use_safetensors=True,
        cache_dir=cache_dir,
    )
    if low_vram:
        # Resident SDXL + ControlNet at this size runs at the very edge of the
        # 12 GB card, which is fine on an idle machine and pathological on a
        # busy one: any other VRAM user tips the driver into system-memory
        # fallback, and a 73-second card becomes a 30-minute stall
        # (2026-07-27, twice). Offloading holds each submodel on the GPU only
        # while it runs — a few times slower than resident weights, immune to
        # sharing the card with a desktop session. Same seeds, same outputs:
        # the math still happens on CUDA.
        pipeline.enable_model_cpu_offload()
    else:
        pipeline.to("cuda")
    # 12 GB is enough for SDXL plus a ControlNet at this size only with the VAE
    # working in slices; without this it peaks during decode. Called on the VAE
    # directly — the pipeline-level helpers are removed in diffusers 0.40.
    pipeline.vae.enable_tiling()
    pipeline.vae.enable_slicing()
    pipeline.set_progress_bar_config(disable=True)
    return pipeline


def generate(
    pipeline,
    aerial: Image.Image,
    strength: float,
    seed: int,
    steps: int,
    guidance: float,
    controlnet_scale: float,
    prompt: str = PROMPT,
    negative_prompt: str = NEGATIVE_PROMPT,
    work_scale: int = 1,
) -> Image.Image:
    # work_scale > 1 runs the diffusion at a multiple of WORK_SIZE so the
    # model synthesizes finer texture than the 0.6 m NAIP source carries. The
    # output card scales by the same factor: the extra pixels are the point.
    # Invented detail is only plausible, so scaled cards must re-earn their
    # drift pass before shipping.
    work_size = (WORK_SIZE[0] * work_scale, WORK_SIZE[1] * work_scale)
    card_size = (CARD_SIZE[0] * work_scale, CARD_SIZE[1] * work_scale)
    conditioning = aerial.resize(work_size, Image.LANCZOS)
    generator = torch.Generator(device="cuda").manual_seed(seed)

    result = pipeline(
        prompt=prompt,
        negative_prompt=negative_prompt,
        image=conditioning,
        control_image=conditioning,
        strength=strength,
        num_inference_steps=steps,
        guidance_scale=guidance,
        controlnet_conditioning_scale=controlnet_scale,
        generator=generator,
    ).images[0]

    return result.resize(card_size, Image.LANCZOS)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hole", type=int, required=True)
    parser.add_argument(
        "--aerial",
        type=Path,
        help="source aerial card; defaults to the repo's hole-NN.webp",
    )
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="output directory — must be outside the repo",
    )
    parser.add_argument(
        "--strength",
        type=float,
        nargs="+",
        default=[0.25, 0.35, 0.45],
        help="denoise strengths to sweep; higher is more painterly and less faithful",
    )
    parser.add_argument("--seed", type=int, default=20260726)
    parser.add_argument("--steps", type=int, default=30)
    parser.add_argument("--guidance", type=float, default=5.0)
    parser.add_argument(
        "--controlnet-scale",
        type=float,
        nargs="+",
        default=[0.9],
        help=(
            "ControlNet conditioning scale(s). This, not denoise strength, is "
            "the dial that decides how painterly the result may become: at 0.9 "
            "the aerial dominates and strength barely matters. Every "
            "combination of strength and scale is generated."
        ),
    )
    parser.add_argument("--controlnet", type=str, default=CONTROLNET_MODEL)
    parser.add_argument(
        "--style",
        choices=sorted(STYLES),
        default="photo",
        help=(
            "prompt family: 'photo' is the shipped enhanced-aerial look; "
            "'painted' asks for the yardage-book art style and appends the "
            "style to output filenames so nothing overwrites the photo set"
        ),
    )
    parser.add_argument(
        "--work-scale",
        type=int,
        default=1,
        choices=[1, 2],
        help=(
            "run the diffusion at this multiple of the base 960x1280 working "
            "size and emit a card scaled to match; 2 makes the model invent "
            "fine texture the 0.6 m aerial cannot supply, at ~4x the compute "
            "and VRAM — pair with --low-vram on the 12 GB card"
        ),
    )
    parser.add_argument(
        "--low-vram",
        action="store_true",
        help=(
            "offload submodels to CPU between uses so the run coexists with "
            "a busy desktop session instead of thrashing at the 12 GB edge"
        ),
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path("C:/Users/mc516/Documents/Aries Radar/peach-tree-imagery/hf-cache"),
    )
    args = parser.parse_args()

    aerial_path = args.aerial or Path(
        f"public/course/peach-tree/hole-{args.hole:02d}.webp"
    )
    aerial = Image.open(aerial_path).convert("RGB")
    args.out.mkdir(parents=True, exist_ok=True)

    print(f"Loading {args.controlnet} and SDXL into {args.cache_dir} ...")
    pipeline = load_pipeline(args.controlnet, args.cache_dir, low_vram=args.low_vram)

    combinations = [
        (strength, scale) for scale in args.controlnet_scale for strength in args.strength
    ]

    prompt, negative_prompt = STYLES[args.style]
    for strength, controlnet_scale in combinations:
        started = time.time()
        image = generate(
            pipeline,
            aerial,
            strength=strength,
            seed=args.seed,
            steps=args.steps,
            guidance=args.guidance,
            controlnet_scale=controlnet_scale,
            prompt=prompt,
            negative_prompt=negative_prompt,
            work_scale=args.work_scale,
        )
        style_tag = "" if args.style == "photo" else f"-{args.style}"
        scale_tag = "" if args.work_scale == 1 else f"-x{args.work_scale}"
        stem = (
            f"hole-{args.hole:02d}-locked"
            f"-s{strength:.2f}-c{controlnet_scale:.2f}{style_tag}{scale_tag}"
        ).replace(".", "_")
        image_path = args.out / f"{stem}.png"
        image.save(image_path)

        # Written beside every image: an image whose settings are unknown
        # cannot be reproduced, and an unreproducible result is not evidence.
        (args.out / f"{stem}.json").write_text(
            json.dumps(
                {
                    "hole": args.hole,
                    "aerial": str(aerial_path),
                    "baseModel": BASE_MODEL,
                    "controlnet": args.controlnet,
                    "strength": strength,
                    "seed": args.seed,
                    "steps": args.steps,
                    "guidance": args.guidance,
                    "controlnetConditioningScale": controlnet_scale,
                    "workSize": [d * args.work_scale for d in WORK_SIZE],
                    "cardSize": [d * args.work_scale for d in CARD_SIZE],
                    "workScale": args.work_scale,
                    "style": args.style,
                    "prompt": prompt,
                    "negativePrompt": negative_prompt,
                    "torch": torch.__version__,
                    "lowVram": args.low_vram,
                    "secondsTaken": round(time.time() - started, 1),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        # ASCII only: the Windows console runs cp1252 and a stray arrow here
        # crashes the run after the image is already on disk.
        # ASCII only: the Windows console runs cp1252 and a stray arrow here
        # crashes the run after the image is already on disk.
        print(
            f"  strength {strength:.2f} control {controlnet_scale:.2f} "
            f"-> {image_path.name} ({time.time() - started:.0f}s)"
        )


if __name__ == "__main__":
    main()
