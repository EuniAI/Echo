import logging
import threading

from app.lang_graph.subgraphs.bug_reproduction_state import BugReproductionState
from app.tools.load_patch import load_patch


class LoadPatchNode:
    """
    Load patch from patches.json using instance_id.

    Reads the patch file and extracts the model_patch for the given instance.
    Sets patch_load_error if loading fails.
    """

    def __init__(self):
        self._logger = logging.getLogger(f"thread-{threading.get_ident()}.{__name__}")

    def __call__(self, state: BugReproductionState):
        instance_id = state.get("instance_id")
        patch_file_path = state.get("patch_file_path")

        if not instance_id:
            error_msg = "instance_id is required to load patch"
            self._logger.error(error_msg)
            return {"patch_load_error": error_msg, "issue_patch": ""}

        if not patch_file_path:
            error_msg = "patch_file_path is required to load patch"
            self._logger.error(error_msg)
            return {"patch_load_error": error_msg, "issue_patch": ""}

        self._logger.info(f"Loading patch for instance_id: {instance_id}")
        patch_content = load_patch(instance_id, patch_file_path)

        # Check if it's an error message
        if patch_content.startswith("Error:"):
            self._logger.error(f"Failed to load patch: {patch_content}")
            return {"patch_load_error": patch_content, "issue_patch": ""}

        self._logger.info(f"Successfully loaded patch for {instance_id}")
        return {
            "issue_patch": patch_content,
            "patch_load_error": ""
        }
