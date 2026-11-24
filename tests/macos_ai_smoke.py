"""Core real-model inference on synthetic images and locally synthesized speech.

Uses the application's loaders and configured repository cache. Only small
fixtures are generated; no wedding footage or external translation APIs are used.
Model download is intentional; use --offline for subsequent cached checks.
"""
import argparse
import gc
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--only", choices=["clip", "blip", "yolo", "whisper", "faces", "all"], default="all")
    args = parser.parse_args()
    if args.offline:
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
    import torch
    from PIL import Image, ImageDraw
    from core.ai_models import AIBackend
    from core.clip_features import as_clip_tensor
    import config
    output = Path(os.environ.get("CYNE_TEST_OUTPUT", ".cache/mac-verification")).resolve()
    output.mkdir(parents=True, exist_ok=True)
    ai = AIBackend()
    report = {"torch": torch.__version__, "device": ai.device,
              "mps_available": torch.backends.mps.is_available(), "checks": {}}
    report_path = output / "inference.json"
    if report_path.exists():
        report["checks"].update(json.loads(report_path.read_text()).get("checks", {}))

    def record(name, data, started):
        report["checks"][name] = dict(data, elapsed_seconds=round(time.monotonic()-started, 2))
        report_path.write_text(json.dumps(report, indent=2) + "\n")
        print(name, json.dumps(report["checks"][name]), flush=True)
        ai.unload_models()
        gc.collect()

    def capacity():
        free = shutil.disk_usage(output).free / 1024**3
        if free < 5:
            raise RuntimeError(f"Only {free:.1f} GiB free; stop before another model download")

    image = Image.new("RGB", (384, 384), "white")
    ImageDraw.Draw(image).rectangle((64, 64, 320, 320), fill="red")
    image.save(output / "synthetic-image.png")

    if args.only in ("faces", "all"):
        started = time.monotonic()
        import numpy as np
        import face_recognition
        locations = face_recognition.face_locations(np.zeros((128, 128, 3), dtype=np.uint8), model="hog")
        assert locations == []
        record("faces", {"backend": "dlib HOG / CPU", "blank_fixture_detections": locations}, started)

    if args.only in ("clip", "all"):
        capacity(); started = time.monotonic()
        model, processor = ai.load_clip()  # Real full application vocabulary.
        with torch.inference_mode():
            visual = as_clip_tensor(model.get_image_features(**processor(images=image, return_tensors="pt").to(ai.device)))
            text = as_clip_tensor(model.get_text_features(**processor(text=["a red square", "a blue square"],
                padding=True, truncation=True, max_length=77, return_tensors="pt").to(ai.device)))
        assert visual.shape == (1, 768) and text.shape == (2, 768)
        assert torch.isfinite(visual).all() and torch.isfinite(text).all()
        scores = torch.nn.functional.cosine_similarity(visual, text).tolist()
        assert scores[0] > scores[1], scores
        assert visual.device.type == ai.device
        record("clip", {"visual_shape": list(visual.shape), "text_shape": list(text.shape),
            "tag_count": ai.tag_embeddings.shape[0], "similarities_red_blue": scores,
            "tensor_device": str(visual.device)}, started)

    if args.only in ("blip", "all"):
        capacity(); started = time.monotonic()
        model, processor = ai.load_blip()
        inputs = processor(images=image, text="a photo of", return_tensors="pt").to(ai.device)
        with torch.inference_mode():
            ids = model.generate(**inputs, max_new_tokens=20, do_sample=False)
        caption = processor.batch_decode(ids, skip_special_tokens=True)[0]
        assert caption.strip()
        model_device = next(model.parameters()).device
        assert model_device.type == ai.device
        record("blip", {"caption": caption, "model_device": str(model_device)}, started)

    if args.only in ("yolo", "all"):
        capacity(); started = time.monotonic()
        from ultralytics.utils import ASSETS
        model = ai.load_yolo()
        results = model(str(ASSETS / "bus.jpg"), verbose=False)
        labels = [result.names[int(box.cls[0])] for result in results for box in result.boxes]
        assert "bus" in labels and "person" in labels, labels
        model_device = next(model.model.parameters()).device
        assert model_device.type == ai.device
        record("yolo", {"fixture": "ultralytics packaged bus.jpg", "labels": labels,
            "model_device": str(model_device), "result_device": str(results[0].boxes.data.device)}, started)

    if args.only in ("whisper", "all"):
        capacity(); started = time.monotonic()
        # A disposable project selects small; it does not alter a user's settings.
        with tempfile.TemporaryDirectory(prefix="cyne-speech-") as tmp:
            config.load_project_settings(tmp)
            config._settings.set("whisper_model", "small")
            speech, wav = str(Path(tmp)/"speech.aiff"), str(Path(tmp)/"speech.wav")
            subprocess.run(["say", "-o", speech, "On our wedding day, I promise to stand by your side."], check=True, timeout=60)
            subprocess.run(["ffmpeg", "-v", "error", "-i", speech, "-ar", "16000", "-ac", "1", wav], check=True, timeout=60)
            model = ai.load_whisper()
            segments, info = model.transcribe(wav, language="en", beam_size=5, vad_filter=False)
            segments = list(segments)
            transcript = " ".join(s.text.strip() for s in segments)
            assert "wedding" in transcript.lower() and "promise" in transcript.lower(), transcript
            assert all(0 <= s.start < s.end for s in segments)
            record("whisper", {"model": "small", "backend": ai.get_whisper_params()[1:],
                "transcript": transcript, "segments": [{"start": s.start, "end": s.end} for s in segments]}, started)
    print("Real inference checks completed", flush=True)


if __name__ == "__main__":
    run()
