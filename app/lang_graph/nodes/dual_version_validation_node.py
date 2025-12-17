import logging
import threading
from pathlib import Path

from app.docker.base_container import BaseContainer
from app.git.git_repository import GitRepository
from app.lang_graph.subgraphs.bug_reproduction_state import BugReproductionState
from app.utils.patch_util import get_updated_files


class DualVersionValidationNode:
    """
    Validates that the test fails on old codebase and passes on patched codebase.

    Process:
    1. Run test on current (old) codebase - should FAIL
    2. Apply patch to git repository
    3. Update container with patched code
    4. Run test on patched codebase - should PASS
    5. Reset git repository to clean state
    6. Set validation_passed=True only if test fails on old AND passes on new
    """

    def __init__(
        self,
        container: BaseContainer,
        git_repo: GitRepository,
    ):
        self._logger = logging.getLogger(f"thread-{threading.get_ident()}.{__name__}")
        self.container = container
        self.git_repo = git_repo

    def _get_test_file_path(self, state: BugReproductionState) -> Path:
        """Extract the test file path from bug_reproducing_patch."""
        added_files, modified_files, removed_files = get_updated_files(
            state["bug_reproducing_patch"]
        )
        if len(added_files) != 1:
            raise ValueError(f"Expected exactly 1 added test file, got {len(added_files)}")
        return added_files[0]

    def _run_test(self, test_file: Path, test_commands: list) -> tuple[str, bool]:
        """
        Run test and return (output, passed).

        Returns:
            tuple: (test_output, test_passed_bool)
        """
        # Use test commands from state if available, otherwise use default pytest
        if test_commands:
            # Use the first command as base and adapt to single file
            test_cmd = test_commands[0]
        else:
            test_cmd = f"python -m pytest {test_file} -xvs"

        output = self.container.execute_command(test_cmd)

        # Check if test passed
        # Look for pytest success indicators and absence of failure indicators
        passed = (
            ("passed" in output.lower() or "ok" in output.lower())
            and "failed" not in output.lower()
            and "error" not in output.lower()
        )

        return output, passed

    def __call__(self, state: BugReproductionState):
        try:
            test_file = self._get_test_file_path(state)
        except ValueError as e:
            self._logger.error(f"Cannot validate: {e}")
            return {
                "validation_passed": False,
                "old_version_test_result": f"Error: {e}",
                "new_version_test_result": "",
                "validation_attempt_count": state.get("validation_attempt_count", 0) + 1,
            }

        self._logger.info("Starting dual-version validation")

        # Step 1: Run test on OLD codebase (should FAIL)
        self._logger.info("Running test on old codebase (should fail)")
        old_output, old_passed = self._run_test(test_file, state.get("reproduced_bug_commands", []))

        if old_passed:
            self._logger.warning("Test PASSED on old codebase - validation failed")
            return {
                "validation_passed": False,
                "old_version_test_result": old_output,
                "new_version_test_result": "(not executed - test passed on old version)",
                "validation_attempt_count": state.get("validation_attempt_count", 0) + 1,
            }

        self._logger.info("Test failed on old codebase (as expected)")

        # Step 2: Apply patch to repository
        try:
            self._logger.info("Applying patch to repository")
            self.git_repo.apply_patch(state["issue_patch"])
        except Exception as e:
            self._logger.error(f"Failed to apply patch: {e}")
            self.git_repo.reset_repository()
            return {
                "validation_passed": False,
                "old_version_test_result": old_output,
                "new_version_test_result": f"Error applying patch: {e}",
                "validation_attempt_count": state.get("validation_attempt_count", 0) + 1,
            }

        # Step 3: Update container with patched code
        try:
            self._logger.info("Updating container with patched code")
            # Get list of modified files from patch
            added_files, modified_files, removed_files = get_updated_files(state["issue_patch"])
            all_updated_files = list(set(added_files + modified_files))

            self.container.update_files(
                self.git_repo.playground_path, all_updated_files, removed_files
            )
        except Exception as e:
            self._logger.error(f"Failed to update container: {e}")
            self.git_repo.reset_repository()
            return {
                "validation_passed": False,
                "old_version_test_result": old_output,
                "new_version_test_result": f"Error updating container: {e}",
                "validation_attempt_count": state.get("validation_attempt_count", 0) + 1,
            }

        # Step 4: Run test on NEW (patched) codebase (should PASS)
        self._logger.info("Running test on patched codebase (should pass)")
        new_output, new_passed = self._run_test(test_file, state.get("reproduced_bug_commands", []))

        # Step 5: Reset repository (always do this to clean up)
        self._logger.info("Resetting repository to clean state")
        self.git_repo.reset_repository()

        # Step 6: Determine if validation passed
        validation_passed = (not old_passed) and new_passed

        if validation_passed:
            self._logger.info("Validation PASSED: Test fails on old, passes on new")
        else:
            self._logger.warning(
                f"Validation FAILED: old_passed={old_passed}, new_passed={new_passed}"
            )

        return {
            "validation_passed": validation_passed,
            "old_version_test_result": old_output,
            "new_version_test_result": new_output,
            "validation_attempt_count": state.get("validation_attempt_count", 0) + 1,
        }
