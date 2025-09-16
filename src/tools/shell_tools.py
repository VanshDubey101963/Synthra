import subprocess
import yaml

class ShellTool: 
    def __init__(self , config_path = "configs/mac.config.yml"):
        with open(config_path , "r") as f:
            self.config = yaml.safe_load(f)

    def run_command(self , command : str):
        """Run a shell command directly"""
        try:
            result = subprocess.run(command ,shell=True, capture_output=True, text=True)
            return result.stdout.strip() if result.stdout else result.stderr.strip()
        except Exception as e:
            return str(e)
        
    def open_app(self , app_key : str):
        """Open an application using the bindings in YAML"""
        app_bindings = self.config.get("app_bindings",{})
        if app_key in app_bindings:
            path = app_bindings[app_key]
            return self.run_command(f'open "{path}"')
        return f"App '{app_key}' not found in config."
