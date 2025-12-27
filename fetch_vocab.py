# FILE: fetch_vocab_pro.py
import requests
import re

# 1. ImageNet-21k (The "Everything" List - ~21,000 tags)
# Source: Google Research Big Transfer (BiT) official repository
URL_IMAGENET = "https://storage.googleapis.com/bit_models/imagenet21k_wordnet_lemmas.txt"

# 2. Places365 (The "Environments" List - 365 tags)
# Source: MIT CSAIL Vision official repository
URL_PLACES = "https://raw.githubusercontent.com/CSAILVision/places365/master/categories_places365.txt"

def fetch_master_list():
    print("🚀 CONTACTING DATABASES...")
    
    full_vocab = set()

    # --- FETCH IMAGENET-21K ---
    try:
        print(f"   ⬇️  Downloading ImageNet-21k (21,000+ concepts)...")
        resp = requests.get(URL_IMAGENET)
        if resp.status_code == 200:
            lines = resp.text.split('\n')
            for line in lines:
                # ImageNet formatting is sometimes "noun, synonym". We just want the first one.
                # Example: "espresso_maker, espresso_machine" -> "Espresso maker"
                clean = line.split(',')[0].replace('_', ' ').strip()
                if len(clean) > 2:
                    full_vocab.add(clean.title())
        else:
            print("   ❌ Error reaching ImageNet server.")
    except Exception as e:
        print(f"   ❌ ImageNet failed: {e}")

    # --- FETCH PLACES365 ---
    try:
        print(f"   ⬇️  Downloading Places365 (Environments)...")
        resp = requests.get(URL_PLACES)
        if resp.status_code == 200:
            lines = resp.text.split('\n')
            for line in lines:
                # Format: "/a/airfield" -> "Airfield"
                parts = line.split(' ')
                if parts:
                    clean = parts[0].split('/')[-1].replace('_', ' ').strip()
                    if len(clean) > 2:
                        full_vocab.add(clean.title())
        else:
            print("   ❌ Error reaching MIT server.")
    except Exception as e:
        print(f"   ❌ Places365 failed: {e}")

    # --- SAVE TO DISK ---
    final_list = sorted(list(full_vocab))
    
    with open("vocabulary.txt", "w", encoding="utf-8") as f:
        for word in final_list:
            f.write(word + "\n")

    print(f"\n✅ SUCCESS! Master vocabulary built.")
    print(f"   📚 Total unique tags: {len(final_list)}")
    print(f"   📂 Saved to: {os.path.abspath('vocabulary.txt')}")
    print("   (Restart CyneDirector to load this new brain)")

if __name__ == "__main__":
    import os
    fetch_master_list()