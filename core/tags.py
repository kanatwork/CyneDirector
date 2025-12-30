import os
from pathlib import Path

# --- ARCHITECTURAL STRATEGY ---
# 1. PRIORITY: Distinct Objects > Abstract Concepts. 
#    (Prevents "Lens Flare" false positives when the image is just a bright light).
# 2. ACTIONS: Gerunds (Ending in -ing) work best for CLIP to detect motion/activity.

# --- TAG HIERARCHY ---
# Defines parent-child relationships for tags
TAG_HIERARCHY = {
    "Vehicle": ["Car", "Taxi", "Police Car", "Ambulance", "Bicycle", "Motorcycle", "Bus", "Train", "Truck", "Van", "Boat", "Yacht", "Airplane", "Helicopter", "Drone", "Ship", "Subway", "Tram"],
    "Person": ["Woman", "Man", "Girl", "Boy", "Baby", "Toddler", "Teenager", "Elderly Person", "Child", "Adult", "People", "Individual"],
    "Animal": ["Dog", "Cat", "Bird", "Eagle", "Pigeon", "Horse", "Cow", "Sheep", "Chicken", "Duck", "Goose", "Swan", "Fish", "Shark", "Whale", "Dolphin", "Lion", "Tiger", "Bear", "Wolf", "Fox", "Deer", "Rabbit"],
    "Food": ["Pizza", "Burger", "Cake", "Fruit", "Vegetable", "Bread", "Soup", "Salad", "Plate of Food", "Sandwich"],
    "Technology": ["Smartphone", "Laptop", "Notebook", "Computer", "Tablet", "Phone", "Camera", "Television", "TV", "Screen", "Monitor", "Keyboard", "Mouse"],
    "Furniture": ["Chair", "Table", "Sofa", "Bed", "Desk", "Shelf", "Cabinet"],
    "Clothing": ["Shirt", "Pants", "Dress", "Jacket", "Coat", "Suit", "Tie", "Scarf", "Hat", "Cap", "Shoes", "Boots"],
    "Action": ["Running", "Walking", "Sitting", "Standing", "Jumping", "Climbing", "Talking", "Shouting", "Laughing", "Smiling", "Crying", "Singing", "Speaking", "Typing", "Writing", "Reading", "Cooking", "Driving", "Cycling", "Swimming", "Flying", "Dancing", "Fighting", "Hugging", "Kissing", "Waving", "Clapping", "Pointing", "Working", "Playing", "Exercising"]
}

def get_tag_parent(tag):
    """Get parent tag for a given tag, if any."""
    for parent, children in TAG_HIERARCHY.items():
        if tag in children:
            return parent
    return None

def get_tag_children(tag):
    """Get child tags for a given parent tag, if any."""
    return TAG_HIERARCHY.get(tag, [])

def get_tag_family(tag):
    """Get all related tags (parent + siblings) for a given tag."""
    family = [tag]
    parent = get_tag_parent(tag)
    if parent:
        family.append(parent)
        siblings = get_tag_children(parent)
        family.extend(siblings)
    else:
        children = get_tag_children(tag)
        family.extend(children)
    return list(set(family))  # Remove duplicates

