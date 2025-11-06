"""Main entry point for Synthra code review agent."""
import sys
import os
from pathlib import Path
import uuid

# Add src to path if needed
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.agents.review_agent.agent import interact


def print_banner():
    """Print Synthra review agent banner."""
    banner = """
╔═══════════════════════════════════════════════════════════════╗
║                                                               ║
║   ███████╗██╗   ██╗███╗   ██╗████████╗██╗  ██╗██████╗  █████╗║
║   ██╔════╝╚██╗ ██╔╝████╗  ██║╚══██╔══╝██║  ██║██╔══██╗██╔══██╗║
║   ███████╗ ╚████╔╝ ██╔██╗ ██║   ██║   ███████║██████╔╝███████║║
║   ╚════██║  ╚██╔╝  ██║╚██╗██║   ██║   ██╔══██║██╔══██╗██╔══██║║
║   ███████║   ██║   ██║ ╚████║   ██║   ██║  ██║██║  ██║██║  ██║║
║   ╚══════╝   ╚═╝   ╚═╝  ╚═══╝   ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝║
║                                                               ║
║              CODE REVIEW AGENT - Powered by AI               ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝
"""
    print(banner)


def validate_path(path_str: str) -> Path:
    """Validate and return Path object."""
    path = Path(path_str).expanduser().resolve()
    
    if not path.exists():
        print(f"❌ Error: Path does not exist: {path}")
        sys.exit(1)
    
    if not path.is_dir():
        print(f"❌ Error: Path is not a directory: {path}")
        sys.exit(1)
    
    return path


def main():
    """Main function to run code review agent."""
    print_banner()
    
    print("Welcome to Synthra Code Review Agent!")
    print("This agent will analyze your codebase and provide detailed feedback.\n")
    
    # Get project path from user
    if len(sys.argv) > 1:
        project_path_str = sys.argv[1]
    else:
        project_path_str = input("📁 Enter the absolute path of the project to review: ").strip()
    
    if not project_path_str:
        print("❌ Error: No path provided")
        sys.exit(1)
    
    # Validate path
    project_path = validate_path(project_path_str)
    
    # Generate unique project ID
    project_id = f"review-{uuid.uuid4().hex[:8]}"
    
    # Get review scope (optional customization)
    print("\n🔧 Review Configuration:")
    print("  [1] Full comprehensive review (default)")
    print("  [2] Quick architecture overview")
    print("  [3] Focus on code quality and linting")
    print("  [4] Git history analysis only")
    
    choice = input("\nSelect review type (press Enter for full review): ").strip()
    
    # Prepare user input based on choice
    review_prompts = {
        "1": "Perform a comprehensive code review covering all aspects: architecture, code quality, git history, metrics, and provide detailed recommendations.",
        "2": "Provide a quick architecture overview focusing on project structure, frameworks used, and high-level organization.",
        "3": "Focus on code quality analysis: run linters, check for code smells, and suggest improvements for key files.",
        "4": "Analyze the git repository: commit history, contributors, branch structure, and development patterns."
    }
    
    user_input = review_prompts.get(choice, review_prompts["1"])
    
    print(f"\n🚀 Starting review of: {project_path}")
    print(f"📋 Review Type: {user_input[:80]}...\n")
    
    # Run the review agent
    try:
        result = interact(
            project_id=project_id,
            project_path=str(project_path),
            user_input=user_input
        )
        print(f"\n{result}")
    except KeyboardInterrupt:
        print("\n\n⚠️  Review interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n\n❌ Fatal error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
