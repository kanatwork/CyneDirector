import os

# --- CONFIGURATION ---
OUTPUT_FILE = "FULL_PROJECT_DUMP.txt"

# Folders to completely ignore (Prevent massive files)
IGNORE_DIRS = {
    '__pycache__', '.git', '.idea', '.vscode', 'venv', 'env', 
    'node_modules', '_cyne_db', 'videos', 'footage', 'output', 'cache'
}

# File extensions to text-read (Add more if needed)
ALLOWED_EXTENSIONS = {
    '.py', '.json', '.md', '.txt', '.css', '.qss', '.bat', '.sh', '.xml', '.yml', '.yaml'
}

# Specific files to ignore
IGNORE_FILES = {
    'pack_project.py', # Don't include this script itself
    OUTPUT_FILE,       # Don't include the dump file
    '.DS_Store',
    'Thumbs.db'
}

def pack_code():
    project_root = os.getcwd()
    
    print(f"📦 Packing project from: {project_root}")
    print(f"🚫 Ignoring folders: {', '.join(IGNORE_DIRS)}")
    
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as outfile:
        # Header
        outfile.write("=== CYNEDIRECTOR CODEBASE DUMP ===\n\n")
        
        file_count = 0
        
        for root, dirs, files in os.walk(project_root):
            # Modify dirs in-place to skip ignored directories
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
            
            for file in files:
                if file in IGNORE_FILES:
                    continue
                
                # Check extension
                _, ext = os.path.splitext(file)
                if ext.lower() not in ALLOWED_EXTENSIONS:
                    continue
                
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, project_root)
                
                try:
                    with open(full_path, 'r', encoding='utf-8', errors='ignore') as infile:
                        content = infile.read()
                        
                        # Formatting for the dump
                        outfile.write("\n" + "="*50 + "\n")
                        outfile.write(f"FILE: {rel_path}\n")
                        outfile.write("="*50 + "\n")
                        outfile.write(content + "\n")
                        
                        file_count += 1
                        print(f"   ✅ Packed: {rel_path}")
                        
                except Exception as e:
                    print(f"   ❌ Error reading {rel_path}: {e}")

        outfile.write("\n=== END OF DUMP ===")
        
    print(f"\n🎉 Done! Packed {file_count} files into '{OUTPUT_FILE}'.")
    print("You can now upload this file to the new chat.")

if __name__ == "__main__":
    pack_code()