import torch
import sys
import os
import gc
import threading

class AIBackend:
    _instance = None
    _lock = threading.Lock() # Fix for multi-threaded access

    def __new__(cls):
        if cls._instance is None:
            with cls._lock: # Ensure only one thread creates the instance
                if cls._instance is None:
                    cls._instance = super(AIBackend, cls).__new__(cls)
                    
                    # --- FORCE GPU CHECK ---
                    if torch.cuda.is_available():
                        cls._instance.device = "cuda"
                        torch.backends.cudnn.benchmark = True 
                        print(f"🚀 AI ACCELERATION: ON ({torch.cuda.get_device_name(0)})")
                    else:
                        cls._instance.device = "cpu"
                        print("⚠️ WARNING: RUNNING ON CPU. INDEXING WILL BE SLOW.")

                    cls._instance.clip_model = None
                    cls._instance.clip_processor = None
                    cls._instance.whisper_model = None
                    cls._instance.tag_embeddings = None
                    cls._instance.load_lock = threading.Lock() # Lock for loading specific models
            
        return cls._instance

    def load_clip(self):
        with self.load_lock: # Prevent race condition if multiple workers try to load
            if self.clip_model: return self.clip_model, self.clip_processor
            
            print(f"Loading CLIP (Large) on {self.device}...")
            try:
                from transformers import CLIPProcessor, CLIPModel
                from core.tags import get_tag_bank
                
                model_name = "openai/clip-vit-large-patch14"
                self.clip_processor = CLIPProcessor.from_pretrained(model_name)
                
                # --- ROBUST LOADING (Fix for RTX 50-Series) ---
                try:
                    self.clip_model = CLIPModel.from_pretrained(model_name).to(self.device)
                except RuntimeError as e:
                    if "no kernel image" in str(e) or "CUDA" in str(e):
                        print(f"⚠️ GPU ERROR: Your GPU is too new for this PyTorch version.")
                        print("   ➜ Switching to CPU mode automatically.")
                        self.device = "cpu"
                        self.clip_model = CLIPModel.from_pretrained(model_name).to(self.device)
                    else:
                        raise e
                
                # Pre-compute Tag Embeddings
                print("Pre-computing Tag Embeddings...")
                tags = get_tag_bank()
                tag_embeddings_list = []
                batch_size = 50
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
                print(f"AI LOAD ERROR: {e}")
                raise e

    def load_whisper(self):
        with self.load_lock:
            if self.whisper_model: return self.whisper_model
            
            print(f"Loading Faster-Whisper (Large-v3) on {self.device}...")
            from faster_whisper import WhisperModel
            
            try:
                device_str = "cuda" if self.device == "cuda" else "cpu"
                # Float16 is standard for RTX cards. INT8 is for CPU.
                compute_type = "float16" if self.device == "cuda" else "int8"
                
                try:
                    self.whisper_model = WhisperModel("large-v3", device=device_str, compute_type=compute_type)
                except RuntimeError as e:
                    print(f"⚠️ GPU ERROR (Whisper): {e}")
                    print("   ➜ Switching to CPU mode (int8)...")
                    self.whisper_model = WhisperModel("large-v3", device="cpu", compute_type="int8")

            except Exception as e:
                print(f"Whisper Load Error: {e}. Falling back to medium model.")
                self.whisper_model = WhisperModel("medium", device="cpu", compute_type="int8")
                
            return self.whisper_model

    def unload_models(self):
        """Frees VRAM by deleting models and clearing cache."""
        with self.load_lock:
            print("🧹 Unloading AI Models...")
            if self.clip_model:
                del self.clip_model
                del self.clip_processor
                del self.tag_embeddings
                self.clip_model = None
                self.clip_processor = None
                self.tag_embeddings = None
                
            if self.whisper_model:
                del self.whisper_model
                self.whisper_model = None

            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            print("   VRAM Cleared.")