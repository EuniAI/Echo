import functools
from typing import Mapping, Optional, Sequence

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from app.docker.base_container import BaseContainer
from app.git.git_repository import GitRepository
from app.lang_graph.nodes.bug_reproducing_execute_node import BugReproducingExecuteNode
from app.lang_graph.nodes.bug_reproducing_file_node import BugReproducingFileNode
from app.lang_graph.nodes.bug_reproducing_structured_node import BugReproducingStructuredNode
from app.lang_graph.nodes.bug_reproducing_write_message_node import (
    BugReproducingWriteMessageNode,
)
from app.lang_graph.nodes.bug_reproducing_write_node import BugReproducingWriteNode
from app.lang_graph.nodes.dual_version_validation_node import DualVersionValidationNode
from app.lang_graph.nodes.focal_code_retrieval_node import FocalCodeRetrievalNode
from app.lang_graph.nodes.git_diff_node import GitDiffNode
from app.lang_graph.nodes.git_reset_node import GitResetNode
from app.lang_graph.nodes.reset_messages_node import ResetMessagesNode
from app.lang_graph.nodes.test_case_retrieval_node import TestCaseRetrievalNode
from app.lang_graph.nodes.update_container_node import UpdateContainerNode
from app.lang_graph.nodes.validation_feedback_node import ValidationFeedbackNode
from app.lang_graph.subgraphs.bug_reproduction_state import BugReproductionState


