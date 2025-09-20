from langchain_core.tools import tool
import subprocess
import json
import shutil
from pathlib import Path

BASE_DIR = Path("/home/vanshdubey/synthra/projects")
BASE_DIR.mkdir(exist_ok=True)

def _project_dir(project_id: str) -> Path:
    return BASE_DIR / project_id

@tool
def write_files(project_id: str, files_map: str) -> str:
    """Create or update multiple files in the project directory.
    
    Args:
        project_id: The project identifier (REQUIRED - ask user if not provided)
        files_map: JSON string mapping file paths to their content
    
    Returns:
        str: Status message about files written
    """
    if not project_id:
        return "ERROR: project_id is required. Please provide the project identifier."
    
    base = _project_dir(project_id)
    base.mkdir(parents=True, exist_ok=True)
    
    if isinstance(files_map, str):
        try:
            fm = json.loads(files_map)
        except json.JSONDecodeError:
            return "ERROR: write_files: files_map not valid JSON"
    else:
        fm = files_map
    
    written = []
    for rel, content in fm.items():
        target = base / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        written.append(rel)
    
    return f"✅ Project '{project_id}': Wrote {len(written)} files: {written}"

@tool  
def run_shell(project_id: str, cmd: str) -> str:
    """Execute shell commands in the project directory.
    
    Args:
        project_id: The project identifier (REQUIRED - ask user if not provided)
        cmd: Shell command to execute
    
    Returns:
        str: Command output or error message
    """
    if not project_id:
        return "ERROR: project_id is required. Please provide the project identifier."
        
    base = _project_dir(project_id)
    base.mkdir(parents=True, exist_ok=True)
    
    try:
        result = subprocess.run(
            cmd, 
            shell=True, 
            cwd=base, 
            capture_output=True, 
            text=True, 
            check=True
        )
        return f"✅ Project '{project_id}' command result: {result.stdout.strip() or '(no output)'}"
    except subprocess.CalledProcessError as e:
        return f"❌ Project '{project_id}' ERROR (exit {e.returncode}): {e.stderr}"

@tool
def list_files(project_id: str) -> str:
    """List all files in the project directory.
    
    Args:
        project_id: The project identifier (REQUIRED - ask user if not provided)
    
    Returns:
        str: JSON string of file paths
    """
    if not project_id:
        return "ERROR: project_id is required. Please provide the project identifier."
        
    base = _project_dir(project_id)
    if not base.exists():
        return json.dumps([])
    
    files = [
        str(p.relative_to(base).as_posix()) 
        for p in base.rglob("*") 
        if p.is_file()
    ]
    return f"✅ Project '{project_id}' files: {json.dumps(files)}"

@tool
def archive_project(project_id: str) -> str:
    """Archive the project and mark as closed.
    
    Args:
        project_id: The project identifier (REQUIRED - ask user if not provided)
    
    Returns:
        str: Archive status message
    """
    if not project_id:
        return "ERROR: project_id is required. Please provide the project identifier."
        
    base = _project_dir(project_id)
    if not base.exists():
        return f"ERROR: project '{project_id}' does not exist"
    
    archive_path = BASE_DIR / f"{project_id}_archive.zip"
    shutil.make_archive(str(archive_path.with_suffix('')), 'zip', base)
    return f"✅ ARCHIVED project '{project_id}': {archive_path}"

tools = [write_files, run_shell, list_files, archive_project]