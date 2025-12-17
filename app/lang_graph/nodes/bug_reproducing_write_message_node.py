import logging
import threading

from langchain_core.messages import HumanMessage

from app.lang_graph.subgraphs.bug_reproduction_state import BugReproductionState
from app.utils.issue_util import format_issue_info


class BugReproducingWriteMessageNode:
    FIRST_HUMAN_PROMPT = """\
{issue_info}

Patch Information:
{patch_info}

Focal Code Context (relevant code that may need fixing):
{focal_code_context}

Test Case Context (similar existing tests for reference):
{test_context}

Now generate the complete self-contained test case that reproduces the bug with the same error/exception.
"""

    FOLLOWUP_HUMAN_PROMPT = """\
Your previous test case failed to reproduce the bug. Here is the failure log:
{reproduced_bug_failure_log}

Now think about what went wrong and generate the complete self-contained test case that reproduces the bug with the same error/exception again.
"""

    def __init__(self):
        self._logger = logging.getLogger(f"thread-{threading.get_ident()}.{__name__}")

    def format_human_message(self, state: BugReproductionState):
        if "reproduced_bug_failure_log" in state and state["reproduced_bug_failure_log"]:
            return HumanMessage(
                self.FOLLOWUP_HUMAN_PROMPT.format(
                    reproduced_bug_failure_log=state["reproduced_bug_failure_log"],
                )
            )

        # Format focal code context
        focal_code_context = state.get("bug_reproducing_focal_code_context", [])
        focal_code_str = "\n\n".join([str(context) for context in focal_code_context]) if focal_code_context else "No focal code context retrieved"

        # Format test case context
        test_context = state.get("bug_reproducing_test_context", [])
        test_context_str = "\n\n".join([str(context) for context in test_context]) if test_context else "No test case context retrieved"

        # Format patch info
        patch_info = state.get("issue_patch", "")
        patch_info_str = f"```diff\n{patch_info}\n```" if patch_info else "No patch available"

        return HumanMessage(
            self.FIRST_HUMAN_PROMPT.format(
                issue_info=format_issue_info(
                    state["issue_title"], state["issue_body"], state["issue_comments"]
                ),
                patch_info=patch_info_str,
                focal_code_context=focal_code_str,
                test_context=test_context_str,
            )
        )

    def __call__(self, state: BugReproductionState):
        human_message = self.format_human_message(state)
        self._logger.debug(f"Sending message to BugReproducingWriteNode:\n{human_message}")
        return {"bug_reproducing_write_messages": [human_message]}
