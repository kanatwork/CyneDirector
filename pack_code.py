import os

# Files to ignore (saves space)
IGNORE_DIRS = {'__pycache__', '_cyne_db', '.git', '.vscode', 'logs'}
IGNORE_EXTS = {'.pyc', '.jpg', '.mp4', '.json', '.kan'}

def pack_project():
    output_file = "FULL_PROJECT_DUMP.txt"
    root_dir = os.getcwd()
    
    with open(output_file, "w", encoding="utf-8") as outfile:
        outfile.write("=== CYNEDIRECTOR CODEBASE DUMP ===\n\n")
        
        for dirpath, dirnames, filenames in os.walk(root_dir):
            # Skip ignored directories
            dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]
            
            for filename in filenames:
                if any(filename.endswith(ext) for ext in IGNORE_EXTS):
                    continue
                    
                filepath = os.path.join(dirpath, filename)
                rel_path = os.path.relpath(filepath, root_dir)
                
                # Only grab .py files or requirements
                if filename.endswith(".py") or filename == "requirements.txt":
                    outfile.write(f"\n\n{'='*50}\nFILE: {rel_path}\n{'='*50}\n")
                    try:
                        with open(filepath, "r", encoding="utf-8") as infile:
                            outfile.write(infile.read())
                    except Exception as e:
                        outfile.write(f"[Error reading file: {e}]")

    print(f"Done! Upload '{output_file}' to the chat.")

if __name__ == "__main__":
    pack_project()