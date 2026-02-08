"""
Test script for CyneDirector AI pipeline.
Verifies device detection, model loading, and basic inference
without needing any video files.

Usage:
    python test_device_detection.py
"""

import sys
import time
import torch
import numpy as np
from PIL import Image

# ── Helpers ──────────────────────────────────────────────────────────────────

PASS = "[PASS]"
FAIL = "[FAIL]"
SKIP = "[SKIP]"

results = []


def section(title):
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def record(name, passed, detail=""):
    tag = PASS if passed else FAIL
    results.append((name, passed, detail))
    line = f"  {tag} {name}"
    if detail:
        line += f" — {detail}"
    print(line)


def make_test_image(width=384, height=384):
    """Create a synthetic test image (gradient with a rectangle)."""
    arr = np.zeros((height, width, 3), dtype=np.uint8)
    # Horizontal blue gradient
    arr[:, :, 2] = np.linspace(0, 255, width, dtype=np.uint8)
    # Green rectangle in the centre (gives CLIP something to describe)
    h4, w4 = height // 4, width // 4
    arr[h4:h4 * 3, w4:w4 * 3, 1] = 200
    return Image.fromarray(arr)


# ── 1. Device Detection ─────────────────────────────────────────────────────

section("1. Device Detection")

print(f"  PyTorch version : {torch.__version__}")
print(f"  CUDA available  : {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"  CUDA device     : {torch.cuda.get_device_name(0)}")
    major, minor = torch.cuda.get_device_capability(0)
    print(f"  Compute cap.    : {major}.{minor}")
    print(f"  VRAM            : {torch.cuda.get_device_properties(0).total_mem / 1024**3:.1f} GB")

has_mps = hasattr(torch.backends, "mps") and torch.backends.mps.is_available()
print(f"  MPS available   : {has_mps}")

try:
    from core.ai_models import AIBackend
    ai = AIBackend()
    device = ai.device
    dtype = ai.dtype
    record("AIBackend initialised", True, f"device={device}, dtype={dtype}")
except Exception as e:
    record("AIBackend initialised", False, str(e))
    print("\nCannot continue without AIBackend. Exiting.")
    sys.exit(1)

# Verify device selection logic
if torch.cuda.is_available():
    expected = "cuda"
elif has_mps:
    expected = "mps"
else:
    expected = "cpu"
record("Device matches expected", device == expected,
       f"expected={expected}, got={device}")

# Verify dtype follows device
if device == "cuda":
    record("CUDA uses float16", dtype == torch.float16)
else:
    record(f"{device.upper()} uses float32", dtype == torch.float32)

# ── 2. Whisper Params ───────────────────────────────────────────────────────

section("2. Whisper Device Params")

try:
    acc_name, acc_dev, acc_ct = ai.get_whisper_params("accuracy")
    spd_name, spd_dev, spd_ct = ai.get_whisper_params("speed")

    record("Accuracy params", True, f"model={acc_name}, device={acc_dev}, compute={acc_ct}")
    record("Speed params", True, f"model={spd_name}, device={spd_dev}, compute={spd_ct}")

    if device == "cuda":
        record("CUDA accuracy uses large-v3 + float16",
               acc_name == "large-v3" and acc_ct == "float16")
        record("CUDA speed uses medium + float16",
               spd_name == "medium" and spd_ct == "float16")
    else:
        record(f"{device.upper()} accuracy uses large-v3 + int8",
               acc_name == "large-v3" and acc_ct == "int8")
        record(f"{device.upper()} speed uses small + int8",
               spd_name == "small" and spd_ct == "int8")
except Exception as e:
    record("get_whisper_params", False, str(e))

# ── 3. CLIP Loading & Inference ─────────────────────────────────────────────

section("3. CLIP Model")

clip_ok = False
try:
    t0 = time.time()
    clip_model, clip_processor = ai.load_clip()
    elapsed = time.time() - t0
    record("CLIP loaded", True, f"{elapsed:.1f}s")

    # Test image inference
    test_img = make_test_image()
    inputs = clip_processor(images=test_img, return_tensors="pt", padding=True).to(device)
    with torch.no_grad():
        features = clip_model.get_image_features(**inputs)
        features /= features.norm(p=2, dim=-1, keepdim=True)

    embedding = features.cpu().numpy()[0]
    record("CLIP image inference", True,
           f"embedding shape={embedding.shape}, norm={np.linalg.norm(embedding):.4f}")

    # Test text inference
    texts = ["a green rectangle", "a photo of a dog", "a blue gradient"]
    text_inputs = clip_processor(text=texts, return_tensors="pt", padding=True).to(device)
    with torch.no_grad():
        text_features = clip_model.get_text_features(**text_inputs)
        text_features /= text_features.norm(p=2, dim=-1, keepdim=True)
        similarities = (features @ text_features.T).cpu().numpy()[0]

    best_idx = int(np.argmax(similarities))
    print(f"    Similarities: {dict(zip(texts, [f'{s:.3f}' for s in similarities]))}")
    record("CLIP text matching", True, f"best match: \"{texts[best_idx]}\" ({similarities[best_idx]:.3f})")
    clip_ok = True

except Exception as e:
    record("CLIP", False, str(e))

# ── 4. BLIP-2 Loading & Inference ───────────────────────────────────────────

section("4. BLIP-2 Model")

try:
    t0 = time.time()
    blip_model, blip_processor = ai.load_blip()
    elapsed = time.time() - t0
    record("BLIP-2 loaded", True, f"{elapsed:.1f}s")

    # Test caption generation
    test_img = make_test_image()
    inputs = blip_processor(images=test_img, text="a photo of", return_tensors="pt").to(device)

    # Verify half() only on CUDA
    if device == "cuda" and ai.dtype == torch.float16:
        inputs["pixel_values"] = inputs["pixel_values"].half()
        record("pixel_values converted to half (CUDA)", True)
    else:
        record(f"pixel_values kept as float32 ({device})", True,
               f"dtype={inputs['pixel_values'].dtype}")

    with torch.no_grad():
        out_ids = blip_model.generate(**inputs, max_new_tokens=30)
        caption = blip_processor.batch_decode(out_ids, skip_special_tokens=True)[0].strip()

    record("BLIP-2 caption generated", bool(caption), f"\"{caption}\"")

except Exception as e:
    record("BLIP-2", False, str(e))

# ── 5. Whisper Loading ──────────────────────────────────────────────────────

section("5. Whisper Model")

try:
    t0 = time.time()
    whisper_model = ai.load_whisper()
    elapsed = time.time() - t0
    record("Whisper loaded", True, f"{elapsed:.1f}s")

    # We can't do a real transcription without an audio file, but verify
    # the model object exists and has the expected interface.
    has_transcribe = hasattr(whisper_model, "transcribe")
    record("Whisper has transcribe()", has_transcribe)

except Exception as e:
    record("Whisper", False, str(e))

# ── 6. Performance Module ──────────────────────────────────────────────────

section("6. Performance / Batch Sizing")

try:
    from core.performance import get_optimal_batch_size, get_available_memory_mb

    ram_mb = get_available_memory_mb()
    record("RAM detection", True, f"{ram_mb:.0f} MB available")

    for dev in ["cuda", "mps", "cpu"]:
        bs = get_optimal_batch_size(base_batch_size=64, min_batch=16, max_batch=128, device=dev)
        record(f"Batch size (device={dev})", True, f"{bs}")

except Exception as e:
    record("Performance module", False, str(e))

# ── 7. Cleanup ──────────────────────────────────────────────────────────────

section("7. Cleanup")

try:
    ai.unload_models()
    record("Models unloaded", True)
except Exception as e:
    record("unload_models", False, str(e))

# ── Summary ─────────────────────────────────────────────────────────────────

section("Summary")

passed = sum(1 for _, ok, _ in results if ok)
failed = sum(1 for _, ok, _ in results if not ok)
total = len(results)

print(f"\n  {passed}/{total} checks passed, {failed} failed\n")

if failed:
    print("  Failed checks:")
    for name, ok, detail in results:
        if not ok:
            print(f"    - {name}: {detail}")
    print()

sys.exit(1 if failed else 0)
