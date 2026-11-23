"""Exercise cached AI models without downloads: python -m tests.cached_ai_smoke."""
import os
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
import main  # Windows DLL bootstrap
import faulthandler
from unittest.mock import patch
import numpy as np
from PIL import Image
import torch
from core.ai_models import AIBackend
from core.clip_features import as_clip_tensor


def run():
    faulthandler.dump_traceback_later(180, exit=True)
    ai = AIBackend()
    print(f"Runtime: torch={torch.__version__}, device={ai.device}, GPU={torch.cuda.get_device_name(0)}", flush=True)
    assert ai.device == "cuda", "This machine should use its RTX 5070"
    assert os.environ.get("TORCH_CUDA_ARCH_LIST") == "12.0"
    # A short vocabulary exercises the same loading path without rebuilding
    # the full 13,182-tag bank during a smoke check.
    with patch("core.tags.get_tag_bank", return_value=["wedding", "bride", "groom", "flowers"]):
        model, processor = ai.load_clip()
    assert model is not None and processor is not None
    image = Image.new("RGB", (384, 384), (220, 30, 30))
    with torch.no_grad():
        image_features = as_clip_tensor(model.get_image_features(
            **processor(images=image, return_tensors="pt").to(ai.device)))
        text_features = as_clip_tensor(model.get_text_features(
            **processor(text=["wedding vows " * 100], padding=True, truncation=True,
                        max_length=77, return_tensors="pt").to(ai.device)))
    assert image_features.shape == text_features.shape == (1, 768)
    assert torch.isfinite(image_features).all() and torch.isfinite(text_features).all()
    assert ai.tag_embeddings.shape == (4, 768)
    print("Cached CLIP image/text inference and long transcript input: passed", flush=True)
    ai.unload_models()

    model, processor = ai.load_blip()
    assert model is not None and processor is not None
    inputs = processor(images=image, text="a photo of", return_tensors="pt").to(ai.device)
    if ai.dtype == torch.float16:
        inputs["pixel_values"] = inputs["pixel_values"].half()
    with torch.no_grad():
        output = model.generate(**inputs, max_new_tokens=8)
    caption = processor.batch_decode(output, skip_special_tokens=True)[0]
    assert caption.strip()
    print(f"Cached BLIP caption inference: passed ({caption})", flush=True)
    ai.unload_models()

    model = ai.load_whisper()
    segments, info = model.transcribe(np.zeros(16000, dtype=np.float32), language="en",
                                      beam_size=1, vad_filter=False)
    list(segments)
    print("Cached Whisper audio inference: passed", flush=True)
    ai.unload_models()
    faulthandler.cancel_dump_traceback_later()


if __name__ == "__main__":
    run()
