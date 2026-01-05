import pytest
import shutil
import subprocess
from pathlib import Path
import os
import json

@pytest.fixture(scope="session")
def act_bin():
    """Find the act binary."""
    # Check for act in PATH
    act_path = shutil.which("act")
    if not act_path:
        pytest.skip("act not installed on this system")
    return act_path

@pytest.fixture(scope="session")
def project_root():
    """Return the absolute path to the project root."""
    # Assumes tests/act_integration is 2 levels deep from root
    return Path(__file__).parent.parent.parent.resolve()

@pytest.fixture
def run_act(act_bin, project_root, tmp_path):
    """Fixture to run act with simplified arguments and git isolation."""
    
    def _run(workflow=None, job=None, event_file=None, event_payload=None, secrets=None, env=None, dry_run=False, isolate=True):
        """
        Run act with specified parameters.
        
        Args:
            workflow: Path to workflow file (relative to project root)
            job: Job name to run
            event_file: Path to existing event.json file
            event_payload: Dict to write to a temporary event.json file
            secrets: Dict of secrets to pass (or list of names to pass from env)
            env: Dict of env vars to pass
            dry_run: If True, uses -n flag (dry run)
            isolate: If True (default), copies repo to temp dir to avoid git mutation
            
        Returns:
            subprocess.CompletedProcess
        """
        # Determine working directory
        work_dir = project_root
        
        if isolate:
            # Create a sandboxed copy of the repo
            # Use build/act_sandbox inside project root to ensure Docker/Colima can mount it
            # (System tmp dirs are often not shared with Docker VM on macOS)
            sandbox_root = project_root / "build" / "act_sandbox"
            sandbox_root.mkdir(parents=True, exist_ok=True)
            
            # Use tmp_path.name (e.g., test_function_name0) for uniqueness
            sandbox_dir = sandbox_root / tmp_path.name
            
            # Clean up previous run if exists
            if sandbox_dir.exists():
                shutil.rmtree(sandbox_dir)
            
            # Define what to ignore to keep copy fast
            ignore = shutil.ignore_patterns(
                ".venv", "venv", ".git/worktrees", 
                "__pycache__", "node_modules", "output",
                "*.pyc", ".pytest_cache", "build"
            )
            
            # Copy the project root to sandbox
            shutil.copytree(project_root, sandbox_dir, ignore=ignore, dirs_exist_ok=True)
            
            # Ensure sandbox is a valid git repo (handle worktrees or missing .git)
            # This is critical for act/actions that use git commands
            git_dir = sandbox_dir / ".git"
            if not git_dir.is_dir():
                if git_dir.exists():
                    os.remove(git_dir) # Remove worktree file if it exists
                
                # Initialize fresh repo to satisfy git dependencies
                subprocess.run(["git", "init"], cwd=sandbox_dir, check=True)
                subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=sandbox_dir, check=True)
                subprocess.run(["git", "config", "user.name", "Test User"], cwd=sandbox_dir, check=True)
                subprocess.run(["git", "add", "."], cwd=sandbox_dir, check=True)
                subprocess.run(["git", "commit", "-m", "Sandbox setup"], cwd=sandbox_dir, check=True)
                
            work_dir = sandbox_dir

        # Helper: Create event file from payload
        temp_event_file = None
        if event_payload:
            temp_event_file = tmp_path / "simulated_event.json"
            temp_event_file.write_text(json.dumps(event_payload))
            event_file = temp_event_file

        cmd = [act_bin]
        
        # Colima socket (minimal check)
        if hasattr(shutil, 'which') and shutil.which("colima"):
             pass
                
        # Basic args
        if workflow:
            # act expect -W to be either a directory or file.
            # If we are in sandbox (cwd), relative path works?
            # Safer to use absolute path within the workspace
            # BUT if we are isolated, we must point to the workflow IN THE SANDBOX?
            # Or the original one?
            # act mounts the cwd.
            # If we use -W absolute_path_to_original, act might get confused about context.
            # It's best to rely on act finding workflows in CWD/.github/workflows if -W not passed
            # OR pass relative path.
            
            # Use relative path if possible
            cmd.extend(["-W", str(workflow)])
            
        if job:
            cmd.extend(["-j", job])
            
        if dry_run:
            cmd.append("-n")
            
        # Secrets
        secrets_to_use = secrets
        if secrets_to_use is None:
             # Check for .secrets file in project root (gitignored)
             # User requested checking ".env (gitignored)", often named .secrets in this repo context
             # I'll check both just in case, prioritizing .secrets as established
             for potential_secret_file in [".secrets", ".env"]:
                 secrets_path = project_root / potential_secret_file
                 if secrets_path.exists():
                     secrets_to_use = {}
                     try:
                         for line in secrets_path.read_text().splitlines():
                             line = line.strip()
                             if not line or line.startswith("#"):
                                 continue
                             if "=" in line:
                                 k, v = line.split("=", 1)
                                 secrets_to_use[k.strip()] = v.strip()
                         break # Stop after finding first valid file
                     except Exception:
                         pass

        if secrets_to_use:
            if isinstance(secrets_to_use, list):
                for name in secrets_to_use:
                    cmd.extend(["-s", name])
            elif isinstance(secrets_to_use, dict):
                for k, v in secrets_to_use.items():
                    cmd.extend(["-s", f"{k}={v}"])
                    
        # Env vars
        if env:
            for k, v in env.items():
                cmd.extend(["--env", f"{k}={v}"])
                
        # Event file
        if event_file:
            cmd.extend(["-e", str(event_file)])
            
        cmd.extend(["--container-architecture", "linux/amd64"])
        
        # Debugging: verify sandbox content
        # print(f"DEBUG: Sandbox content: {[x.name for x in work_dir.iterdir()]}")
        
        print(f"Running command: {' '.join(cmd)}")
        print(f"Working directory: {work_dir}")
        print(f"Environment: {env}")
        
        return subprocess.run(
            cmd,
            cwd=work_dir,
            capture_output=True,
            text=True,
            env={**os.environ}
        )
        
    return _run
