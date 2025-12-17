import logging
import threading

from app.lang_graph.nodes.issue_bug_reproduction_retrival_code_with_patch_node import (
    IssueBugReproductionRetrivalCodeWithPatchNode,
)
from app.lang_graph.subgraphs.bug_reproduction_state import BugReproductionState
from app.utils.context_retrieval import context_retrieval_tool, ContextRetrievalError


class FocalCodeRetrievalNode:
    QUERY = """
Issue: {issue_title}

Description: {issue_body}

Patch information:
{issue_patch}

Find the most relevant code functions that could be modified to fix this bug,
including all necessary class and function definitions.
"""

    """
    Retrieves focal code context based on issue and patch using external CRA service.

    Two-step process:
    1. Generate query using IssueBugReproductionRetrivalCodeWithPatchNode (for logging)
    2. Execute context retrieval using external CRA service
    """

    def __init__(self):
        self._logger = logging.getLogger(f"thread-{threading.get_ident()}.{__name__}")
        self.query_node = IssueBugReproductionRetrivalCodeWithPatchNode()

    def __call__(self, state: BugReproductionState):
        self._logger.info("Retrieving focal code context via external CRA")
        query = self.QUERY.format(issue_title=state["issue_title"],
                                  issue_body=state["issue_body"],
                                  issue_patch=state["issue_patch"])
        try:
            result = context_retrieval_tool(
                query=query,
                max_refined_query=state["max_refined_query_loop"],
                repository_id=state["repository_id"]
            )
        except ContextRetrievalError as e:
            self._logger.error(f"CRA retrieval failed: {e}")
            return {
                "bug_reproducing_focal_code_context": []
            }
        # Convert CRA contexts to internal format

        self._logger.info(f"Focal code context retrieved: {result['total_contexts']} items")
        return {
                "bug_reproducing_focal_code_context": result["contexts"]
        }
