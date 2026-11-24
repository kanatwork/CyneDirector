"""Explicit bounds for application buffers; model/native allocations are separate.

Metadata remains compatible with existing project readers. If a complete record
cannot fit, fail the stage instead of silently dropping scenes/transcript text.
"""
from dataclasses import dataclass
import json

MIB = 1024 ** 2


class MemoryBudgetExceeded(RuntimeError):
    pass


@dataclass(frozen=True)
class MemoryPolicy:
    mib: int = 256
    speech_seconds: int = 180

    def __post_init__(self):
        if type(self.mib) is not int or not 64 <= self.mib <= 1024:
            raise ValueError("processing_memory_mib must be an integer from 64 to 1024")
        if type(self.speech_seconds) is not int or not 1 <= self.speech_seconds <= 300:
            raise ValueError("speech_chunk_seconds must be an integer from 1 to 300")

    @classmethod
    def from_settings(cls, settings):
        return cls(settings.get("processing_memory_mib", 256), settings.get("speech_chunk_seconds", 180))

    @property
    def metadata_bytes(self):
        return min(16 * MIB, self.mib * MIB // 32)

    @property
    def max_nodes(self):
        return self.mib * 800

    @property
    def scene_records(self):
        return min(32768, self.mib * 32)

    @property
    def transcript_records(self):
        return min(40000, self.mib * 80)

    @property
    def frame_batch(self):
        return min(32, self.mib // 4)

    vector_batch = 64
    scene_images = 5
    keyframes = 5
    max_decode_pixels = 4096 * 2304
    summary_characters = 4096

    def dimensions(self, width, height):
        if width<=0 or height<=0:
            raise MemoryBudgetExceeded("Source dimensions are unknown; decode budget cannot be established")
        if width * height > self.max_decode_pixels:
            raise MemoryBudgetExceeded(f"Decoded frame {width}×{height} exceeds {self.max_decode_pixels} pixel budget")

    def validate(self, value):
        # Iterator stack grows with nesting depth, not the number of records.
        stack, nodes = [iter([value])], 0
        while stack:
            try:
                item = next(stack[-1])
            except StopIteration:
                stack.pop(); continue
            nodes += 1
            if nodes > self.max_nodes or len(stack) > 24:
                raise MemoryBudgetExceeded("Metadata structure exceeds processing buffer budget")
            if isinstance(item, dict):
                stack.append(iter(item.values()))
            elif isinstance(item, (list, tuple)):
                stack.append(iter(item))
        size = 0
        for chunk in json.JSONEncoder(ensure_ascii=False, allow_nan=False).iterencode(value):
            size += len(chunk.encode("utf-8"))
            if size > self.metadata_bytes:
                raise MemoryBudgetExceeded(f"Complete metadata exceeds {self.metadata_bytes} bytes; previous generation retained")
        return size

    def describe(self):
        return {"processing_memory_mib": self.mib, "metadata_bytes": self.metadata_bytes,
                "scene_record_limit": self.scene_records, "transcript_record_limit": self.transcript_records,
                "metadata_nodes": self.max_nodes, "scene_records": self.scene_records,
                "transcript_records": self.transcript_records, "frame_batch": self.frame_batch,
                "vector_batch": self.vector_batch, "retained_scene_images": self.scene_images,
                "keyframe_tail": self.keyframes, "speech_chunk_seconds": self.speech_seconds,
                "max_decode_pixels": self.max_decode_pixels,
                "scope": "application buffers; model, decoder and native allocator memory additional"}


class RecordBuffer(list):
    def __init__(self, limit, byte_limit, *, excluded=()):
        super().__init__()
        self.limit, self.byte_limit, self.excluded = limit, byte_limit, excluded
        self.bytes = 0

    def append(self, item):
        if len(self) >= self.limit:
            raise MemoryBudgetExceeded(f"Complete record count exceeds {self.limit}; stage not published")
        serializable = {k:v for k,v in item.items() if k not in self.excluded}
        # A model segment cannot create an arbitrarily large transient JSON string.
        for value in serializable.values():
            if isinstance(value, str) and len(value) > 65536:
                raise MemoryBudgetExceeded("One metadata record exceeds the 64K character limit")
        size = len(json.dumps(serializable, ensure_ascii=False, allow_nan=False).encode("utf-8"))
        if self.bytes + size > self.byte_limit:
            raise MemoryBudgetExceeded("Complete record bytes exceed processing budget; stage not published")
        super().append(item)
        self.bytes += size


class Tail(list):
    def __init__(self, limit):
        super().__init__(); self.limit = limit

    def append(self, value):
        if len(self) == self.limit:
            del self[0]
        super().append(value)


class ThreeFrameSet(set):
    """The algorithm only asks whether a tag occurs in at least three frames."""
    def add(self, frame):
        if len(self) < 3:
            super().add(frame)


def transcript_buffer(policy):
    return RecordBuffer(policy.transcript_records, policy.metadata_bytes // 2)
