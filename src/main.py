from tools.shell_tools import ShellTool
from tools.scaffold_tools import ScaffoldTool

# def main():
#     pass

# if __name__ == "main":
#     main()

if __name__ == "__main__":
    # Shell tool
    shell = ShellTool()
    print(shell.open_app("browser"))  # Opens Chrome (from config)
    print(shell.run_command("ls"))    # Runs shell command

    # Scaffold tool
    scaffold = ScaffoldTool()
    print(scaffold.create_project("test_app", "python"))
    print(scaffold.create_project("frontend", "react"))
