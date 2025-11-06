"""Tools for code review agent - file analysis, git inspection, and linting."""
from langchain_core.tools import tool
import subprocess
import json
from pathlib import Path
import os
from collections import defaultdict


@tool
def list_project_files(project_id: str, root_path: str) -> str:
    """List all files in the project directory recursively.
    
    Args:
        project_id: The project identifier (REQUIRED)
        root_path: Absolute path to the project directory
    
    Returns:
        str: JSON string containing list of all file paths
    """
    if not project_id:
        return "ERROR: project_id is required"
    
    base = Path(root_path)
    if not base.exists():
        return json.dumps({"error": f"Path does not exist: {root_path}", "files": []})
    
    if not base.is_dir():
        return json.dumps({"error": f"Path is not a directory: {root_path}", "files": []})
    
    try:
        files = []
        for p in base.rglob("*"):
            if p.is_file():
                # Skip common binaries and build artifacts
                if any(skip in str(p) for skip in ['.git/', '__pycache__/', 'node_modules/', '.venv/', 'venv/', 'dist/', 'build/']):
                    continue
                files.append(str(p.as_posix()))
        
        return json.dumps({"files": files, "count": len(files)})
    except Exception as e:
        return json.dumps({"error": str(e), "files": []})


@tool
def read_file(project_id: str, file_path: str) -> str:
    """Read the content of a specific file.
    
    Args:
        project_id: The project identifier (REQUIRED)
        file_path: Absolute path to the file
    
    Returns:
        str: File content or error message
    """
    if not project_id:
        return "ERROR: project_id is required"
    
    try:
        path = Path(file_path)
        if not path.exists():
            return f"ERROR: File not found at {file_path}"
        
        if not path.is_file():
            return f"ERROR: Path is not a file: {file_path}"
        
        # Check file size (skip very large files)
        size_mb = path.stat().st_size / (1024 * 1024)
        if size_mb > 5:
            return f"ERROR: File too large ({size_mb:.2f}MB). Skipping to avoid memory issues."
        
        content = path.read_text(encoding="utf-8", errors="replace")
        return content
    except Exception as e:
        return f"ERROR reading {file_path}: {str(e)}"


