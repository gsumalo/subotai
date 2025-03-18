import argparse
import os
import platform
import shutil
import subprocess
import tempfile
import yaml
from conan.api.conan_api import ConanAPI
from conan.cli.cli import Cli
from conan.cli.exit_codes import SUCCESS, ERROR_MIGRATION, ERROR_GENERAL, USER_CTRL_C, ERROR_SIGTERM, USER_CTRL_BREAK, ERROR_INVALID_CONFIGURATION, ERROR_UNEXPECTED
from jinja2 import Template
from sys import prefix

def parse(template, build_type):
    with open(template, "r") as file:
        yaml_template = file.read()
    
    context = {
        "os": platform.system().lower(),
        "build_type": build_type,
    }
    
    template = Template(yaml_template)
    
    return yaml.safe_load(template.render(context))

def generate_requirements(packages):
    scopes = {
        "all": "a",
        "build": "b",
        "host": "h"
    }
    
    requirements = []
    
    for package, versions in packages['packages'].items():
        for version, configs in versions.items():
            if configs is None:
                requirement = [f"--requires={package}/{version}"]
                requirements.append(requirement)
            else:
                for config in configs:
                    scope = scopes['all']
                    settings = []
                    configurations = []
                    options = []
                    tools = []
                    
                    if 'scope' in config:
                        scope = scopes[config['scope'].strip()]
                    
                    if 'settings' in config:
                        for setting in config['settings']:
                            safe_setting = setting.strip()
                            
                            if (len(safe_setting) > 0):
                                settings.append(f"-s:{scope}")
                                settings.append(safe_setting)

                    if 'configurations' in config:
                        for configuration in config['configurations']:
                            safe_conf = configuration.strip()
                            
                            if (len(safe_conf) > 0):
                                configurations.append(f"-c:{scope}")
                                configurations.append(safe_conf)
                    
                    if 'options' in config:
                        for option in config['options']:
                            safe_option = option.strip()
                            
                            if (len(safe_option) > 0):
                                options.append(f"-o:{scope}")
                                options.append(safe_option)
                    
                    if 'tool_requires' in config:
                        for tool in config['tool_requires']:
                            safe_tool = tool.strip()
                            
                            if (len(safe_tool) > 0):
                                tools.append(f"--tool-requires={safe_tool}")
                    
                    requirement = [f"--requires={package}/{version}"]
                    requirement += settings
                    requirement += configurations
                    requirement += options
                    requirement += tools
                    
                    requirements.append(requirement)
    
    return requirements

def generate_commands(build_type, profile, packages):
    commands = []
    
    prefix = ['install', '-pr:a', f"{profile}", '--build=missing', '-s', f"build_type={build_type}"]
    
    for requirement in generate_requirements(packages):
        command = []
        command += prefix
        command += requirement
        
        commands.append(command)

    return commands

def serialize_command(command):
    rv = "conan"
    
    for arg in command:
        rv += f" {arg}"
        
    return rv

def conan_main(args):
    print(f"EXECUTE: {serialize_command(args)}", flush=True)
    
    try:
        conan_api = ConanAPI()
    except ConanMigrationError:  # Error migrating
        sys.exit(ERROR_MIGRATION)
    except ConanException as e:
        sys.stderr.write("Error in Conan initialization: {}".format(e))
        sys.exit(ERROR_GENERAL)

    cli = Cli(conan_api)
    error = SUCCESS
    try:
        cli.run(args)
    except BaseException as e:
        error = cli.exception_exit_error(e)

    return error

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Package generator for Conan recipes based on YAML+Jinja2 specification',
                                     epilog="Akiro is the name of the wizard who invoked gods to bring Conan back to life.\n"
                                            "Subotai is the archer and thief who recovered Conan from the Tree of Woe.\n"
                                            "Both were more than wingmen of Conan and help him to achieve Crom's recognition")
    parser.add_argument('filename', nargs='?', default='subotai.yaml', help='file with the specification of packages (default: %(default)s)')
    parser.add_argument('-b', '--build_type', default='Release')
    parser.add_argument('-p', '--profile', default='default')
    parser.add_argument('--dry-run', action='store_true', help='print the list of generated commands and exit')
    parser.add_argument('--generate-built-list', action='store_true', help='generate JSON file with the list of the built packages')
    parser.add_argument('--parse-only', action='store_true', help='check the syntax of the specification file and exit')
    args = parser.parse_args()
    
    packages = parse(args.filename, args.build_type);
    
    if args.parse_only:
        print(packages)
    else:
        commands = generate_commands(args.build_type, args.profile, packages)

        if args.dry_run:
            for command in commands:
                print(serialize_command(command))
        elif args.generate_built_list:
            first_command = True
            final_built_file = 'built.json'
            
            for command in commands:
                graph_file = tempfile.NamedTemporaryFile()
                graph_file_name = graph_file.name
                built_file = tempfile.NamedTemporaryFile()
                built_file_name = built_file.name
                merge_file = tempfile.NamedTemporaryFile()
                merge_file_name = merge_file.name
                
                try:
                    graph_file.close()
                    built_file.close()
                    merge_file.close()
                    
                    extended_command = []
                    extended_command += command
                    extended_command += ['--format=json', f"--out-file={graph_file_name}"]
                    conan_main(extended_command)
                    
                    list_built_command = ["list", f"--graph={graph_file.name}", "--graph-binaries=build", "--format=json", f"--out-file={built_file_name}"]
                    conan_main(list_built_command)
                    
                    if first_command:
                        shutil.copy(built_file_name, final_built_file)
                        first_command = False
                    else:
                        shutil.copy(final_built_file, merge_file_name)
                        merge_list_command = ["pkglist", "merge", f"--list={merge_file_name}", f"--list={built_file_name}", "--format=json", f"--out-file={final_built_file}"]
                        conan_main(merge_list_command)
                        
                finally:
                    os.remove(graph_file_name)
                    os.remove(built_file_name)
                    
                    if os.path.exists(merge_file_name):
                        os.remove(merge_file_name)
        else:
            for command in commands:
                conan_main(command)
