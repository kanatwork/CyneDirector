# [FILE: core/ai_models.py]
import torch
import sys
import os
import gc
import threading
from core.logger import get_logger

logger = get_logger(__name__)

# Enable JIT kernel caching to prevent recompiling on every launch
os.environ["CUDA_CACHE_DISABLE"] = "0"


def _detect_cuda_arch():
    """Detect the GPU compute capability and set TORCH_CUDA_ARCH_LIST accordingly.

    Supports: Turing (7.5), Ampere (8.0/8.6), Ada Lovelace (8.9),
    Hopper (9.0), Blackwell (9.0+ / 10.x — mapped to 9.0 if unsupported).
    """
    if not torch.cuda.is_available():
        return

    major, minor = torch.cuda.get_device_capability(0)
    arch = f"{major}.{minor}"

    # Known compute capabilities PyTorch can target.
    # If the detected arch is newer than what PyTorch knows, fall back to the
    # highest supported arch so the JIT compiler can still produce valid kernels.
    supported = ["7.5", "8.0", "8.6", "8.9", "9.0"]
    if arch not in supported:
        # GPU is newer than anything in the list — use the highest known arch
        arch = supported[-1]

    os.environ["TORCH_CUDA_ARCH_LIST"] = arch


_detect_cuda_arch()

