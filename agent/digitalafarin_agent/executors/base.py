from pathlib import Path
from typing import Protocol


class DeploymentExecutor(Protocol):
    name: str

    def recipe_commands(
        self,
        runtime: str,
        install_configuration: dict,
        build_configuration: dict,
        root_directory: str,
    ) -> list[list[str]]: ...

    def restart(self, unit_name: str) -> None: ...
