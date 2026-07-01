import subprocess
import os

def open_windows_app(app_name: str) -> dict:
    """
    Launches a Windows application by name.
    """
    # Mapping simple names to system executables
    app_mapping = {
        "notepad": "notepad.exe",
        "calc": "calc.exe",
        "calculator": "calc.exe",
        "explorer": "explorer.exe",
        "cmd": "cmd.exe",
        "powershell": "powershell.exe",
        "paint": "mspaint.exe",
        "mspaint": "mspaint.exe",
        "chrome": "chrome.exe",
        "edge": "msedge.exe",
        "firefox": "firefox.exe"
    }
    
    app_clean = app_name.lower().strip()
    executable = app_mapping.get(app_clean, app_clean)
    
    try:
        # Check standard subprocess.Popen execution
        # Use shell start commands if path is not absolute or in system PATH
        if app_clean in app_mapping or executable.endswith(".exe"):
            subprocess.Popen(executable, shell=True)
            return {
                "success": True,
                "message": f"Successfully requested launch of application: '{executable}'."
            }
        else:
            # Try launching via OS start protocol (for directories, URLs, files)
            os.startfile(app_name)
            return {
                "success": True,
                "message": f"Successfully launched system resource '{app_name}' via OS shell handler."
            }
    except Exception as e:
        # Fallback to start command via shell
        try:
            subprocess.Popen(f"start {app_name}", shell=True)
            return {
                "success": True,
                "message": f"Successfully launched '{app_name}' via fallback shell start command."
            }
        except Exception as err:
            return {
                "success": False,
                "message": f"Failed to launch application '{app_name}': {e} | Fallback err: {err}"
            }

if __name__ == "__main__":
    # Dry run calc launcher
    res = open_windows_app("calc")
    print(res)
