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
                    
                    # --- PERFORMANCE OPTIMIZATION FOR RTX 40/50 SERIES ---
                    if torch.cuda.is_available():
                        cls._instance.device = "cuda"
                        
                        # 1. Enable cuDNN Benchmark (Finds fastest algo for your GPU)
                        torch.backends.cudnn.benchmark = True 
                        
                        # 2. Enable TensorFloat-32 (TF32) - CRITICAL FOR SPEED
                        torch.backends.cuda.matmul.allow_tf32 = True
                        torch.backends.cudnn.allow_tf32 = True
                        
                        # 3. High Precision Matrix Mul
                        try:
                            torch.set_float32_matmul_precision('high')
                        except AttributeError:
                            pass 

                        print(f"🚀 AI ACCELERATION: ON ({torch.cuda.get_device_name(0)})")
                        print("   ✅ TensorFloat-32 (TF32) Enabled")
                    else:
                        cls._instance.device = "cpu"
                        print("⚠️ WARNING: RUNNING ON CPU. INDEXING WILL BE SLOW.")

                    cls._instance.clip_model = None
                    cls._instance.clip_processor = None
                    cls._instance.whisper_model = None
                    cls._instance.tag_embeddings = None
                    cls._instance.load_lock = threading.Lock() 
            
        return cls._instance

    def load_clip(self):
        with self.load_lock:
            if self.clip_model: return self.clip_model, self.clip_processor
            
            print(f"Loading CLIP (Large) on {self.device}...")
            try:
                from transformers import CLIPProcessor, CLIPModel
                from core.tags import get_tag_bank
                
                model_name = "openai/clip-vit-large-patch14"
                self.clip_processor = CLIPProcessor.from_pretrained(model_name)
                self.clip_model = CLIPModel.from_pretrained(model_name).to(self.device)
                
                # Pre-compute Tag Embeddings with larger batch
                print("Pre-computing Tag Embeddings...")
                tags = get_tag_bank()
                tag_embeddings_list = []
                
                # Increased batch size for initialization
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
                print(f"AI LOAD ERROR: {e}")
                raise e

    def load_whisper(self):
        with self.load_lock:
            if self.whisper_model: return self.whisper_model
            
            print(f"Loading Faster-Whisper (Large-v3) on {self.device}...")
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