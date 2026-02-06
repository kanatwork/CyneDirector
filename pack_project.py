import os
from pathlib import Path
from datetime import datetime

# Config
OUTPUT_FILE = "FULL_PROJECT_DUMP_v2.txt"
MAX_FILE_SIZE_KB = 500  # Skip files larger than this

# Extensions to include
CODE_EXTENSIONS = {
    '.py', '.js', '.ts', '.tsx', '.jsx', '.html', '.css', '.scss',
    '.json', '.yaml', '.yml', '.toml', '.cfg', '.ini', '.conf',
    '.md', '.txt', '.rst', '.sh', '.bat', '.ps1', '.cmd',
    '.sql', '.graphql', '.proto', '.xml', '.env', '.example',
    '.gitignore', '.dockerignore', '.editorconfig',
}

# Files to include even without extension match
INCLUDE_FILES = {
    'config', 'requirements', 'Dockerfile', 'Makefile',
    'main', '.gitignore', 'vocabulary',
    'PERFORMANCE_OPTIMIZATIONS.md', 'STRATEGIC_ANALYSIS.md',
}

# Directories to skip entirely
SKIP_DIRS = {
    '.git', '.cursor', '.vscode', '__pycache__', 'node_modules',
    '.mypy_cache', '.pytest_cache', '__pypackages__', '.venv',
    'venv', 'env', '.env', 'dist', 'build', '.eggs', '*.egg-info',
    '.tox', '.nox', 'logs',  # logs folder - skip bulk logs
}

# Files to skip
SKIP_FILES = {
    OUTPUT_FILE, 'FULL_PROJECT_DUMP', 'pack_project.py',
    'pack_code.py', '0.20.0', 'vocabulary',
}


def should_include_file(filepath: Path) -> bool:
    name = filepath.name
    if name in SKIP_FILES:
        return False
    if filepath.stat().st_size > MAX_FILE_SIZE_KB * 1024:
        return False
    if name in INCLUDE_FILES:
        return True
    if filepath.suffix.lower() in CODE_EXTENSIONS:
        return True
    # Include extensionless files that look like config/scripts
    if filepath.suffix == '' and filepath.stat().st_size < 10 * 1024:
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                first_line = f.readline()
                if first_line.startswith('#') or first_line.startswith('//'):
                    return True
        except:
            pass
    return False


def should_skip_dir(dirname: str) -> bool:
    return dirname in SKIP_DIRS or dirname.startswith('.')


def pack_project():
    root = Path('.')
    files_packed = []
    files_skipped = []
    total_chars = 0

    output_lines = []
    output_lines.append("=" * 80)
    output_lines.append(f"CYNEDIRECTOR v20 — FULL PROJECT DUMP")
    output_lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    output_lines.append("=" * 80)

    # First pass: collect directory tree
    output_lines.append("\n## DIRECTORY STRUCTURE\n")
    for dirpath, dirnames, filenames in os.walk(root):
        # Filter out skip dirs
        dirnames[:] = [d for d in dirnames if not should_skip_dir(d)]
        dirnames.sort()

        level = len(Path(dirpath).parts) - 1
        indent = "  " * level
        dirname = Path(dirpath).name if level > 0 else "CyneDirector_v20/"
        output_lines.append(f"{indent}📁 {dirname}/")
        
        for fname in sorted(filenames):
            fpath = Path(dirpath) / fname
            size_kb = fpath.stat().st_size / 1024
            output_lines.append(f"{indent}  📄 {fname} ({size_kb:.1f} KB)")

    # Second pass: dump file contents
    output_lines.append("\n" + "=" * 80)
    output_lines.append("## FILE CONTENTS")
    output_lines.append("=" * 80)

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not should_skip_dir(d)]
        dirnames.sort()

        for fname in sorted(filenames):
            fpath = Path(dirpath) / fname
            rel_path = fpath.relative_to(root)

            if not should_include_file(fpath):
                files_skipped.append(str(rel_path))
                continue

            try:
                with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
            except Exception as e:
                files_skipped.append(f"{rel_path} (read error: {e})")
                continue

            files_packed.append(str(rel_path))
            total_chars += len(content)

            output_lines.append(f"\n{'─' * 80}")
            output_lines.append(f"FILE: {rel_path}")
            output_lines.append(f"SIZE: {len(content)} chars | {fpath.stat().st_size / 1024:.1f} KB")
            output_lines.append(f"{'─' * 80}")
            output_lines.append(content)

    # Summary
    summary = []
    summary.append("\n" + "=" * 80)
    summary.append("## PACK SUMMARY")
    summary.append(f"Files included: {len(files_packed)}")
    summary.append(f"Files skipped:  {len(files_skipped)}")
    summary.append(f"Total chars:    {total_chars:,}")
    summary.append(f"Approx tokens:  ~{total_chars // 4:,}")
    summary.append("=" * 80)

    if files_skipped:
        summary.append("\nSkipped files:")
        for f in files_skipped[:30]:
            summary.append(f"  - {f}")
        if len(files_skipped) > 30:
            summary.append(f"  ... and {len(files_skipped) - 30} more")

    # Prepend summary right after header
    output_lines[4:4] = summary

    # Write
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write('\n'.join(output_lines))

    print(f"\n✅ Packed {len(files_packed)} files → {OUTPUT_FILE}")
    print(f"   Total: ~{total_chars:,} chars (~{total_chars // 4:,} tokens)")
    print(f"   Skipped: {len(files_skipped)} files")
    
    file_size = os.path.getsize(OUTPUT_FILE) / 1024
    print(f"   Output size: {file_size:.1f} KB")
    
    if total_chars > 400_000:
        print(f"\n⚠️  This is large (~{total_chars // 4:,} tokens).")
        print(f"   Claude can handle it, but consider uploading as a file")
        print(f"   rather than pasting into chat.")


if __name__ == "__main__":
    pack_project()