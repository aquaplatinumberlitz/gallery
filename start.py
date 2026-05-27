import os
import sys
import subprocess
import platform
import time
import webbrowser
import shutil
import socket
from pathlib import Path

# --- CONFIG ---
ROOT_DIR = Path(__file__).parent.resolve()
BACKEND_DIR = (ROOT_DIR / "backend").resolve()
FRONTEND_DIR = (ROOT_DIR / "frontend").resolve()
NODE_MODULES_DIR = FRONTEND_DIR / "node_modules"
OS_MARK_FILE = NODE_MODULES_DIR / ".os_mark"

BACKEND_PORT = 8000
FRONTEND_PORT = 5173

# --- PLATFORM DETECTION ---
OS_NAME = platform.system()
IS_WINDOWS = OS_NAME == "Windows"

print(f"Detected OS: {OS_NAME.upper()}")

def get_venv_path():
    venv_name = ".venv_win" if IS_WINDOWS else ".venv_linux"
    return BACKEND_DIR / venv_name

def get_python_exec(venv_path):
    if IS_WINDOWS:
        return venv_path / "Scripts" / "python.exe"
    return venv_path / "bin" / "python"

def get_pip_exec(venv_path):
    if IS_WINDOWS:
        return venv_path / "Scripts" / "pip.exe"
    return venv_path / "bin" / "pip"

def run_command(command, cwd=None, shell=False):
    try:
        if shell and isinstance(command, list):
            command = " ".join(command)
        subprocess.check_call(command, cwd=cwd, shell=shell)
    except subprocess.CalledProcessError as e:
        print(f"ERROR: Command failed: {e}")
        sys.exit(1)

# --- HANDLE node_modules ACROSS OSes ---
def check_node_modules_os():
    """Ensure node_modules matches the current OS.

    If node_modules was installed on a different OS, delete it so dependencies
    can be reinstalled correctly.
    """
    if not NODE_MODULES_DIR.exists():
        return True  # No install yet
    if not OS_MARK_FILE.exists():
        return True  # No marker, assume OK
    try:
        installed_os = OS_MARK_FILE.read_text().strip()
        if installed_os != OS_NAME:
            print(f"   WARNING: node_modules was installed on {installed_os}, current OS is {OS_NAME}. Reinstalling...")
            shutil.rmtree(NODE_MODULES_DIR, ignore_errors=True)
            return True
    except:
        pass
    return True

def mark_os():
    """Write OS marker for node_modules install."""
    try:
        OS_MARK_FILE.write_text(OS_NAME)
    except:
        pass

def find_free_port(start_port: int) -> int:
    port = start_port
    while port <= 65535:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                port += 1
    raise RuntimeError("No free port available.")

# -----------------------------------------------

