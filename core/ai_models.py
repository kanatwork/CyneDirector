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
                    
                    # --- RTX 5070 OPTIMIZATION ---
                    if torch.cuda.is_available():
                        cls._instance.device = "cuda"
                        # Use Float16 for massive speedup and VRAM savings
                        cls._instance.dtype = torch.float16 
                        
                        torch.backends.cudnn.benchmark = True 
                        torch.backends.cuda.matmul.allow_tf32 = True
                        torch.backends.cudnn.allow_tf32 = True
                        print(f"🚀 AI ACCELERATION: ON ({torch.cuda.get_device_name(0)}) | Precision: Float16")
                    else:
                        cls._instance.device = "cpu"
                        cls._instance.dtype = torch.float32
                        print("⚠️ WARNING: RUNNING ON CPU.")

                    # Model Placeholders
                    cls._instance.clip_model = None
                    cls._instance.clip_processor = None
                    cls._instance.blip_model = None
                    cls._instance.blip_processor = None
                    cls._instance.whisper_model = None
                    cls._instance.tag_embeddings = None
                    cls._instance.load_lock = threading.Lock() 
            
        return cls._instance

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
                
                # Pre-compute Tag Embeddings
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

    # --- 2. BLIP-2 (Action Description - THE UPGRADE) ---
    def load_blip(self):
        with self.load_lock:
            if self.blip_model: return self.blip_model, self.blip_processor
            
            print(f"Loading BLIP-2 (Advanced Captioning) on {self.device}...")
            try:
                # We use Blip2Processor and Blip2ForConditionalGeneration
                from transformers import Blip2Processor, Blip2ForConditionalGeneration
                
                # "opt-2.7b" is the sweet spot. Much smarter than base BLIP, but fits on GPU.
                model_name = "Salesforce/blip2-opt-2.7b"
                
                self.blip_processor = Blip2Processor.from_pretrained(model_name)
                # Load in Float16 to save memory
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
            from faster_whisper import WhisperModel
            
            try:
                device_str = "cuda" if self.device == "cuda" else "cpu"
                compute_type = "float16" if self.device == "cuda" else "int8"
                self.whisper_model = WhisperModel("large-v3", device=device_str, compute_type=compute_type)
            except Exception as e:
                print(f"Whisper Load Error: {e}")
                raise e
            return self.whisper_model

    def unload_models(self):
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