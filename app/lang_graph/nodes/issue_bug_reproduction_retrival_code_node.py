import logging
import threading

from app.lang_graph.subgraphs.bug_reproduction_state import BugReproductionState
from app.utils.issue_util import format_issue_info


class IssueBugReproductionRetrivalCodeNode:
    BUG_REPRODUCING_RETRIVAL_CODE_QUERY = """\
{issue_info}

OBJECTIVE: Find the most relevant code function that could be modified to fix the bug,
including ALL necessary class and function definitions.

<reasoning>
1. Analyze bug characteristics:
   - Root cause of the bug
   - Core functionality being affected by the bug
   - The code function that is related to the bug
   - The code function that could be modified to fix the bug
   - The code function that is related to the bug

2. Focus areas:
   - All necessary class and function definitions
</reasoning>

REQUIREMENTS:
- Return the most relevant code function with complete context, ensuring ALL necessary class and function definitions are included.
- Must include all necessary code function definitions
- Must include all necessary parameters and return values
- Must include all necessary function calls and class instantiations

<examples>
<example id="database-timeout">
<bug>
db.execute("SELECT * FROM users").fetchall() 
raises ConnectionTimeout when load is high
</bug>

<ideal_test_match>
# File: tests/test_database.py
import pytest
from unittest.mock import Mock, patch
from database.exceptions import ConnectionTimeout
from database.models import QueryResult
from database.client import DatabaseClient

class TestDatabaseTimeout:
    @pytest.fixture
    def mock_db_connection(self):
        conn = Mock()
        conn.execute.side_effect = [
            ConnectionTimeout("Connection timed out"),
            QueryResult(["user1", "user2"])  # Second try succeeds
        ]
        return conn
        
    def test_handle_timeout_during_query(self, mock_db_connection):
        # Complete test showing timeout scenario
        # Including retry logic verification
        # With all necessary assertions
</ideal_test_match>
</example>

<example id="file-permission">
<bug>
FileProcessor('/root/data.txt').process() 
fails with PermissionError
</bug>

<ideal_test_match>
# File: tests/test_file_processor.py
import os
import pytest
from unittest.mock import patch, mock_open
from file_processor import FileProcessor
from file_processor.exceptions import ProcessingError

class TestFilePermissions:
    @patch('os.access')
    @patch('builtins.open')
    def test_file_permission_denied(self, mock_open, mock_access):
        # Full test setup with mocked file system
        # Permission denial simulation
        # Error handling verification
</ideal_test_match>
</example>

Search priority:
1. Code functions most likely to be modified to fix the bug
2. Code functions most likely to be affected by the bug
3. Code functions most likely to be related to the bug

Find the most relevant code function with complete context, ensuring ALL necessary class and function definitions are included.
"""

    def __init__(self):
        self._logger = logging.getLogger(f"thread-{threading.get_ident()}.{__name__}")

    def __call__(self, state: BugReproductionState):
        bug_reproducing_retrival_code_query = self.BUG_REPRODUCING_RETRIVAL_CODE_QUERY.format(
            issue_info=format_issue_info(
                state["issue_title"], state["issue_body"], state["issue_comments"]
            ),
        )
        self._logger.debug(
            f"Sending query to context provider subgraph:\n{bug_reproducing_retrival_code_query}"
        )
        return {"bug_reproducing_retrival_code_query": bug_reproducing_retrival_code_query}
