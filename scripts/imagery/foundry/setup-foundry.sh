#!/bin/zsh
# Foundry imagery environment for the Peach Tree hole-card pipeline (SDXL + ControlNet tile + IP-Adapter on MPS).
set -e
WORK=~/rex/peach-tree-imagery
cd $WORK
export HF_HOME=$WORK/hf-cache
export HF_HUB_DISABLE_TELEMETRY=1
echo "[$(date '+%H:%M:%S')] creating venv"
[ -d .venv ] || uv venv --python 3.12 .venv
echo "[$(date '+%H:%M:%S')] installing packages"
uv pip install --python .venv/bin/python torch torchvision diffusers transformers accelerate safetensors huggingface_hub Pillow numpy scipy opencv-python-headless sentencepiece protobuf
.venv/bin/python -c "import torch, diffusers, transformers; print('torch', torch.__version__, 'mps', torch.backends.mps.is_available(), '| diffusers', diffusers.__version__, '| transformers', transformers.__version__)"
echo "[$(date '+%H:%M:%S')] downloading models into $HF_HOME"
.venv/bin/python - <<'PY'
import time
from huggingface_hub import snapshot_download
jobs = [
  ("stabilityai/stable-diffusion-xl-base-1.0", ["*.json","*.txt","tokenizer/*","tokenizer_2/*","scheduler/*",
      "text_encoder/model.fp16.safetensors","text_encoder_2/model.fp16.safetensors",
      "unet/diffusion_pytorch_model.fp16.safetensors","vae/diffusion_pytorch_model.fp16.safetensors"]),
  ("madebyollin/sdxl-vae-fp16-fix", ["*.json","diffusion_pytorch_model.safetensors"]),
  ("xinsir/controlnet-tile-sdxl-1.0", ["*.json","diffusion_pytorch_model.safetensors"]),
  ("h94/IP-Adapter", ["sdxl_models/ip-adapter_sdxl_vit-h.safetensors","sdxl_models/ip-adapter-plus_sdxl_vit-h.safetensors","models/image_encoder/*"]),
]
for repo, pats in jobs:
    t=time.time(); p=snapshot_download(repo, allow_patterns=pats); print(f"  {repo} -> {p} ({time.time()-t:.0f}s)", flush=True)
PY
echo "[$(date '+%H:%M:%S')] cache size:"; du -sh $HF_HOME
echo "[$(date '+%H:%M:%S')] SETUP DONE"
