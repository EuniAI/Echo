import logging
import threading

from app.lang_graph.nodes.issue_bug_reproduction_retrival_test_with_patch_node import (
    IssueBugReproductionRetrivalTestWithPatchNode,
)
from app.lang_graph.subgraphs.bug_reproduction_state import BugReproductionState
from app.utils.context_retrieval import ContextRetrievalError, context_retrieval_tool


class TestCaseRetrievalNode:
    QUERY = """
Issue: {issue_title}

Description: {issue_body}

Patch information:
{issue_patch}

Find existing test cases that are similar to what would be needed to test this bug.
Look for test patterns, test setup code, and testing approaches that could be used.
"""

    """
    Retrieves existing test case context based on issue and patch using external CRA service.

    Two-step process:
    1. Generate query using IssueBugReproductionRetrivalTestWithPatchNode (for logging)
    2. Execute context retrieval using external CRA service
    """

    def __init__(self):
        self._logger = logging.getLogger(f"thread-{threading.get_ident()}.{__name__}")
        self.query_node = IssueBugReproductionRetrivalTestWithPatchNode()

    def __call__(self, state: BugReproductionState):
        self._logger.info("Retrieving test case context via external CRA")
        query = self.QUERY.format(
            issue_title=state["issue_title"],
            issue_body=state["issue_body"],
            issue_patch=state["issue_patch"],
        )
        try:
            result = context_retrieval_tool(
                query=query,
                max_refined_query=state["max_refined_query_loop"],
                repository_id=state["repository_id"],
            )
        except ContextRetrievalError as e:
            self._logger.error(f"CRA retrieval failed: {e}")
            return {"bug_reproducing_test_context": []}
        # Convert CRA contexts to internal format

        self._logger.info(f"Test case context retrieved: {result['total_contexts']} items")
        return {"bug_reproducing_test_context": result["contexts"]}
