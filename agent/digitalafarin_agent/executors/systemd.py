import re
import subprocess
import os
from pathlib import Path

from digitalafarin_agent.redaction import redact


SAFE_FILE = re.compile(r"^[A-Za-z0-9_.-]+$")
SAFE_SCRIPT = re.compile(r"^[A-Za-z0-9:_-]+$")
SAFE_MODULE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")
SAFE_UNIT = re.compile(r"^[A-Za-z0-9_.@:-]+\.service$")


class RecipeError(RuntimeError):
    pass


class SystemdExecutor:
    name = "systemd"

    def recipe_commands(
        self,
        runtime: str,
        install_configuration: dict,
        build_configuration: dict,
        root_directory: str,
    ) -> list[list[str]]:
        if runtime == "node-nextjs":
            if set(install_configuration) - {"package_manager", "lockfile"}:
                raise RecipeError("unsupported Node install configuration")
            if set(build_configuration) - {"build_script"}:
                raise RecipeError("unsupported Node build configuration")
            manager = install_configuration.get("package_manager", "npm")
            script = build_configuration.get("build_script", "build")
            if manager != "npm" or not SAFE_SCRIPT.fullmatch(script):
                raise RecipeError("invalid Node recipe")
            install_action = "ci" if install_configuration.get("lockfile", True) else "install"
            return [["npm", install_action], ["npm", "run", script]]
        if runtime == "python-django":
            if set(install_configuration) - {"requirements_file"}:
                raise RecipeError("unsupported Python install configuration")
            if set(build_configuration) - {"migrate", "collectstatic", "gunicorn_module"}:
                raise RecipeError("unsupported Django build configuration")
            requirements = install_configuration.get("requirements_file", "requirements.txt")
            module = build_configuration.get("gunicorn_module", "config.wsgi")
            if not SAFE_FILE.fullmatch(requirements) or not SAFE_MODULE.fullmatch(module):
                raise RecipeError("invalid Django recipe")
            commands = [[".venv/bin/pip", "install", "-r", requirements]]
            if build_configuration.get("migrate", False):
                commands.append([".venv/bin/python", "manage.py", "migrate", "--noinput"])
            if build_configuration.get("collectstatic", False):
                commands.append([".venv/bin/python", "manage.py", "collectstatic", "--noinput"])
            return commands
        raise RecipeError("unsupported runtime recipe")

    def restart(self, unit_name: str) -> None:
        if not SAFE_UNIT.fullmatch(unit_name) or unit_name.startswith("digitalafarin-platform-"):
            raise RecipeError("invalid or protected unit")
        subprocess.run(
            ["systemctl", "restart", unit_name],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
            shell=False,
        )

    def run_commands(
        self,
        commands: list[list[str]],
        cwd: Path,
        environment: dict[str, str],
        known_secrets: tuple[str, ...],
    ) -> None:
        process_environment = {**os.environ, **environment}
        for command in commands:
            try:
                result = subprocess.run(
                    command,
                    cwd=cwd,
                    env=process_environment,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=900,
                    shell=False,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise RecipeError(type(exc).__name__) from exc
            if result.returncode != 0:
                raise RecipeError(redact(result.stderr or result.stdout, known_secrets)[:500])
