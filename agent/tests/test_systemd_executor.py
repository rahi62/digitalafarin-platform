import pytest

from digitalafarin_agent.executors.systemd import RecipeError, SystemdExecutor


def test_node_recipe_builds_fixed_argv():
    executor = SystemdExecutor()
    commands = executor.recipe_commands(
        runtime="node-nextjs",
        install_configuration={"package_manager": "npm", "lockfile": True},
        build_configuration={"build_script": "build"},
        root_directory="frontend",
    )

    assert commands == [["npm", "ci"], ["npm", "run", "build"]]


def test_django_recipe_builds_fixed_argv():
    executor = SystemdExecutor()
    commands = executor.recipe_commands(
        runtime="python-django",
        install_configuration={"requirements_file": "requirements.txt"},
        build_configuration={"migrate": True, "collectstatic": True, "gunicorn_module": "config.wsgi"},
        root_directory="backend",
    )

    assert commands == [
        [".venv/bin/pip", "install", "-r", "requirements.txt"],
        [".venv/bin/python", "manage.py", "migrate", "--noinput"],
        [".venv/bin/python", "manage.py", "collectstatic", "--noinput"],
    ]


def test_recipe_rejects_shell_syntax_and_unknown_executor():
    executor = SystemdExecutor()
    with pytest.raises(RecipeError):
        executor.recipe_commands("node-nextjs", {}, {"build_script": "build; id"}, ".")
    with pytest.raises(RecipeError):
        executor.recipe_commands("ruby", {}, {}, ".")
