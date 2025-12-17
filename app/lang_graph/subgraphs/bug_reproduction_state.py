from typing import Annotated, Mapping, Sequence, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

from app.models.context import Context


class BugReproductionState(TypedDict):
    issue_patch: str
    issue_title: str
    issue_body: str
    issue_comments: Sequence[Mapping[str, str]]

    # Patch
    patch: str

    # Dual context retrieval (replaces bug_reproducing_query and bug_reproducing_context)
    bug_reproducing_focal_code_context: Sequence[Context]
    bug_reproducing_test_context: Sequence[Context]

    bug_reproducing_write_messages: Annotated[Sequence[BaseMessage], add_messages]
    bug_reproducing_file_messages: Annotated[Sequence[BaseMessage], add_messages]
    bug_reproducing_execute_messages: Annotated[Sequence[BaseMessage], add_messages]

    bug_reproducing_patch: str

    # Dual-version validation fields
    old_version_test_result: str
    new_version_test_result: str
    validation_passed: bool
    validation_attempt_count: int
    max_validation_attempts: int

    reproduced_bug: bool
    reproduced_bug_failure_log: str
    reproduced_bug_file: str
    reproduced_bug_commands: Sequence[str]

    # Context Retrieval
    repository_id: int
    max_refined_query_loop: int
