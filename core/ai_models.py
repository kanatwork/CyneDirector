# [FILE: core/ai_models.py]
import torch
import sys
import os
import gc
import threading

class AIBackend:
    _instance = None
    _lock = threading.Lock() 

    def __new__(cls):
        if cls._instance is None:
            with cls._lock: 
                if cls._instance is None:
                    cls._instance = super(AIBackend, cls).__new__(cls)
                    
                    # --- HARDWARE DETECTION & SAFETY ---
                    # We probe the hardware to ensure stability before loading heavy models
                    cls._instance.device, cls._instance.dtype = cls._instance._detect_hardware_capabilities()

                    # Model Placeholders
                    cls._instance.clip_model = None
                    cls._instance.clip_processor = None
                    cls._instance.blip_model = None
                    cls._instance.blip_processor = None
                    cls._instance.whisper_model = None
                    cls._instance.tag_embeddings = None
                    
                    # Thread-safe loading lock
                    cls._instance.load_lock = threading.Lock() 
            
        return cls._instance

    def _detect_hardware_capabilities(self):
        """
        Proactively tests if the GPU is usable. 
        Returns: (device_str, torch_dtype)
        """
        if not torch.cuda.is_available():
            print("⚠️ AI CORE: No CUDA detected. Running on CPU (Slow).")
            return "cpu", torch.float32

        try:
            # 1. Test basic allocation
            x = torch.tensor([1.0]).cuda()
            # 2. Test a small matmul (catches some driver/kernel mismatches)
            y = x @ x
            
            # 3. Apply Optimizations
            torch.backends.cudnn.benchmark = True 
            torch.backends.cuda.matmul.allow_tf32 = True
            torch.backends.cudnn.allow_tf32 = True
            
            device_name = torch.cuda.get_device_name(0)
            print(f"🚀 AI ACCELERATION: ON ({device_name}) | Precision: Float16")
            
            return "cuda", torch.float16
        except RuntimeError as e:
            print(f"⚠️ GPU ERROR: CUDA available but failed stability test: {e}")
            print(" ➜ Switching to CPU mode to prevent crash.")
            return "cpu", torch.float32

    # --- 1. CLIP (Keywords) ---
    def load_clip(self):
        with self.load_lock:
            if self.clip_model: return self.clip_model, self.clip_processor
            
            print(f"Loading CLIP (Search Engine) on {self.device}...")
            try:
                from transformers import CLIPProcessor, CLIPModel
                from core.tags import get_tag_bank
                
                model_name = "openai/clip-vit-large-patch14"
                self.clip_processor = CLIPProcessor.from_pretrained(model_name)
                self.clip_model = CLIPModel.from_pretrained(model_name).to(self.device)
                
                # Pre-compute Tag Embeddings (Crucial for Search Speed)
                print("Building Search Index...")
                tags = get_tag_bank()
                tag_embeddings_list = []
                
                batch_size = 100 
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
                print(f"CLIP LOAD ERROR: {e}")
                raise e

    # --- 2. BLIP-2 (Action Description) ---
    def load_blip(self):
        with self.load_lock:
            if self.blip_model: return self.blip_model, self.blip_processor
            
            print(f"Loading BLIP-2 (Advanced Captioning) on {self.device}...")
            try:
                from transformers import Blip2Processor, Blip2ForConditionalGeneration
                
                model_name = "Salesforce/blip2-opt-2.7b"
                self.blip_processor = Blip2Processor.from_pretrained(model_name)
                
                # Load in Float16 to save memory if on GPU
                self.blip_model = Blip2ForConditionalGeneration.from_pretrained(
                    model_name, 
                    torch_dtype=self.dtype
                ).to(self.device)
                
                return self.blip_model, self.blip_processor
            except Exception as e:
                print(f"BLIP-2 LOAD ERROR: {e}")
                raise e

    # --- 3. WHISPER (Audio) ---
    def load_whisper(self):
        with self.load_lock:
            if self.whisper_model: return self.whisper_model
            
            print(f"Loading Faster-Whisper on {self.device}...")
            try:
                from faster_whisper import WhisperModel
                
                # Map torch device to faster_whisper string
                device_str = "cuda" if self.device == "cuda" else "cpu"
                
                # Determine compute type (float16 is faster on GPU, int8 safe for CPU)
                if self.device == "cuda":
                    compute_type = "float16"
                else:
                    compute_type = "int8"

                self.whisper_model = WhisperModel("large-v3", device=device_str, compute_type=compute_type)
            
            except Exception as e:
                print(f"Whisper 'large-v3' Load Error: {e}.")
                print("Falling back to 'medium' model on CPU (int8).")
                try:
                    from faster_whisper import WhisperModel
                    self.whisper_model = WhisperModel("medium", device="cpu", compute_type="int8")
                except Exception as e2:
                    print(f"CRITICAL WHISPER FAILURE: {e2}")
                    raise e2
                    
            return self.whisper_model

    def unload_models(self):
        """Frees VRAM by deleting models and clearing cache."""
        with self.load_lock:
            print("🧹 Unloading AI Models...")
            
            if self.clip_model:
                del self.clip_model
                del self.clip_processor
                del self.tag_embeddings
            
            if self.blip_model:
                del self.blip_model
                del self.blip_processor

            if self.whisper_model:
                del self.whisper_model
                
            self.clip_model = None
            self.clip_processor = None
            self.blip_model = None
            self.blip_processor = None
            self.whisper_model = None
            self.tag_embeddings = None

            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            print("   VRAM Cleared.")