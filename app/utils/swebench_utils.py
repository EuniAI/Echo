from typing import Sequence

from swebench import MAP_REPO_VERSION_TO_SPECS


def get_build_commands(instance: dict) -> Sequence[str]:
    specs = MAP_REPO_VERSION_TO_SPECS[instance["repo"]][instance["version"]]
    eval_commands = [
        ". /opt/miniconda3/bin/activate",
        "conda activate testbed",
    ]
    if "eval_commands" in specs:
        eval_commands += specs["eval_commands"]
    if "install" in specs:
        eval_commands.append(specs["install"])

    return eval_commands
