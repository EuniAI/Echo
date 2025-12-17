import logging
import threading

from langchain_core.messages import HumanMessage

from app.lang_graph.subgraphs.bug_reproduction_state import BugReproductionState


class ValidationFeedbackNode:
    """
    Generates feedback message when validation fails.

    Analyzes old and new test results and creates a message to guide
    the next iteration of test generation.
    """

    FEEDBACK_TEMPLATE = """
The previous test case did not meet the validation requirements:

OLD VERSION TEST RESULT (should FAIL):
{old_result}
Test Status: {old_status}

NEW VERSION TEST RESULT (should PASS after patch):
{new_result}
Test Status: {new_status}

ANALYSIS:
{analysis}

Please generate a new test case that:
1. Fails on the old codebase (demonstrates the bug)
2. Passes on the patched codebase (bug is fixed)
3. Tests the exact behavior described in the issue
"""

    def __init__(self):
        self._logger = logging.getLogger(f"thread-{threading.get_ident()}.{__name__}")

    def _analyze_failure(self, old_result: str, new_result: str) -> tuple[bool, bool, str]:
        """
        Analyze test results and generate feedback.

        Returns:
            tuple: (old_passed, new_passed, analysis_message)
        """
        # Check if test passed based on output
        old_passed = ("passed" in old_result.lower() or "ok" in old_result.lower()) and "failed" not in old_result.lower()
        new_passed = ("passed" in new_result.lower() or "ok" in new_result.lower()) and "failed" not in new_result.lower()

        if old_passed and new_passed:
            analysis = "The test passes on both old and new versions. This means the test is not demonstrating the bug. The test needs to fail on the old version to show the bug exists."
        elif old_passed and not new_passed:
            analysis = "The test passes on old version but fails on new version. This is backwards - the bug should exist in the old version (test fails) and be fixed in the new version (test passes)."
        elif not old_passed and not new_passed:
            analysis = "The test fails on both old and new versions. The patch should fix the bug, so the test should pass on the new version. Either the test is checking the wrong behavior, or there's an issue with test setup."
        else:
            # This shouldn't happen if we reach this node (validation already passed)
            analysis = "Unexpected state - validation appears to have passed."

        return old_passed, new_passed, analysis

    def __call__(self, state: BugReproductionState):
        old_result = state.get("old_version_test_result", "")
        new_result = state.get("new_version_test_result", "")

        old_passed, new_passed, analysis = self._analyze_failure(old_result, new_result)

        old_status = "PASSED (INCORRECT - should fail)" if old_passed else "FAILED"
        new_status = "PASSED" if new_passed else "FAILED (INCORRECT - should pass)"

        feedback_message = self.FEEDBACK_TEMPLATE.format(
            old_result=old_result,
            new_result=new_result,
            old_status=old_status,
            new_status=new_status,
            analysis=analysis
        )

        self._logger.info(f"Validation failed - providing feedback for retry (attempt {state.get('validation_attempt_count', 0)})")

        # Add feedback to write messages to guide next iteration
        return {
            "bug_reproducing_write_messages": [HumanMessage(feedback_message)]
        }