def check_pip_health(pip_exec):
    """Return True if pip works for the current venv (detects moved/renamed venv)."""
    if not pip_exec.exists():
        return False
    try:
        # Run pip --version. If the venv was moved/renamed, this often fails.
        subprocess.run(
            [str(pip_exec), "--version"], 
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.DEVNULL, 
            check=True
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return False

def setup_backend():
    print("\n[1/4] Checking backend...")
    venv_path = get_venv_path()
    python_exec = get_python_exec(venv_path)
    pip_exec = get_pip_exec(venv_path)

    # Flag for recreating the venv
    need_create = False

    # 1) Check if venv exists
    if not venv_path.exists():
        print("   Virtual environment not found. Creating...")
        need_create = True
    else:
        # 2) If it exists, verify it's healthy (pip runnable)
        if not check_pip_health(pip_exec):
            print("   WARNING: Virtual environment looks broken (folder moved/renamed?).")
            print("   Recreating virtual environment...")
            try:
                shutil.rmtree(venv_path, ignore_errors=True)
            except Exception as e:
                print(f"   ERROR: Failed to delete old venv: {e}")
                # Try to continue and let venv creation overwrite if possible
            need_create = True
    
    # 3) Create venv if needed
    if need_create:
        print(f"   Creating virtual environment at: {venv_path}...")
        run_command([sys.executable, "-m", "venv", str(venv_path)])
        # Refresh paths after creation
        python_exec = get_python_exec(venv_path)
        pip_exec = get_pip_exec(venv_path)

    print("   Checking Python dependencies...")
    
    if not pip_exec.exists():
        print(f"ERROR: pip not found at {pip_exec} after creating venv.")
        sys.exit(1)

    # Check if requirements are already installed
    marker_file = venv_path / ".installed"
    requirements_file = BACKEND_DIR / "requirements.txt"
    
    # Check if requirements.txt was modified after last install
    should_install = need_create or not marker_file.exists()
    if not should_install and marker_file.exists() and requirements_file.exists():
        if requirements_file.stat().st_mtime > marker_file.stat().st_mtime:
            print("   WARNING: requirements.txt changed, updating dependencies...")
            should_install = True
    
    if not should_install:
        print("   Backend dependencies already installed.")
    else:
        print("   Installing Python requirements...")
        run_command([str(pip_exec), "install", "-r", "requirements.txt"], cwd=BACKEND_DIR)
        # Create/update marker file
        try:
            marker_file.write_text(str(time.time()))
        except:
            pass
            
    return python_exec

def setup_frontend():
    print("\n[2/4] Checking frontend...")
    
    check_node_modules_os()  # Deletes node_modules if it was installed on a different OS
    
    # Use npm to minimize external dependencies and keep installs consistent across machines.
    pkg_manager = "npm"

    print(f"   Using package manager: {pkg_manager.upper()}")

    # Check if need install
    install_marker = NODE_MODULES_DIR / ".last_install_time"
    package_json = FRONTEND_DIR / "package.json"
    
    should_install = (
        not NODE_MODULES_DIR.exists() or
        not install_marker.exists() or
        package_json.stat().st_mtime > install_marker.stat().st_mtime
    )

    if should_install:
        print("   Installing frontend packages...")
        run_command([pkg_manager, "install"], cwd=FRONTEND_DIR, shell=True)
        mark_os()
        try:
            install_marker.write_text(str(time.time()))
        except:
            pass
    else:
        print("   Frontend is ready.")
    
    return pkg_manager

def start_servers(python_exec, pkg_manager):
    print("\n[3/4] Starting servers...")

    backend_port = find_free_port(BACKEND_PORT)
    frontend_port = find_free_port(FRONTEND_PORT)
    if frontend_port == backend_port:
        frontend_port = find_free_port(frontend_port + 1)

    print(f"   Starting Backend API (Port {backend_port})...")
    backend_env = os.environ.copy()
    backend_env["PORT"] = str(backend_port)
    backend_env["FRONTEND_PORT"] = str(frontend_port)
    backend_cmd = [str(python_exec), "-m", "uvicorn", "main:app", "--reload", "--host", "127.0.0.1", "--port", str(backend_port)]
    backend_process = subprocess.Popen(backend_cmd, cwd=BACKEND_DIR, env=backend_env)

    time.sleep(3)

    print(f"   Starting Frontend Interface (Port {frontend_port})...")
    frontend_cmd = f"{pkg_manager} run dev"
    frontend_env = os.environ.copy()
    frontend_env["VITE_PORT"] = str(frontend_port)
    frontend_env["VITE_API_URL"] = f"http://127.0.0.1:{backend_port}"
    frontend_process = subprocess.Popen(frontend_cmd, cwd=FRONTEND_DIR, shell=True, env=frontend_env)

    return backend_process, frontend_process, backend_port, frontend_port

def main():
    try:
        python_exec = setup_backend()
        pkg_manager = setup_frontend()
        be_proc, fe_proc, be_port, fe_port = start_servers(python_exec, pkg_manager)

        print("\n[4/4] Opening browser...")
        time.sleep(2)
        webbrowser.open(f"http://localhost:{fe_port}")

        print("\nAll services are running.")
        print("Press Ctrl+C to stop.")

        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\nStopping...")
        try:
            be_proc.terminate()
            if IS_WINDOWS:
                subprocess.call(['taskkill', '/F', '/T', '/PID', str(fe_proc.pid)])
            else:
                fe_proc.terminate()
        except:
            pass
        sys.exit(0)

if __name__ == "__main__":
    main()
