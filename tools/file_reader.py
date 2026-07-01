import os

def read_local_file(filepath: str, start_line: int = 1, end_line: int = 250) -> str:
    """
    Reads contents of a local text or code file within specified line limits.
    """
    if not os.path.exists(filepath):
        return f"Error: File does not exist at path '{filepath}'."
        
    try:
        # Check size to avoid reading massive binary records
        file_size = os.path.getsize(filepath)
        if file_size > 10 * 1024 * 1024:  # >10 MB
            return f"Error: File size is too large ({file_size / (1024*1024):.2f} MB). Skipping content read."
            
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
            
        total_lines = len(lines)
        if start_line < 1:
            start_line = 1
        if end_line > total_lines:
            end_line = total_lines
            
        if start_line > total_lines:
            return f"Error: Start line {start_line} is greater than total file lines ({total_lines})."
            
        output = [
            f"FILE PATH: {os.path.abspath(filepath)}",
            f"TOTAL LINES: {total_lines}",
            f"SHOWING RANGE: Line {start_line} to {end_line}",
            "--- FILE CONTENT START ---"
        ]
        
        # 1-indexed slicing
        for idx in range(start_line - 1, end_line):
            output.append(f"{idx + 1:4d} | {lines[idx].rstrip()}")
            
        output.append("--- FILE CONTENT END ---")
        return "\n".join(output)
        
    except Exception as e:
        return f"Error reading file: {e}"

if __name__ == "__main__":
    # Test read on current file
    print(read_local_file(__file__, 1, 15))
