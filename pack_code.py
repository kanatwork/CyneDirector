import os

# --- CONFIGURATION ---
OUTPUT_FILE = "FULL_PROJECT_DUMP.txt"

# Folders to completely ignore
IGNORE_DIRS = {
    "_cyne_db",       # Database files (Heavy/Binary)
    "__pycache__",    # Compiled python
    ".git",           # Git history
    ".vscode",        # Editor settings
    "logs",           # Crash logs
    "assets",         # Images/Icons
    "venv",           # Virtual Environment
    "env"
}

# Only include files with these extensions
INCLUDE_EXTS = {
    ".py",            # Python Source
    ".txt",           # Requirements/Notes (if any)
    ".md"             # Readmes
}

# Specific filenames to always exclude
IGNORE_FILES = {
    "pack_project.py", # Don't include this script itself
    "FULL_PROJECT_DUMP.txt",
    ".DS_Store"
}

def pack_project():
    project_root = os.path.dirname(os.path.abspath(__file__))
    
    with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
        out.write(f"=== CYNEDIRECTOR CODEBASE DUMP ===\n")
        out.write(f"Generated from: {project_root}\n\n")

        for root, dirs, files in os.walk(project_root):
            # 1. Filter Directories in-place
            # This modifies 'dirs' so os.walk doesn't even enter ignored folders
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and not d.startswith(".")]
            
            for file in files:
                if file in IGNORE_FILES:
                    continue
                
                # 2. Extension Check
                _, ext = os.path.splitext(file)
                if ext.lower() not in INCLUDE_EXTS:
                    continue
                
                # 3. Write File Content
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, project_root)
                
                print(f"Packing: {rel_path}")
                
                out.write(f"\n{'='*50}\n")
                out.write(f"FILE: {rel_path}\n")
                out.write(f"{'='*50}\n")
                
                try:
                    with open(full_path, "r", encoding="utf-8") as f:
                        content = f.read()
                        out.write(content + "\n")
                except Exception as e:
                    out.write(f"[ERROR READING FILE: {e}]\n")

    print(f"\n✅ Success! All source code packed into: {OUTPUT_FILE}")

if __name__ == "__main__":
    pack_project()