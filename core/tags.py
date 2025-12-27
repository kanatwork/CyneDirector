import os
from pathlib import Path

# --- ARCHITECTURAL STRATEGY ---
# 1. PRIORITY: Distinct Objects > Abstract Concepts. 
#    (Prevents "Lens Flare" false positives when the image is just a bright light).
# 2. ACTIONS: Gerunds (Ending in -ing) work best for CLIP to detect motion/activity.

# A curated "Essentials" list to ensure the app works well out-of-the-box.
DEFAULT_TAG_BANK = [
    # --- PROPS & OBJECTS (The most important category for B-Roll) ---
    "Smartphone", "Laptop", "Notebook", "Pen", "Pencil", "Camera", "Headphones",
    "Coffee Cup", "Glass of Water", "Wine Bottle", "Beer", "Plate of Food", "Sandwich",
    "Car", "Taxi", "Police Car", "Ambulance", "Bicycle", "Motorcycle", "Bus", "Train",
    "Boat", "Yacht", "Airplane", "Helicopter", "Drone",
    "Gun", "Knife", "Sword", "Ring", "Diamond", "Money", "Credit Card", "Wallet",
    "Bag", "Suitcase", "Backpack", "Umbrella", "Glasses", "Sunglasses", "Watch",
    "Mirror", "Clock", "Lamp", "Candle", "Fire", "Smoke",
    "Chair", "Table", "Sofa", "Bed", "Door", "Window", "Carpet", "Curtain",
    
    # --- PEOPLE ---
    "Woman", "Man", "Girl", "Boy", "Baby", "Toddler", "Teenager", "Elderly Person",
    "Crowd", "Couple", "Friends", "Family", "Business Team", "Police Officer",
    "Doctor", "Nurse", "Soldier", "Artist", "Musician", "Chef", "Waiter", "Driver",
    "Silhouette", "Portrait", "Close up of Eyes", "Close up of Hands",

    # --- ACTIONS (Verbs) ---
    "Running", "Walking", "Sitting", "Standing", "Sleeping", "Eating", "Drinking",
    "Talking", "Shouting", "Laughing", "Smiling", "Crying", "Frowning",
    "Typing", "Writing", "Reading", "Cooking", "Driving", "Cycling", "Swimming",
    "Dancing", "Fighting", "Punching", "Hugging", "Kissing", "Shaking Hands",
    "Clapping", "Pointing", "Thinking", "Looking at Phone", "Working on Laptop",

    # --- ANIMALS ---
    "Dog", "Cat", "Bird", "Eagle", "Pigeon", "Horse", "Cow", "Sheep", "Chicken",
    "Fish", "Shark", "Whale", "Lion", "Tiger", "Bear", "Wolf", "Snake", "Spider",
    "Butterfly", "Bee", "Insect",

    # --- NATURE & ENVIRONMENTS ---
    "Forest", "Tree", "Flower", "Grass", "Mountain", "Desert", "Sand", "Beach",
    "Ocean", "River", "Lake", "Waterfall", "Rain", "Snow", "Storm", "Clouds",
    "Blue Sky", "Sunset", "Sunrise", "Night Sky", "Moon", "Stars",
    "City Skyline", "Skyscraper", "Street", "Road", "Bridge", "Tunnel", "Highway",
    "Traffic", "Building", "House", "Apartment", "Office", "Hospital", "School",
    "Restaurant", "Cafe", "Bar", "Club", "Gym", "Airport", "Station", "Warehouse",
    "Ruins", "Construction Site",

    # --- COLORS & LIGHTING (Distinct only) ---
    "Red", "Blue", "Green", "Yellow", "Purple", "Orange", "Black", "White",
    "Neon Light", "Sunlight", "Shadows", "Silhouette", "Reflection",

    # --- CINEMATOGRAPHY (Strictly Distinct) ---
    # We removed ambiguous terms like "Dutch Angle" or "Medium Shot" to reduce noise.
    "Aerial View", "Drone Shot", "Underwater", "Macro Shot", "Black and White",
    "Green Screen", "Animation", "Text Overlay"
]

def get_tag_bank():
    """
    Loads tags from 'vocabulary.txt' if it exists in the project root or assets folder.
    Otherwise, returns the sophisticated DEFAULT_TAG_BANK.
    """
    # 1. Check for custom vocabulary file in common locations
    possible_paths = [
        Path("vocabulary.txt"),
        Path("assets/vocabulary.txt"),
    ]
    
    custom_tags = []
    
    for p in possible_paths:
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    # Read lines, strip whitespace, remove empty lines
                    lines = [line.strip() for line in f.readlines() if line.strip()]
                    custom_tags.extend(lines)
                print(f"[Tags] Loaded {len(lines)} custom tags from {p}")
                break # Stop after finding the first valid file
            except Exception as e:
                print(f"[Tags] Error reading {p}: {e}")

    # 2. Merge or Fallback
    if custom_tags:
        # Deduplicate while preserving order
        return list(dict.fromkeys(custom_tags))
    
    return DEFAULT_TAG_BANK