@tool
def analyze_project_structure(project_id: str, root_path: str) -> str:
    """Analyze project structure and detect frameworks, languages, and architecture patterns.
    
    Args:
        project_id: The project identifier (REQUIRED)
        root_path: Absolute path to the project directory
    
    Returns:
        str: JSON string with project structure analysis
    """
    if not project_id:
        return "ERROR: project_id is required"
    
    base = Path(root_path)
    if not base.exists():
        return json.dumps({"error": "Path does not exist"})
    
    try:
        analysis = {
            "languages": defaultdict(int),
            "frameworks": [],
            "architecture": "unknown",
            "config_files": [],
            "total_files": 0,
            "directories": []
        }
        
        # Language extensions mapping
        lang_ext = {
            ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
            ".jsx": "React", ".tsx": "React/TypeScript", ".java": "Java",
            ".cpp": "C++", ".c": "C", ".go": "Go", ".rs": "Rust",
            ".rb": "Ruby", ".php": "PHP", ".cs": "C#", ".swift": "Swift",
            ".kt": "Kotlin", ".scala": "Scala", ".html": "HTML", ".css": "CSS"
        }
        
        # Framework/config file indicators
        framework_indicators = {
            "package.json": "Node.js/npm",
            "requirements.txt": "Python/pip",
            "Pipfile": "Python/pipenv",
            "pyproject.toml": "Python/Poetry",
            "Cargo.toml": "Rust/Cargo",
            "go.mod": "Go Modules",
            "pom.xml": "Java/Maven",
            "build.gradle": "Java/Gradle",
            "composer.json": "PHP/Composer",
            "Gemfile": "Ruby/Bundler",
            "docker-compose.yml": "Docker Compose",
            "Dockerfile": "Docker"
        }
        
        # Scan directory structure
        for p in base.rglob("*"):
            if p.is_file():
                # Skip build artifacts
                if any(skip in str(p) for skip in ['__pycache__', 'node_modules', '.git', '.venv', 'venv', 'dist', 'build']):
                    continue
                
                analysis["total_files"] += 1
                
                # Detect language by extension
                suffix = p.suffix.lower()
                if suffix in lang_ext:
                    analysis["languages"][lang_ext[suffix]] += 1
                
                # Detect frameworks by config files
                if p.name in framework_indicators:
                    analysis["frameworks"].append(framework_indicators[p.name])
                    analysis["config_files"].append(p.name)
        
        # Detect architecture pattern
        dirs = [d.name for d in base.iterdir() if d.is_dir() and not d.name.startswith('.')]
        analysis["directories"] = dirs
        
        if "services" in dirs or "microservices" in dirs:
            analysis["architecture"] = "Microservices"
        elif "src" in dirs or "lib" in dirs:
            analysis["architecture"] = "Modular"
        elif len(dirs) < 3:
            analysis["architecture"] = "Monolithic"
        else:
            analysis["architecture"] = "Mixed/Custom"
        
        # Convert defaultdict to regular dict for JSON serialization
        analysis["languages"] = dict(analysis["languages"])
        
        return json.dumps(analysis, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def git_analysis(project_id: str, root_path: str) -> str:
    """Analyze git repository history, commits, and contributors.
    
    Args:
        project_id: The project identifier (REQUIRED)
        root_path: Absolute path to the project directory
    
    Returns:
        str: JSON string with git analysis results
    """
    if not project_id:
        return "ERROR: project_id is required"
    
    git_dir = os.path.join(root_path, ".git")
    if not os.path.exists(git_dir):
        return json.dumps({"is_git_repo": False, "message": "No git repository found"})
    
    try:
        # Get commit count
        commit_count = subprocess.run(
            ["git", "rev-list", "--count", "HEAD"],
            cwd=root_path, capture_output=True, text=True, check=True
        ).stdout.strip()
        
        # Get commit log
        log_result = subprocess.run(
            ["git", "log", "--pretty=format:%h|%an|%ae|%ad|%s", "--date=short", "-50"],
            cwd=root_path, capture_output=True, text=True, check=True
        ).stdout
        
        commits = []
        for line in log_result.strip().split("\n"):
            if line:
                parts = line.split("|")
                if len(parts) == 5:
                    commits.append({
                        "hash": parts[0],
                        "author": parts[1],
                        "email": parts[2],
                        "date": parts[3],
                        "message": parts[4]
                    })
        
        # Get contributor stats
        contributors = subprocess.run(
            ["git", "shortlog", "-sn", "--all"],
            cwd=root_path, capture_output=True, text=True, check=True
        ).stdout
        
        contributor_list = []
        for line in contributors.strip().split("\n"):
            parts = line.strip().split("\t")
            if len(parts) == 2:
                contributor_list.append({"commits": int(parts[0]), "name": parts[1]})
        
        # Get branch info
        branches = subprocess.run(
            ["git", "branch", "-a"],
            cwd=root_path, capture_output=True, text=True, check=True
        ).stdout.strip().split("\n")
        
        return json.dumps({
            "is_git_repo": True,
            "total_commits": int(commit_count),
            "recent_commits": commits[:10],
            "contributors": contributor_list,
            "branches": [b.strip().replace("* ", "") for b in branches],
            "commit_sample_size": len(commits)
        }, indent=2)
    except Exception as e:
        return json.dumps({"is_git_repo": True, "error": str(e)})


@tool
def lint_code_file(project_id: str, file_path: str) -> str:
    """Run appropriate linter on a code file.
    
    Args:
        project_id: The project identifier (REQUIRED)
        file_path: Absolute path to the file
    
    Returns:
        str: Linting results or error message
    """
    if not project_id:
        return "ERROR: project_id is required"
    
    path = Path(file_path)
    if not path.exists():
        return "ERROR: File not found"
    
    suffix = path.suffix.lower()
    
    try:
        # Python files
        if suffix == ".py":
            result = subprocess.run(
                ["flake8", "--max-line-length=120", file_path],
                capture_output=True, text=True, timeout=10
            )
            output = result.stdout.strip()
            return output if output else "✅ No linting issues found"
        
        # JavaScript/TypeScript files
        elif suffix in [".js", ".jsx", ".ts", ".tsx"]:
            result = subprocess.run(
                ["eslint", file_path],
                capture_output=True, text=True, timeout=10
            )
            output = result.stdout.strip()
            return output if output else "✅ No linting issues found"
        
        else:
            return f"No linter configured for {suffix} files"
            
    except FileNotFoundError:
        return f"Linter not installed for {suffix} files"
    except subprocess.TimeoutExpired:
        return "Linting timed out"
    except Exception as e:
        return f"Linting error: {str(e)}"


@tool
def get_file_metrics(project_id: str, file_path: str) -> str:
    """Get detailed metrics for a code file (lines, complexity indicators).
    
    Args:
        project_id: The project identifier (REQUIRED)
        file_path: Absolute path to the file
    
    Returns:
        str: JSON string with file metrics
    """
    if not project_id:
        return "ERROR: project_id is required"
    
    try:
        path = Path(file_path)
        if not path.exists() or not path.is_file():
            return json.dumps({"error": "File not found"})
        
        content = path.read_text(encoding="utf-8", errors="replace")
        lines = content.split("\n")
        
        metrics = {
            "file": file_path,
            "total_lines": len(lines),
            "non_empty_lines": len([l for l in lines if l.strip()]),
            "comment_lines": 0,
            "file_size_kb": path.stat().st_size / 1024,
            "functions": 0,
            "classes": 0
        }
        
        suffix = path.suffix.lower()
        
        # Python-specific analysis
        if suffix == ".py":
            metrics["comment_lines"] = len([l for l in lines if l.strip().startswith("#")])
            metrics["functions"] = len([l for l in lines if l.strip().startswith("def ")])
            metrics["classes"] = len([l for l in lines if l.strip().startswith("class ")])
        
        # JavaScript/TypeScript analysis
        elif suffix in [".js", ".jsx", ".ts", ".tsx"]:
            metrics["comment_lines"] = len([l for l in lines if l.strip().startswith("//")])
            metrics["functions"] = content.count("function ") + content.count("=> ")
            metrics["classes"] = content.count("class ")
        
        return json.dumps(metrics, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


# Export all tools
tools = [
    list_project_files,
    read_file,
    analyze_project_structure,
    git_analysis,
    lint_code_file,
    get_file_metrics
]
