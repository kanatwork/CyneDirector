import sys
import os
print("=== CYNEDIRECTOR DIAGNOSTIC ===")

print("\n[1] CHECKING FACE LIBRARY...")
try:
    import facenet_pytorch
    print("   ✅ facenet-pytorch is installed.")
except ImportError:
    print("   ❌ CRITICAL: 'facenet-pytorch' is MISSING.")
    print("      Run: pip install facenet-pytorch")

print("\n[2] CHECKING AI MODEL (CLIP)...")
try:
    import torch
    from transformers import CLIPProcessor, CLIPModel
    print(f"   ✅ Torch detected (CUDA: {torch.cuda.is_available()})")
    print("   Loading CLIP model (Testing download)...")
    model = CLIPModel.from_pretrained("openai/clip-vit-large-patch14")
    print("   ✅ CLIP Model loaded successfully!")
except Exception as e:
    print(f"   ❌ CLIP Failed: {e}")
    print("      (This is why Visual Indexing is not working)")

input("\nPress Enter to exit...")