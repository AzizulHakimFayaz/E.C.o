import os
import fnmatch

def search_folder(directory: str = ".", pattern: str = "*", recursive: bool = True) -> list[dict]:
    """
    Scans a folder recursively and returns list of files matching pattern.
    """
    found_files = []
    
    # Exclude directories
    exclude_dirs = {".git", ".venv", "venv", "env", "__pycache__", "node_modules", "chroma_db"}
    
    try:
        if recursive:
            for root, dirs, files in os.walk(directory):
                # Filter out excluded directories in-place
                dirs[:] = [d for d in dirs if d not in exclude_dirs and not d.startswith('.')]
                
                for file in files:
                    if fnmatch.fnmatch(file.lower(), pattern.lower()) or pattern in file:
                        full_path = os.path.join(root, file)
                        rel_path = os.path.relpath(full_path, directory).replace("\\", "/")
                        found_files.append({
                            "path": rel_path,
                            "absolute_path": os.path.abspath(full_path),
                            "size_bytes": os.path.getsize(full_path)
                        })
        else:
            for file in os.listdir(directory):
                full_path = os.path.join(directory, file)
                if os.path.isfile(full_path):
                    if fnmatch.fnmatch(file.lower(), pattern.lower()) or pattern in file:
                        found_files.append({
                            "path": file,
                            "absolute_path": os.path.abspath(full_path),
                            "size_bytes": os.path.getsize(full_path)
                        })
                        
        return found_files
        
    except Exception as e:
        print(f"[Folder Search Tool] Error searching path '{directory}': {e}")
        return []

if __name__ == "__main__":
    # Test scan
    res = search_folder(".", "*.py")
    for r in res[:5]:
        print(r)
