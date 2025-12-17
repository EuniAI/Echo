"""Context Retrieval utilities for calling Prometheus CRA (Context Retrieval Agent)."""

from typing import Any

import requests

from app.configuration.config import settings


class ContextRetrievalError(Exception):
    """Raised when context retrieval operations fail."""


class RepositoryError(Exception):
    """Raised when repository operations fail."""


# ============================================================================
# Repository Management
# ============================================================================


def upload_repository(
    https_url: str,
    commit_id: str | None = None
) -> dict[str, Any]:
    """
    Upload a repository to Prometheus CRA system.

    Args:
        https_url: HTTPS URL of the git repository (e.g., "https://github.com/user/repo.git")
        commit_id: Specific commit ID to use (optional, defaults to latest)

    Returns:
        dict containing:
            - repository_id: The ID of the uploaded repository
            - status: Upload status
            - Additional metadata from the server

    Raises:
        RepositoryError: If the upload fails or returns an error
    """
    endpoint = f"{settings.CRA_BASE_URL}/repository/upload/"

    # Prepare request payload
    payload = {
        "https_url": https_url,
        "commit_id": commit_id,
    }

    try:
        # Send POST request to upload repository
        response = requests.post(
            endpoint,
            json=payload,
            timeout=None,
            headers={
                "Content-Type": "application/json",
            },
        )

        # Check if request was successful
        response.raise_for_status()

        # Parse response
        data = response.json()["data"]

        # Validate response structure
        if "repository_id" not in data:
            raise RepositoryError(
                f"Invalid upload response: missing 'repository_id' field. Got: {data}"
            )

        return data

    except requests.exceptions.ConnectionError as e:
        raise RepositoryError(f"Failed to connect to CRA at {endpoint}: {e}") from e

    except requests.exceptions.HTTPError as e:
        error_msg = f"Upload failed with status {response.status_code}"
        try:
            error_data = response.json()
            if "error" in error_data:
                error_msg += f": {error_data['error']}"
            elif "detail" in error_data:
                error_msg += f": {error_data['detail']}"
        except Exception:
            error_msg += f": {response.text}"
        raise RepositoryError(error_msg) from e

    except requests.exceptions.RequestException as e:
        raise RepositoryError(f"Upload request failed: {e}") from e

    except ValueError as e:
        raise RepositoryError(f"Failed to parse upload response as JSON: {e}") from e


def delete_repository(
    repository_id: int,
    force: bool = False,
) -> dict[str, Any]:
    """
    Delete a repository from Prometheus CRA system.

    Args:
        repository_id: The ID of the repository to delete
        force: Force deletion even if there are dependencies (default: False)

    Returns:
        dict containing:
            - status: Deletion status
            - message: Deletion message
            - Additional metadata from the server

    Raises:
        RepositoryError: If the deletion fails or returns an error

    Example:
        >>> delete_repository(repository_id=123, force=False)
        {'status': 'success', 'message': 'Repository deleted'}
    """
    base_url = settings.CRA_BASE_URL
    endpoint = f"{base_url}/repository/delete/"

    # Prepare query parameters
    params = {
        "repository_id": repository_id,
        "force": force,
    }

    try:
        # Send DELETE request
        response = requests.delete(
            endpoint,
            params=params,
            timeout=None,
            headers={
                "Content-Type": "application/json",
            },
        )

        # Check if request was successful
        response.raise_for_status()

        # Parse response
        data = response.json()

        return data

    except requests.exceptions.ConnectionError as e:
        raise RepositoryError(f"Failed to connect to CRA at {endpoint}: {e}") from e

    except requests.exceptions.HTTPError as e:
        error_msg = f"Deletion failed with status {response.status_code}"
        try:
            error_data = response.json()
            if "error" in error_data:
                error_msg += f": {error_data['error']}"
            elif "detail" in error_data:
                error_msg += f": {error_data['detail']}"
        except Exception:
            error_msg += f": {response.text}"
        raise RepositoryError(error_msg) from e

    except requests.exceptions.RequestException as e:
        raise RepositoryError(f"Deletion request failed: {e}") from e

    except ValueError as e:
        raise RepositoryError(f"Failed to parse deletion response as JSON: {e}") from e


# ============================================================================
# Context Retrieval
# ============================================================================


def context_retrieval_tool(
    query: str,
    max_refined_query: int,
    repository_id: int,
) -> dict[str, Any]:
    """
    Call Prometheus Context Retrieval Agent to retrieve relevant context.

    Args:
        query: The search query to find relevant context
        max_refined_query: Maximum number of query refinements (default: 3)
        repository_id: Repository ID to search in (optional, reads from CRA_REPOSITORY_ID env var if not provided)

    Returns:
        dict containing:
            - contexts: List of context snippets, each with:
                - relative_path: File path relative to repository root
                - content: Code snippet content
                - start_line_number: Starting line number of the snippet
                - end_line_number: Ending line number of the snippet
            - total_contexts: Total number of contexts retrieved

    Raises:
        ContextRetrievalError: If the request fails or returns an error
    """
    # Get CRA URL (read from environment at call time, not import time)
    cra_url = f"{settings.CRA_BASE_URL}/context/retrieve"

    # Prepare request payload
    payload = {
        "query": query,
        "max_refined_query_loop": max_refined_query,
        "repository_id": repository_id,
    }

    response = None
    try:
        # Send POST request to CRA
        response = requests.post(
            cra_url,
            json=payload,
            timeout=None,
            headers={
                "Content-Type": "application/json",
            },
        )

        # Check if request was successful
        response.raise_for_status()

        # Parse response
        data = response.json()["data"]

        return data

    except requests.exceptions.ConnectionError as e:
        raise ContextRetrievalError(
            f"Failed to connect to CRA at {cra_url}: {e}"
        ) from e

    except requests.exceptions.HTTPError as e:
        error_msg = f"CRA returned error status {response.status_code if response else 'unknown'}"
        if response:
            try:
                error_data = response.json()
                if "error" in error_data:
                    error_msg += f": {error_data['error']}"
            except Exception:
                error_msg += f": {response.text}"
        raise ContextRetrievalError(error_msg) from e

    except requests.exceptions.RequestException as e:
        raise ContextRetrievalError(f"CRA request failed: {e}") from e

    except ValueError as e:
        raise ContextRetrievalError(f"Failed to parse CRA response as JSON: {e}") from e
