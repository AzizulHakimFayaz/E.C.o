import subprocess
import os

def run_terminal_command(command: str, cwd: str = None) -> dict:
    """
    Executes a shell command on the host OS.
    Captures stdout, stderr, and exit code.
    """
    if cwd and not os.path.exists(cwd):
        return {
            "success": False,
            "exit_code": -1,
            "output": f"Error: Working directory '{cwd}' does not exist."
        }
        
    try:
        # Use shell=True for windows commands. Pass environment.
        # Run with a 60 second timeout limit to prevent hanging commands.
        result = subprocess.run(
            command,
            cwd=cwd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=60,
            errors="ignore"
        )
        
        output = result.stdout + result.stderr
        success = (result.returncode == 0)
        
        return {
            "success": success,
            "exit_code": result.returncode,
            "output": output
        }
        
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "exit_code": -2,
            "output": "Error: Command execution timed out (limit: 60 seconds)."
        }
    except Exception as e:
        return {
            "success": False,
            "exit_code": -3,
            "output": f"Error running command: {e}"
        }

if __name__ == "__main__":
    # Test dir command
    res = run_terminal_command("dir", cwd=".")
    print(res["output"][:200])
