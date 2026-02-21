#!/usr/bin/env python3
import sys
import os
import subprocess
import importlib.util

def check_python_version() -> bool:
    print(f"[*] Checking Python version... {sys.version.split()[0]}")
    if sys.version_info < (3, 10):
        print("[!] Error: Python 3.10+ is required.")
        return False
    return True

def check_venv() -> bool:
    print("[*] Checking for virtual environment...")
    in_venv = sys.prefix != sys.base_prefix
    if not in_venv:
        print("[!] Warning: Not running in a virtual environment. Please run 'make venv' and activate it.")
        # We don't return False here as it might be running in a container or global env
    else:
        print(f"[*] Running in venv: {sys.prefix}")
    return True

def check_dependencies() -> bool:
    print("[*] Checking core dependencies...")
    required = [
        "fastapi", "celery", "sqlalchemy", "pydantic", "pytest", 
        "psycopg2", "asyncpg", "redis", "alembic", "httpx"
    ]
    missing = []
    for pkg in required:
        # Some packages have different import names
        import_name = pkg
        if pkg == "psycopg2":
            import_name = "psycopg2"
        elif pkg == "asyncpg":
            import_name = "asyncpg"
            
        try:
            importlib.import_module(import_name)
        except ImportError:
            missing.append(pkg)
    
    if missing:
        print(f"[!] Error: Missing dependencies: {', '.join(missing)}")
        print("[!] Please run 'pip install -r requirements.txt'")
        return False
    print("[*] Core dependencies found.")
    return True

def check_config_files() -> bool:
    print("[*] Checking configuration files...")
    files = [".env", "Makefile", "docker-compose.yml", "alembic.ini"]
    missing = [f for f in files if not os.path.exists(f)]
    
    if missing:
        print(f"[!] Warning: Missing files: {', '.join(missing)}")
    else:
        print("[*] Essential config files present.")
    return True

def run_simple_test() -> bool:
    print("[*] Running a sanity unit test...")
    try:
        # Just check if we can run pytest on a simple unit test
        result = subprocess.run(
            ["pytest", "tests/unit/test_schemas.py", "-v", "--maxfail=1"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            print("[*] Sanity test passed.")
            return True
        else:
            print("[!] Sanity test failed.")
            print(result.stdout)
            return False
    except FileNotFoundError:
        print("[!] Error: 'pytest' not found in PATH.")
        return False

def check_services() -> None:
    print("[*] Checking infrastructure services (if reachable)...")
    # This is optional and might fail if services are not up
    try:
        import redis
        r = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
        r.ping()
        print("[*] Redis is reachable.")
    except Exception:
        print("[ ] Redis is not reachable (expected if infrastructure is not running).")

def main():
    print("=== Whisper Agent Health Check ===\n")
    checks = [
        check_python_version,
        check_venv,
        check_dependencies,
        check_config_files,
        run_simple_test
    ]
    
    all_passed = True
    for check in checks:
        if not check():
            all_passed = False
            print("-" * 30)
    
    check_services()
    
    print("\n" + "=" * 30)
    if all_passed:
        print("✅ REPO IS READY FOR AGENT TASKS")
    else:
        print("❌ REPO HAS SOME ISSUES. PLEASE RECTIFY BEFORE PROCEEDING.")
    print("=" * 30)
    
    sys.exit(0 if all_passed else 1)

if __name__ == "__main__":
    main()
