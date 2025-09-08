import yaml as yaml
import platform

# Following block import a base-configuration yaml file which works on all the platforms as same 
# # The configuration is stored in the configs directory inside the root directory
# configs/base-config.yml 
with open("../configs/base-config.yml", "r") as base_config:
    base_config_obj = yaml.safe_load(base_config)

# Creating the config string object with the right platform's configuration file
match platform.system().lower():
    case 'linux':
         config = 'linux-config.yml'
    case 'windows':
        config = 'windows-config.yml'

# Following block import a platform-configuration yaml file which is a platform specific 
# The configuration is stored in the configs directory inside the root directory
# configs/{name-of-platform}.yml
with open(f"../configs/{config}") as system_config:
    system_config_obj = yaml.safe_load(system_config)
