"""Decode one bounded PCM window at a time; keep clip-relative source times."""
import math
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import wave

from core.memory_budget import MemoryBudgetExceeded
from core.workspace import Workspace, probe


def decode_window(source, target, start, duration, allowed):
    command = ["ffmpeg", "-nostdin", "-v", "error", "-y", "-ss", str(start), "-i", str(source),
               "-map", "0:a:0", "-vn", "-af", f"aresample=16000:async=1:first_pts=0,apad=whole_dur={duration}",
               "-t", str(duration), "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(target)]
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=errors)
        try:
            while process.poll() is None:
                if not allowed():
                    raise RuntimeError("Speech decoding cancelled")
                try:
                    process.wait(timeout=.25)
                except subprocess.TimeoutExpired:
                    pass
            if process.returncode:
                errors.seek(0)
                raise RuntimeError("Speech window decode failed: " + errors.read(2048).decode(errors="replace"))
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait()
    with wave.open(str(target), "rb") as pcm:
        if pcm.getnchannels() != 1 or pcm.getframerate() != 16000 or pcm.getsampwidth() != 2:
            raise MemoryBudgetExceeded("Unexpected speech decode format")
        if pcm.getnframes() > math.ceil(duration * 16000) + 32:
            raise MemoryBudgetExceeded("Decoded PCM exceeds the requested window")
        return pcm.getnframes() * 2


def bounded_transcribe(model, source, project, generation, policy, kwargs, allowed=lambda: True,
                       *, probe_fn=probe, decode_fn=decode_window, temporary_parent=None):
    """Return a closeable segment generator and incrementally populated info.

    Windows overlap by two seconds. Word midpoints choose the owning core window;
    word timestamps, not equal splitting, trim crossing segments. Recognition at
    joins still needs real-language acceptance and can vary with model context.
    """
    from core.source_state import media_path
    source=media_path(source)
    metadata = probe_fn(source)
    duration = metadata["duration"]
    if not any(s.get("codec_type") == "audio" for s in metadata["streams"]):
        raise ValueError("No audio stream for transcription")
    parent = Path(temporary_parent) if temporary_parent else Workspace.load(project).artifact_dir("temporary", generation)
    info = SimpleNamespace(language=None, languages=set(), duration=duration,
        bounded_stats={"chunks": 0, "max_pcm_bytes": 0, "core_seconds": policy.speech_seconds,
                       "overlap_seconds": 2, "timestamps": "source-relative, word-midpoint ownership"})
    options = dict(kwargs, word_timestamps=True)

    def windows():
        for number in range(math.ceil(duration / policy.speech_seconds)):
            if not allowed():
                raise RuntimeError("Transcription cancelled")
            core_start = number * policy.speech_seconds
            core_end = min(duration, core_start + policy.speech_seconds)
            start, end = max(0, core_start-2), min(duration, core_end+2)
            with tempfile.TemporaryDirectory(prefix="speech-", dir=parent) as tmp:
                target = Path(tmp) / "audio.wav"
                if temporary_parent is None:
                    from core.retention import register_artifact
                    register_artifact(project, generation, target, "temporary")
                size = decode_fn(source, target, start, end-start, allowed)
                info.bounded_stats["chunks"] += 1
                info.bounded_stats["max_pcm_bytes"] = max(info.bounded_stats["max_pcm_bytes"], size)
                segments, detected = model.transcribe(str(target), **options)
                language = getattr(detected, "language", None)
                if language:
                    if len(language)>32 or len(info.languages)>128:
                        raise MemoryBudgetExceeded("Detected-language set exceeds bounded metadata")
                    info.language = info.language or language
                    info.languages.add(language)
                try:
                    for segment in segments:
                        if not allowed():
                            raise RuntimeError("Transcription cancelled")
                        text = segment.text.strip()
                        if not text:
                            continue
                        first, last = segment.start+start, segment.end+start
                        if not (math.isfinite(first) and math.isfinite(last) and 0 <= first < last <= duration+.1):
                            raise ValueError("Invalid speech timestamp from model")
                        words = getattr(segment, "words", None)
                        if words and len(words)>4096:
                            raise MemoryBudgetExceeded("One speech segment exceeds the word buffer limit")
                        if words and any(not math.isfinite(w.start) or not math.isfinite(w.end) or w.start<0 or w.end<w.start or w.end>end-start+.1 for w in words):
                            raise ValueError("Invalid word timestamp from model")
                        if duration > policy.speech_seconds and words:
                            selected = [w for w in words if core_start <= (w.start+w.end)/2+start < core_end]
                            if not selected:
                                continue
                            first, last = selected[0].start+start, selected[-1].end+start
                            text = "".join(w.word for w in selected).strip()
                        elif not (core_start <= first and last <= core_end+.02):
                            # Never fabricate a timestamp split for unknown words.
                            if last <= core_start or first >= core_end:
                                continue
                            raise ValueError("Cross-window speech requires word timestamps")
                        if not text or last<=first:
                            raise ValueError("Selected speech has no valid timed text")
                        yield SimpleNamespace(start=max(0, first), end=min(duration, last), text=text, language=language)
                finally:
                    if hasattr(segments, "close"):
                        segments.close()

    generator = windows()
    try:
        first = next(generator, None)  # Makes the first detected language available.
    except BaseException:
        generator.close()
        raise

    def remaining():
        try:
            if first is not None:
                yield first
            yield from generator
        finally:
            generator.close()
    return remaining(), info