class BugReproductionSubgraph:
    """
    This class defines a LangGraph-based state machine that performs automatic bug reproduction
    for GitHub issues. It orchestrates context retrieval, patch writing, file editing,
    container execution, and feedback-based retry loops to reproduce bugs in codebases.
    """

    def __init__(
        self,
        advanced_model: BaseChatModel,
        base_model: BaseChatModel,
        container: BaseContainer,
        git_repo: GitRepository,
        test_commands: Optional[Sequence[str]] = None,
    ):
        """
        Initialize the bug reproduction pipeline with all necessary parts.

        Args:
            advanced_model: More powerful LLM for structured reasoning and synthesis.
            base_model: Lighter LLM for simpler tasks (e.g., file selection).
            container: Docker-based sandbox for running code.
            git_repo: Git repository interface for codebase manipulation.
            test_commands: Optional list of test commands to verify reproduction success.

        Note:
            Context retrieval is now handled by external CRA service, not the knowledge graph.
        """
        self.git_repo = git_repo

        # Step 1: Retrieve focal code based on issue and patch (via external CRA)
        focal_code_retrieval_node = FocalCodeRetrievalNode()

        # Step 2: Retrieve existing test cases based on issue and patch (via external CRA)
        test_case_retrieval_node = TestCaseRetrievalNode()

        # Step 3: Write a patch to reproduce the bug
        bug_reproducing_write_message_node = BugReproducingWriteMessageNode()
        bug_reproducing_write_node = BugReproducingWriteNode(
            advanced_model, git_repo.playground_path
        )
        bug_reproducing_write_tools = ToolNode(
            tools=bug_reproducing_write_node.tools,
            name="bug_reproducing_write_tools",
            messages_key="bug_reproducing_write_messages",
        )

        # Step 4: Edit files if necessary (based on tool calls)
        bug_reproducing_file_node = BugReproducingFileNode(base_model, git_repo.playground_path)
        bug_reproducing_file_tools = ToolNode(
            tools=bug_reproducing_file_node.tools,
            name="bug_reproducing_file_tools",
            messages_key="bug_reproducing_file_messages",
        )

        # Step 5: Create a Git diff from modified files
        git_diff_node = GitDiffNode(git_repo, "bug_reproducing_patch")

        # Step 6: Update container with modified code
        update_container_node = UpdateContainerNode(container, git_repo)

        # Step 7: Run test commands to verify bug reproduction
        bug_reproducing_execute_node = BugReproducingExecuteNode(
            base_model, container, test_commands
        )
        bug_reproducing_execute_tools = ToolNode(
            tools=bug_reproducing_execute_node.tools,
            name="bug_reproducing_execute_tools",
            messages_key="bug_reproducing_execute_messages",
        )

        # Step 8: Decide whether the bug is reproduced or not
        bug_reproducing_structured_node = BugReproducingStructuredNode(advanced_model)

        # Step 9: Validate test on old and new versions
        dual_version_validation_node = DualVersionValidationNode(
            container,
            git_repo,
        )

        # Step 10: Provide feedback when validation fails
        validation_feedback_node = ValidationFeedbackNode()

        # Step 11: Reset state if bug reproduction fails, for retry
        reset_bug_reproducing_file_messages_node = ResetMessagesNode(
            "bug_reproducing_file_messages"
        )
        reset_bug_reproducing_execute_messages_node = ResetMessagesNode(
            "bug_reproducing_execute_messages"
        )

        # Step 12: Git reset to revert changes
        git_reset_node = GitResetNode(git_repo)

        # Define the state machine
        workflow = StateGraph(BugReproductionState)

        # Add nodes to the state machine
        workflow.add_node("focal_code_retrieval_node", focal_code_retrieval_node)
        workflow.add_node("test_case_retrieval_node", test_case_retrieval_node)
        workflow.add_node("bug_reproducing_write_message_node", bug_reproducing_write_message_node)
        workflow.add_node("bug_reproducing_write_node", bug_reproducing_write_node)
        workflow.add_node("bug_reproducing_write_tools", bug_reproducing_write_tools)
        workflow.add_node("bug_reproducing_file_node", bug_reproducing_file_node)
        workflow.add_node("bug_reproducing_file_tools", bug_reproducing_file_tools)
        workflow.add_node("git_diff_node", git_diff_node)
        workflow.add_node("update_container_node", update_container_node)
        workflow.add_node("bug_reproducing_execute_node", bug_reproducing_execute_node)
        workflow.add_node("bug_reproducing_execute_tools", bug_reproducing_execute_tools)
        workflow.add_node("bug_reproducing_structured_node", bug_reproducing_structured_node)
        workflow.add_node("dual_version_validation_node", dual_version_validation_node)
        workflow.add_node("validation_feedback_node", validation_feedback_node)
        workflow.add_node(
            "reset_bug_reproducing_file_messages_node", reset_bug_reproducing_file_messages_node
        )
        workflow.add_node(
            "reset_bug_reproducing_execute_messages_node",
            reset_bug_reproducing_execute_messages_node,
        )
        workflow.add_node("git_reset_node", git_reset_node)

        # Define transitions between nodes
        # Start directly with focal code retrieval (using external CRA)
        workflow.set_entry_point("focal_code_retrieval_node")

        workflow.add_edge("focal_code_retrieval_node", "test_case_retrieval_node")
        workflow.add_edge("test_case_retrieval_node", "bug_reproducing_write_message_node")
        workflow.add_edge("bug_reproducing_write_message_node", "bug_reproducing_write_node")

        # Handle patch-writing tool usage or fallback
        workflow.add_conditional_edges(
            "bug_reproducing_write_node",
            functools.partial(tools_condition, messages_key="bug_reproducing_write_messages"),
            {
                "tools": "bug_reproducing_write_tools",
                END: "bug_reproducing_file_node",
            },
        )
        workflow.add_edge("bug_reproducing_write_tools", "bug_reproducing_write_node")

        # Handle file-editing tool usage or fallback
        workflow.add_conditional_edges(
            "bug_reproducing_file_node",
            functools.partial(tools_condition, messages_key="bug_reproducing_file_messages"),
            {
                "tools": "bug_reproducing_file_tools",
                END: "git_diff_node",
            },
        )
        workflow.add_edge("bug_reproducing_file_tools", "bug_reproducing_file_node")

        # Proceed to execution after code is updated
        workflow.add_conditional_edges(
            "git_diff_node",
            lambda state: bool(state["bug_reproducing_patch"]),
            {True: "update_container_node", False: "bug_reproducing_write_message_node"},
        )
        workflow.add_edge("update_container_node", "bug_reproducing_execute_node")

        # Handle command execution tool usage
        workflow.add_conditional_edges(
            "bug_reproducing_execute_node",
            functools.partial(tools_condition, messages_key="bug_reproducing_execute_messages"),
            {
                "tools": "bug_reproducing_execute_tools",
                END: "bug_reproducing_structured_node",
            },
        )
        workflow.add_edge("bug_reproducing_execute_tools", "bug_reproducing_execute_node")

        # After bug_reproducing_structured_node, decide whether to validate or retry
        workflow.add_conditional_edges(
            "bug_reproducing_structured_node",
            lambda state: state["reproduced_bug"],
            {
                True: "dual_version_validation_node",  # Test claims to reproduce - validate it
                False: "reset_bug_reproducing_file_messages_node",  # Test doesn't claim to reproduce - retry
            },
        )

        # After validation, check if it passed
        def should_retry_validation(state):
            validation_passed = state.get("validation_passed", False)
            if validation_passed:
                return "success"
            attempt_count = state.get("validation_attempt_count", 0)
            max_attempts = state.get("max_validation_attempts", 3)
            return "retry" if attempt_count < max_attempts else "max_retries"

        workflow.add_conditional_edges(
            "dual_version_validation_node",
            should_retry_validation,
            {
                "success": END,  # Validation passed - we're done!
                "retry": "validation_feedback_node",  # Retry with feedback
                "max_retries": END,  # Max retries reached, give up
            },
        )

        # After providing feedback, reset and retry
        workflow.add_edge("validation_feedback_node", "reset_bug_reproducing_file_messages_node")

        # Retry loop: reset messages, revert repo, then go back to rewriting
        workflow.add_edge(
            "reset_bug_reproducing_file_messages_node",
            "reset_bug_reproducing_execute_messages_node",
        )
        workflow.add_edge("reset_bug_reproducing_execute_messages_node", "git_reset_node")
        workflow.add_edge("git_reset_node", "bug_reproducing_write_message_node")

        # Compile the full LangGraph subgraph
        self.subgraph = workflow.compile()

    def invoke(
        self,
        issue_title: str,
        issue_body: str,
        issue_patch: str,
        issue_comments: Sequence[Mapping[str, str]],
        repository_id: int,
        recursion_limit: int = 200,
    ):
        """
        Run the bug reproduction subgraph with external CRA and dual-version validation.

        Args:
            issue_title: Title of the GitHub issue.
            issue_body: Main body text describing the bug.
            issue_patch: Patch content from patches.json or provided directly.
            issue_comments: List of user/system comments for context.
            repository_id: Repository ID from external CRA service.
            recursion_limit: Max steps before triggering recovery fallback.

        Returns:
            Dict with bug reproduction result, validation results, and artifacts.
        """
        config = {"recursion_limit": recursion_limit}

        input_state = {
            "issue_title": issue_title,
            "issue_patch": issue_patch,
            "issue_body": issue_body,
            "issue_comments": issue_comments,
            "repository_id": repository_id,
            "max_refined_query_loop": 2,
            "max_validation_attempts": 3,
            "validation_attempt_count": 0,
        }

        output_state = self.subgraph.invoke(input_state, config)
        return {
            "reproduced_bug": output_state.get("reproduced_bug", False),
            "reproduced_bug_file": output_state.get("reproduced_bug_file", ""),
            "reproduced_bug_commands": output_state.get("reproduced_bug_commands", []),
            "reproduced_bug_patch": output_state.get("bug_reproducing_patch", ""),
            "validation_passed": output_state.get("validation_passed", False),
            "old_version_test_result": output_state.get("old_version_test_result", ""),
            "new_version_test_result": output_state.get("new_version_test_result", ""),
        }