# A curated "Essentials" list to ensure the app works well out-of-the-box.
# EXPANDED TAG BANK for better keyword accuracy and coverage
DEFAULT_TAG_BANK = [
    # --- PROPS & OBJECTS (The most important category for B-Roll) ---
    "Smartphone", "Laptop", "Notebook", "Pen", "Pencil", "Camera", "Headphones", "Tablet", "Computer",
    "Coffee Cup", "Glass of Water", "Wine Bottle", "Beer", "Plate of Food", "Sandwich", "Bottle", "Mug",
    "Car", "Taxi", "Police Car", "Ambulance", "Bicycle", "Motorcycle", "Bus", "Train", "Truck", "Van",
    "Boat", "Yacht", "Airplane", "Helicopter", "Drone", "Ship", "Subway", "Tram",
    "Gun", "Knife", "Sword", "Ring", "Diamond", "Money", "Credit Card", "Wallet", "Jewelry", "Watch",
    "Bag", "Suitcase", "Backpack", "Umbrella", "Glasses", "Sunglasses", "Hat", "Cap", "Shoes", "Boots",
    "Mirror", "Clock", "Lamp", "Candle", "Fire", "Smoke", "Light", "Bulb", "Flashlight",
    "Chair", "Table", "Sofa", "Bed", "Door", "Window", "Carpet", "Curtain", "Desk", "Shelf", "Cabinet",
    "Book", "Newspaper", "Magazine", "Document", "Paper", "Folder", "File", "Envelope",
    "Phone", "Radio", "Television", "TV", "Screen", "Monitor", "Keyboard", "Mouse",
    "Food", "Pizza", "Burger", "Cake", "Fruit", "Vegetable", "Bread", "Soup", "Salad",
    "Clothing", "Shirt", "Pants", "Dress", "Jacket", "Coat", "Suit", "Tie", "Scarf",
    
    # --- PEOPLE (Expanded) ---
    "Woman", "Man", "Girl", "Boy", "Baby", "Toddler", "Teenager", "Elderly Person", "Child", "Adult",
    "Crowd", "Couple", "Friends", "Family", "Business Team", "Police Officer", "Group", "People",
    "Doctor", "Nurse", "Soldier", "Artist", "Musician", "Chef", "Waiter", "Driver", "Teacher", "Student",
    "Silhouette", "Portrait", "Close up of Eyes", "Close up of Hands", "Face", "Person", "Individual",
    "Bride", "Groom", "Wedding Party", "Guest", "Audience", "Spectator", "Performer", "Actor", "Actress",
    "Athlete", "Runner", "Player", "Coach", "Referee", "Fan", "Supporter",

    # --- ACTIONS (Verbs - Expanded) ---
    "Running", "Walking", "Sitting", "Standing", "Sleeping", "Eating", "Drinking", "Jumping", "Climbing",
    "Talking", "Shouting", "Laughing", "Smiling", "Crying", "Frowning", "Singing", "Speaking", "Whispering",
    "Typing", "Writing", "Reading", "Cooking", "Driving", "Cycling", "Swimming", "Flying", "Sailing",
    "Dancing", "Fighting", "Punching", "Hugging", "Kissing", "Shaking Hands", "Waving", "Greeting",
    "Clapping", "Pointing", "Thinking", "Looking at Phone", "Working on Laptop", "Working", "Studying",
    "Playing", "Exercising", "Training", "Practicing", "Performing", "Presenting", "Teaching", "Learning",
    "Shopping", "Buying", "Selling", "Negotiating", "Meeting", "Discussing", "Arguing", "Agreeing",
    "Celebrating", "Partying", "Socializing", "Networking", "Relaxing", "Resting", "Meditating",
    "Searching", "Finding", "Looking", "Observing", "Watching", "Listening", "Hearing", "Seeing",
    "Moving", "Traveling", "Arriving", "Departing", "Entering", "Exiting", "Opening", "Closing",
    "Building", "Constructing", "Creating", "Making", "Designing", "Painting", "Drawing", "Sculpting",
    "Cleaning", "Organizing", "Arranging", "Preparing", "Setting up", "Taking down", "Packing", "Unpacking",

    # --- ANIMALS (Expanded) ---
    "Dog", "Cat", "Bird", "Eagle", "Pigeon", "Horse", "Cow", "Sheep", "Chicken", "Duck", "Goose", "Swan",
    "Fish", "Shark", "Whale", "Dolphin", "Lion", "Tiger", "Bear", "Wolf", "Fox", "Deer", "Rabbit",
    "Snake", "Spider", "Butterfly", "Bee", "Insect", "Ant", "Fly", "Mosquito", "Elephant", "Giraffe",
    "Zebra", "Monkey", "Panda", "Penguin", "Seal", "Turtle", "Frog", "Lizard", "Crocodile", "Alligator",

    # --- NATURE & ENVIRONMENTS (Expanded) ---
    "Forest", "Tree", "Flower", "Grass", "Leaf", "Branch", "Root", "Bark", "Moss", "Fern",
    "Mountain", "Hill", "Valley", "Desert", "Sand", "Beach", "Shore", "Coast", "Cliff", "Rock",
    "Ocean", "Sea", "River", "Lake", "Pond", "Stream", "Waterfall", "Wave", "Tide", "Current",
    "Rain", "Snow", "Storm", "Clouds", "Fog", "Mist", "Wind", "Lightning", "Thunder", "Hail",
    "Blue Sky", "Sunset", "Sunrise", "Dawn", "Dusk", "Twilight", "Night Sky", "Moon", "Stars", "Sun",
    "City Skyline", "Skyscraper", "Street", "Road", "Bridge", "Tunnel", "Highway", "Alley", "Pathway",
    "Traffic", "Building", "House", "Apartment", "Office", "Hospital", "School", "University", "Library",
    "Restaurant", "Cafe", "Bar", "Club", "Gym", "Airport", "Station", "Warehouse", "Factory", "Store",
    "Ruins", "Construction Site", "Park", "Garden", "Playground", "Stadium", "Arena", "Theater", "Cinema",
    "Museum", "Gallery", "Church", "Temple", "Mosque", "Synagogue", "Cathedral", "Castle", "Palace",
    "Farm", "Field", "Meadow", "Prairie", "Jungle", "Tundra", "Ice", "Glacier", "Volcano", "Cave",

    # --- COLORS & LIGHTING (Expanded) ---
    "Red", "Blue", "Green", "Yellow", "Purple", "Orange", "Black", "White", "Gray", "Grey", "Brown",
    "Pink", "Cyan", "Magenta", "Gold", "Silver", "Bronze", "Neon Light", "Sunlight", "Moonlight",
    "Shadows", "Silhouette", "Reflection", "Glow", "Bright", "Dark", "Dim", "Lit", "Unlit",
    "Daylight", "Artificial Light", "Candlelight", "Firelight", "Spotlight", "Flash", "Beam",

    # --- CINEMATOGRAPHY & COMPOSITION (Expanded) ---
    "Aerial View", "Drone Shot", "Underwater", "Macro Shot", "Black and White", "Color", "Sepia",
    "Green Screen", "Animation", "Text Overlay", "Close-up", "Wide Shot", "Long Shot", "Medium Shot",
    "Pan", "Tilt", "Zoom", "Tracking", "Steady", "Shaky", "Blur", "Focus", "Depth of Field",
    "Slow Motion", "Fast Motion", "Time Lapse", "Split Screen", "Montage", "Transition",
    "Golden Hour", "Blue Hour", "High Contrast", "Low Contrast", "Saturated", "Desaturated",
    "Vignette", "Grain", "Noise", "Clean", "Sharp", "Soft", "Gritty", "Smooth"
]

