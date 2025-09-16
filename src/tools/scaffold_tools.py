import os

class ScaffoldTool:
    def __init__(self , base_dir="projects"):
        self.base_dir = base_dir
        os.makedirs(base_dir,exist_ok=True)

    def create_project(self,name : str, type_:str):
        """Generate a project scaffold"""
        project_path = os.path.join(self.base_dir,name)
        os.makedirs(project_path,exist_ok=True)

        if type_ == "python":
            self.create_project_scaffold(project_path)
        elif type_ == "react":
            self.create_project_scaffold(project_path)
        else:
            return f"Project type {type_} not supported yet."
        
        return f"✅ {type_.capitalize()} project created at {project_path}"
    
    def _create_python_scaffold(self,path):
        files = {
            "main.py" : "print('Hello from python project!')",
            "requirements.txt" : "#Add your dependencies here \n",
        }

        for fname , content in files.items():
            with open(os.path.join(path, fname),"w") as f:
                f.write(content)
    
    def _create_react_scaffold(self,path):
        os.makedirs(os.path.join(path,"src"), exist_ok=True)
        files = {
            "package.json": '{ "name": "react-app", "dependencies": {} }',
            "src/index.js": "console.log('Hello from React project!');"
        }
        for fname, content in files.items():
            with open(os.path.join(path, fname), "w") as f:
                f.write(content)