class AIBackend:
    _instance = None
    _lock = threading.Lock() 

    def __new__(cls):
        if cls._instance is None:
            with cls._lock: 
                if cls._instance is None:
                    cls._instance = super(AIBackend, cls).__new__(cls)
                    
                    # --- HARDWARE INITIALIZATION ---
                    cls._instance.device, cls._instance.dtype = cls._instance._detect_best_device()

                    # Model Placeholders
                    cls._instance.clip_model = None
                    cls._instance.clip_processor = None
                    cls._instance.blip_model = None
                    cls._instance.blip_processor = None
                    cls._instance.whisper_model = None
                    cls._instance.tag_embeddings = None
                    cls._instance.llm_model = None
                    cls._instance.llm_tokenizer = None
                    cls._instance.yolo_model = None

                    # Thread-safe loading lock
                    cls._instance.load_lock = threading.Lock() 
            
        return cls._instance

    def _detect_best_device(self):
        """Select the best available compute backend: CUDA > MPS > CPU."""

        # --- 1. Try CUDA (NVIDIA) ---
        if torch.cuda.is_available():
            try:
                torch.backends.cuda.matmul.allow_tf32 = True
                torch.backends.cudnn.allow_tf32 = True
                torch.backends.cudnn.benchmark = True

                # Kernel smoke test — verify JIT compilation works
                conv = torch.nn.Conv2d(1, 1, 3).cuda()
                _ = conv(torch.randn(1, 1, 10, 10).cuda())

                device_name = torch.cuda.get_device_name(0)
                major, minor = torch.cuda.get_device_capability(0)
                arch_list = os.environ.get("TORCH_CUDA_ARCH_LIST", "unknown")
                print(f"AI BACKEND: CUDA ({device_name})")
                print(f"   Compute capability: {major}.{minor} (targeting {arch_list})")
                print(f"   Precision: Float16 (TF32 Enabled)")
                return "cuda", torch.float16

            except RuntimeError as e:
                logger.warning(f"CUDA available but kernel smoke test failed: {e}")
                print(f"CUDA kernel test failed: {e} — trying next backend...")

        # --- 2. Try MPS (Apple Silicon) ---
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            try:
                # Smoke test — MPS can report as available but fail on some ops
                _ = torch.zeros(1, device="mps")

                print("AI BACKEND: MPS (Apple Silicon)")
                print("   Precision: Float32 (MPS has limited float16 support)")
                return "mps", torch.float32

            except RuntimeError as e:
                logger.warning(f"MPS available but smoke test failed: {e}")
                print(f"MPS test failed: {e} — falling back to CPU...")

        # --- 3. CPU fallback ---
        print("AI BACKEND: CPU (no GPU detected)")
        print("   Precision: Float32")
        print("   Performance will be significantly slower than GPU.")
        return "cpu", torch.float32

    # --- 1. CLIP (Keywords) ---
    def load_clip(self):
        with self.load_lock:
            if self.clip_model: return self.clip_model, self.clip_processor
            
            print(f"Loading CLIP [{self.device}]...")
            try:
                from transformers import CLIPProcessor, CLIPModel
                from core.tags import get_tag_bank

                model_name = "openai/clip-vit-large-patch14"
                self.clip_processor = CLIPProcessor.from_pretrained(model_name, use_fast=True)
                self.clip_model = CLIPModel.from_pretrained(model_name).to(self.device)

                # Pre-compute Tag Embeddings
                print("   Building Vector Index...")
                tags = get_tag_bank()
                tag_embeddings_list = []

                batch_size = 256 if self.device == "cuda" else 64
                
                for i in range(0, len(tags), batch_size):
                    batch_tags = tags[i:i+batch_size]
                    inputs = self.clip_processor(text=batch_tags, return_tensors="pt", padding=True).to(self.device)
                    with torch.no_grad():
                        batch_embeds = self.clip_model.get_text_features(**inputs)
                        batch_embeds /= batch_embeds.norm(p=2, dim=-1, keepdim=True)
                        tag_embeddings_list.append(batch_embeds)
                
                self.tag_embeddings = torch.cat(tag_embeddings_list)
                return self.clip_model, self.clip_processor

            except Exception as e:
                print(f"CLIP LOAD FAILED: {e}")
                raise e

    # --- 2. BLIP / BLIP-2 (Scene Captioning) ---
    def load_blip(self):
        with self.load_lock:
            if self.blip_model: return self.blip_model, self.blip_processor

            from config import USE_BLIP2

            if USE_BLIP2:
                print(f"Loading BLIP-2 (2.7B) [{self.device}]...")
                try:
                    from transformers import Blip2Processor, Blip2ForConditionalGeneration

                    model_name = "Salesforce/blip2-opt-2.7b"
                    self.blip_processor = Blip2Processor.from_pretrained(model_name, use_fast=True)
                    self.blip_model = Blip2ForConditionalGeneration.from_pretrained(
                        model_name,
                        dtype=self.dtype
                    ).to(self.device)

                    return self.blip_model, self.blip_processor
                except Exception as e:
                    print(f"BLIP-2 LOAD FAILED: {e}")
                    raise e
            else:
                print(f"Loading BLIP-large (444M) [{self.device}]...")
                try:
                    from transformers import BlipProcessor, BlipForConditionalGeneration

                    model_name = "Salesforce/blip-image-captioning-large"
                    self.blip_processor = BlipProcessor.from_pretrained(model_name, use_fast=True)
                    self.blip_model = BlipForConditionalGeneration.from_pretrained(
                        model_name,
                        dtype=self.dtype
                    ).to(self.device)

                    return self.blip_model, self.blip_processor
                except Exception as e:
                    print(f"BLIP LOAD FAILED: {e}")
                    raise e

    # --- 2b. YOLOv8 (Object Detection) ---
    def load_yolo(self):
        with self.load_lock:
            if self.yolo_model: return self.yolo_model

            print(f"Loading YOLOv8m [{self.device}]...")
            try:
                from ultralytics import YOLO
                self.yolo_model = YOLO("yolov8m.pt")
                # Move to the active device (YOLO handles device internally via .to())
                if self.device != "cpu":
                    self.yolo_model.to(self.device)
                return self.yolo_model
            except Exception as e:
                print(f"YOLO LOAD FAILED: {e}")
                raise e

    # --- 3. WHISPER (Audio) ---

    def get_whisper_params(self, mode="accuracy"):
        """Return (model_name, device, compute_type) for faster-whisper based on
        the active backend and the requested quality mode.

        Workers should call this instead of hardcoding device strings.
        """
        if self.device == "cuda":
            whisper_device = "cuda"
            compute_type = "float16"
            speed_model = "medium"
        else:
            # MPS and CPU both use the CPU path — faster-whisper has no MPS support.
            # Use a smaller model in speed mode because CPU is much slower.
            whisper_device = "cpu"
            compute_type = "int8"
            speed_model = "small"

        model_name = "large-v3" if mode == "accuracy" else speed_model
        return model_name, whisper_device, compute_type

    def load_whisper(self):
        with self.load_lock:
            if self.whisper_model: return self.whisper_model

            model_name, whisper_device, compute_type = self.get_whisper_params("accuracy")
            print(f"Loading Whisper {model_name} [{whisper_device}]...")
            try:
                from faster_whisper import WhisperModel
                self.whisper_model = WhisperModel(model_name, device=whisper_device, compute_type=compute_type)
            except Exception as e:
                print(f"WHISPER FAILED: {e}")
                raise e

            return self.whisper_model

    # --- 4. LLM (Summary Generation) ---
    def load_llm(self):
        """Load lightweight LLM for summary generation."""
        with self.load_lock:
            if self.llm_model: return self.llm_model, self.llm_tokenizer
            
            print(f"Loading LLM for summary generation [{self.device}]...")
            try:
                from transformers import AutoModelForCausalLM, AutoTokenizer

                # Try with bitsandbytes quantization first (more memory efficient, CUDA only)
                try:
                    from transformers import BitsAndBytesConfig
                    model_name = "unsloth/Llama-3.2-3B-Instruct-bnb-4bit"

                    quantization_config = BitsAndBytesConfig(
                        load_in_4bit=True,
                        bnb_4bit_compute_dtype=self.dtype,
                        bnb_4bit_use_double_quant=True,
                        bnb_4bit_quant_type="nf4"
                    )

                    self.llm_tokenizer = AutoTokenizer.from_pretrained(model_name)
                    self.llm_model = AutoModelForCausalLM.from_pretrained(
                        model_name,
                        quantization_config=quantization_config,
                        device_map="auto",
                        dtype=self.dtype
                    )
                    print("   LLM model loaded successfully (with 4-bit quantization)")
                    return self.llm_model, self.llm_tokenizer
                except (ImportError, ModuleNotFoundError, Exception) as bnb_error:
                    # Fallback: Use smaller model without quantization
                    print(f"   BitsAndBytes not available ({bnb_error}), trying smaller model without quantization...")
                    try:
                        model_name = "microsoft/Phi-3-mini-4k-instruct"

                        self.llm_tokenizer = AutoTokenizer.from_pretrained(model_name)
                        self.llm_model = AutoModelForCausalLM.from_pretrained(
                            model_name,
                            device_map="auto",
                            dtype=self.dtype
                        )
                        print("   LLM model loaded successfully (Phi-3-mini, no quantization)")
                        return self.llm_model, self.llm_tokenizer
                    except Exception as fallback_error:
                        print(f"   Fallback model also failed ({fallback_error})")
                        raise bnb_error
                
            except Exception as e:
                print(f"LLM LOAD FAILED: {e}")
                print("   Falling back to template-based summary generation")
                # Don't raise - allow fallback to template-based approach
                return None, None

    def unload_models(self, keep_clip=False):
        """
        Unload AI models to free VRAM.
        
        Args:
            keep_clip: If True, keep CLIP model loaded (needed for transcript embeddings)
        """
        logger.debug(f"Unloading models (keep_clip={keep_clip})")
        with self.load_lock:
            logger.info("Releasing GPU Resources...")
            
            if not keep_clip and self.clip_model:
                del self.clip_model
                del self.clip_processor
                del self.tag_embeddings
                self.clip_model = None
                self.clip_processor = None
                self.tag_embeddings = None
            elif keep_clip:
                logger.debug("Keeping CLIP loaded (needed for transcript embeddings)")
                print("   Keeping CLIP loaded (needed for transcript embeddings)")
            
            if self.blip_model:
                del self.blip_model
                del self.blip_processor
                self.blip_model = None
                self.blip_processor = None

            if self.yolo_model:
                del self.yolo_model
                self.yolo_model = None

            if self.whisper_model:
                del self.whisper_model
                self.whisper_model = None
            
            if self.llm_model:
                del self.llm_model
                del self.llm_tokenizer
                self.llm_model = None
                self.llm_tokenizer = None

            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                torch.mps.empty_cache()
            logger.info("GPU memory purged")