def _is_irrelevant_tag(tag):
    """
    Filters out irrelevant tags that shouldn't be used for visual indexing.
    Excludes: proper nouns, technical terms, abstract concepts, non-visual tags, etc.
    """
    tag_lower = tag.lower().strip()
    
    # Skip empty or very short tags
    if len(tag_lower) < 2:
        return True
    
    # Get default tag bank lowercase for comparison
    default_tags_lower = {t.lower() for t in DEFAULT_TAG_BANK}
    
    # Skip abstract/non-visual concepts
    abstract_concepts = [
        "concept", "idea", "feeling", "emotion", "thought", "memory", "dream",
        "imagination", "fantasy", "reality", "truth", "lie", "belief", "opinion",
        "theory", "hypothesis", "principle", "philosophy", "meaning", "purpose",
        "intention", "desire", "hope", "fear", "worry", "anxiety", "stress",
        "pressure", "tension", "relief", "satisfaction", "disappointment"
    ]
    
    # Check if tag is an abstract concept
    words = tag_lower.split()
    for word in words:
        word_clean = word.strip(".,;:!?()[]{}")
        if word_clean in abstract_concepts:
            return True
    
    # Skip generic/non-descriptive tags
    generic_terms = [
        "thing", "stuff", "object", "item", "element", "component", "part",
        "piece", "unit", "entity", "subject", "topic", "matter", "content",
        "material", "substance", "product", "article", "feature", "aspect"
    ]
    
    # Check if tag is too generic
    if tag_lower in generic_terms:
        return True
    
    # Skip non-visual standalone emotion/feeling words (unless in context like "happy face")
    standalone_emotions = ["happy", "sad", "angry", "excited", "worried", "confused", 
                          "neutral", "surprised", "frustrated", "anxious", "calm"]
    if len(words) == 1 and tag_lower in standalone_emotions:
        return True  # Reject standalone emotions, but allow "happy face", "sad person", etc.
    
    # Skip technical/abstract terms that aren't visual
    irrelevant_patterns = [
        "random access memory", "read-only memory", "central processing unit",
        "graphics processing unit", "solid state drive", "hard disk drive",
        "operating system", "application programming interface", "user interface",
        "machine learning", "artificial intelligence", "neural network",
        "data structure", "file system", "network protocol", "access memory",
        "processing unit", "disk drive", "state drive"
    ]
    
    for pattern in irrelevant_patterns:
        if pattern in tag_lower:
            return True
    
    # Skip technical abbreviations and terms
    technical_terms = [
        "ram", "rom", "cpu", "gpu", "ssd", "hdd", "api", "ui", "ux", "os",
        "memory", "byte", "bit", "program", "software", "hardware", 
        "algorithm", "protocol", "database", "server", "client", "network"
    ]
    
    # Check if tag is exactly a technical term or contains it as a standalone word
    for word in words:
        word_clean = word.strip(".,;:!?()[]{}")
        if word_clean in technical_terms:
            return True
    
    # Skip single-word capitalized tags that aren't in default bank (likely proper nouns)
    # But allow common visual terms
    if len(tag.split()) == 1:
        # If it's capitalized and not in our default bank, likely a proper noun
        if tag[0].isupper() and tag_lower not in default_tags_lower:
            # Additional check: if it's a short capitalized word (2-5 chars), likely a name
            if 2 <= len(tag) <= 5 and tag[0].isupper() and tag[1:].islower():
                return True
            # If it's longer but still capitalized and not in default bank, be cautious
            # Only skip if it doesn't look like a common visual term
            if len(tag) > 5 and tag_lower not in default_tags_lower:
                # Check if it contains technical terms
                if any(term in tag_lower for term in technical_terms):
                    return True
    
    # Skip tags that are clearly names (common name patterns)
    # Simple heuristic: single capitalized word, 3-8 chars, not in default bank
    if len(tag.split()) == 1 and 3 <= len(tag) <= 8:
        if tag[0].isupper() and tag[1:].islower() and tag_lower not in default_tags_lower:
            # Could be a name, skip it
            return True
    
    return False

def get_tag_bank():
    """
    Loads tags from 'vocabulary.txt' if it exists in the project root or assets folder.
    Otherwise, returns the sophisticated DEFAULT_TAG_BANK.
    Filters out irrelevant entries (proper nouns, technical terms, etc.)
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
                    # Filter out irrelevant tags
                    filtered_lines = [line for line in lines if not _is_irrelevant_tag(line)]
                    custom_tags.extend(filtered_lines)
                print(f"[Tags] Loaded {len(filtered_lines)} custom tags from {p} (filtered {len(lines) - len(filtered_lines)} irrelevant)")
                break # Stop after finding the first valid file
            except Exception as e:
                print(f"[Tags] Error reading {p}: {e}")

    # 2. Merge or Fallback
    if custom_tags:
        # Deduplicate while preserving order
        return list(dict.fromkeys(custom_tags))
    
    return DEFAULT_TAG_BANK