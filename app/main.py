"""Main entry point for the Prometheus Bug Reproduction Agent.

This module orchestrates the entire bug reproduction workflow, including:
- Loading data from SWE-bench datasets
- Cloning GitHub repositories and building knowledge graphs
- Running containerized bug reproduction attempts
- Generating reproduction files, commands, and patches

The system uses LangGraph state machines to coordinate LLM-powered bug analysis
and reproduction in isolated Docker environments.
"""

import asyncio
import inspect
import json
import logging
import shutil
import threading
import traceback
from datetime import datetime
from pathlib import Path
from typing import Mapping, Sequence

import click
from datasets import load_dataset
from tqdm.asyncio import tqdm as async_tqdm

from app.configuration.config import settings
from app.docker.general_container import GeneralContainer
from app.docker.user_defined_container import UserDefinedContainer
from app.git.git_repository import GitRepository
from app.graph.knowledge_graph import KnowledgeGraph
from app.lang_graph.subgraphs.bug_reproduction_subgraph import BugReproductionSubgraph
from app.services.database_service import DatabaseService
from app.services.knowledge_graph_service import KnowledgeGraphService
from app.services.llm_service import LLMService
from app.services.neo4j_service import Neo4jService
from app.services.repository_service import RepositoryService
from app.utils.swebench_utils import get_build_commands

# Docker image naming format for SWE-bench evaluation containers
SWEBENCH_IMAGE_FORMAT = "swebench/sweb.eval.x86_64.{repo_prefix}_1776_{instance_id}:v1"

# GitHub repository URL template
GITHUB_HTTPS_URL = "https://github.com/{repo_name}.git"

# Create logs directory for thread-specific log files
LOG_DIR = Path(settings.WORKING_DIRECTORY) / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Initialize services with configuration settings
neo4j_service = Neo4jService(
    settings.NEO4J_URI,
    settings.NEO4J_USERNAME,
    settings.NEO4J_PASSWORD,
)

knowledge_graph_service = KnowledgeGraphService(
    neo4j_service,
    settings.NEO4J_BATCH_SIZE,
    settings.KNOWLEDGE_GRAPH_MAX_AST_DEPTH,
    settings.KNOWLEDGE_GRAPH_CHUNK_SIZE,
    settings.KNOWLEDGE_GRAPH_CHUNK_OVERLAP,
)

database_service = DatabaseService(settings.DATABASE_URL)

repository_service = RepositoryService(
    kg_service=knowledge_graph_service,
    database_service=database_service,
    working_dir=settings.WORKING_DIRECTORY,
)

llm_service = LLMService(
    advanced_model_name=settings.ADVANCED_MODEL,
    base_model_name=settings.BASE_MODEL,
    openai_format_api_key=settings.OPENAI_FORMAT_API_KEY,
    openai_format_base_url=settings.OPENAI_FORMAT_BASE_URL,
    anthropic_api_key=settings.ANTHROPIC_API_KEY,
    gemini_api_key=settings.GEMINI_API_KEY,
    advanced_model_temperature=settings.ADVANCED_MODEL_TEMPERATURE,
    base_model_temperature=settings.BASE_MODEL_TEMPERATURE,
)
services = {
    "neo4j_service": neo4j_service,
    "knowledge_graph_service": knowledge_graph_service,
    "database_service": database_service,
    "repository_service": repository_service,
    "llm_service": llm_service,
}


def _reproduce_bug(
    issue_title: str,
    issue_body: str,
    issue_comments: Sequence[Mapping[str, str]],
    knowledge_graph: KnowledgeGraph,
    repo_path: Path,
    git_repo: GitRepository,
    dockerfile_content: str = None,
    image_name: str = None,
    build_commands: Sequence[str] = None,
    test_commands: Sequence[str] = None,
    run_build: bool = True,
    workdir: str = None,
):
    # Set up a dedicated logger for this thread
    logger = logging.getLogger(f"thread-{threading.get_ident()}.app")
    logger.setLevel(getattr(logging, settings.LOGGING_LEVEL))
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = LOG_DIR / f"{timestamp}_{threading.get_ident()}.log"
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Construct the working directory
    if dockerfile_content or image_name:
        container = UserDefinedContainer(
            repo_path,
            workdir,
            dockerfile_content,
            image_name,
            build_commands,
            test_commands,
        )
    else:
        container = GeneralContainer(repo_path)

    # Start the container
    container.build_docker_image()
    container.start_container()

    # Run build commands if specified
    if run_build:
        container.run_build()

    # Initialize the bug reproduce graph
    bug_reproduction_subgraph = BugReproductionSubgraph(
        advanced_model=llm_service.advanced_model,
        base_model=llm_service.base_model,
        container=container,
        kg=knowledge_graph,
        git_repo=git_repo,
    )

    # Invoke the bug reproduction subgraph
    print("Starting bug reproduction...")
    try:
        output_states = bug_reproduction_subgraph.invoke(
            issue_title=issue_title, issue_body=issue_body, issue_comments=issue_comments
        )
    except Exception as e:
        logger.error(f"Error in answer_issue: {str(e)}\n{traceback.format_exc()}")
        return False, None, None, None
    finally:
        # Clean up resources
        container.cleanup()
        git_repo.reset_repository()
        logger.removeHandler(file_handler)
        file_handler.close()

    print(f"reproduced_bug: {output_states['reproduced_bug']}")
    print(f"reproduced_bug_file: {output_states['reproduced_bug_file']}")
    print(f"reproduced_bug_commands: {output_states['reproduced_bug_commands']}")
    print(f"reproduced_bug_patch: {output_states['reproduced_bug_patch']}")

    return (
        output_states["reproduced_bug"],
        output_states["reproduced_bug_file"],
        output_states["reproduced_bug_commands"],
        output_states["reproduced_bug_patch"],
    )


async def reproduce_bug(
    issue_title: str,
    issue_body: str,
    issue_comments: Sequence[Mapping[str, str]],
    github_url: str,
    github_token: str,
    commit_id: str = None,
    dockerfile_content: str = None,
    image_name: str = None,
    build_commands: Sequence[str] = None,
    test_commands: Sequence[str] = None,
    run_build: bool = True,
    workdir: str = None,
) -> tuple[bool, None, None, None] | tuple[bool, str, str, str]:
    """Reproduce a software bug from a GitHub issue.

    This function orchestrates the complete bug reproduction workflow:
    1. Clones the GitHub repository at a specific commit
    2. Builds a knowledge graph representation of the codebase
    3. Sets up a Docker container environment (general or user-defined)
    4. Uses LLM-powered agents to analyze the issue and attempt reproduction
    5. Cleans up all resources after completion

    Args:
        issue_title: Title/summary of the GitHub issue.
        issue_body: Full description of the bug from the issue body.
        issue_comments: List of comments from the GitHub issue thread.
        github_url: HTTPS URL of the GitHub repository.
        github_token: GitHub access token for authentication (None for public repos).
        commit_id: Specific commit hash to check out (None for latest).
        dockerfile_content: Custom Dockerfile content for user-defined environments.
        image_name: Pre-built Docker image name (e.g., SWE-bench images).
        build_commands: Commands to build/install the project in the container.
        test_commands: Commands to run tests (currently unused).
        run_build: Whether to execute build commands after container startup.
        workdir: Working directory path inside the container (required for user-defined envs).

    Returns:
        A tuple containing:
        - reproduced_bug (bool): Whether the bug was successfully reproduced.
        - reproduced_bug_file (str | None): Path to the reproduction test file.
        - reproduced_bug_commands (str | None): Commands used to reproduce the bug.
        - reproduced_bug_patch (str | None): Git patch that fixes the bug.

    Raises:
        Exception: If workdir is not provided when using dockerfile_content or image_name.

    Note:
        This function automatically cleans up Docker containers, resets Git repositories,
        clears Neo4j knowledge graphs, and removes cloned repositories after execution.
    """
    if dockerfile_content or image_name:
        if workdir is None:
            raise Exception("workdir must be provided for user defined environment")
    # Clone the repository
    print("Starting cloning the repository...")
    repo_path = await repository_service.clone_github_repo(github_token, github_url, commit_id)
    print(f"Repository cloned to: {repo_path}")

    # Build and save the knowledge graph
    root_node_id = await knowledge_graph_service.build_and_save_knowledge_graph(repo_path)

    knowledge_graph = await knowledge_graph_service.get_knowledge_graph(
        root_node_id,
        settings.KNOWLEDGE_GRAPH_MAX_AST_DEPTH,
        settings.KNOWLEDGE_GRAPH_CHUNK_SIZE,
        settings.KNOWLEDGE_GRAPH_CHUNK_OVERLAP,
    )
    git_repo = repository_service.get_repository(repo_path)

    # Run the bug reproduction in a separate thread
    (
        reproduced_bug,
        reproduced_bug_file,
        reproduced_bug_commands,
        reproduced_bug_patch,
    ) = await asyncio.to_thread(
        _reproduce_bug,
        issue_title,
        issue_body,
        issue_comments,
        knowledge_graph,
        repo_path,
        git_repo,
        dockerfile_content,
        image_name,
        build_commands,
        test_commands,
        run_build,
        workdir,
    )

    # Clear the knowledge graph from Neo4j after use
    await knowledge_graph_service.clear_kg(knowledge_graph.root_node_id)
    # Clear the repository from the repository service
    shutil.rmtree(repo_path)

    # Return the reproduction results
    return reproduced_bug, reproduced_bug_file, reproduced_bug_commands, reproduced_bug_patch


async def process_issue(
    github_issue: dict,
    github_token: str,
    predictions: dict,
    file: str,
    run_build: bool,
    semaphore: asyncio.Semaphore,
    lock: asyncio.Lock,
):
    """Process a single GitHub issue with concurrency control.

    This function processes one issue from a SWE-bench dataset, extracting issue information,
    reproducing the bug, and saving results to a predictions file in a thread-safe manner.

    Args:
        github_issue: Dictionary containing SWE-bench issue data with keys:
            - "repo": Repository name (e.g., "django/django")
            - "instance_id": Unique instance identifier
            - "base_commit": Commit hash to reproduce the bug at
            - "problem_statement": Issue title and description
        github_token: GitHub access token for repository access.
        predictions: Shared dictionary to store reproduction results (modified in-place).
        file: Path to JSON file for persisting predictions.
        run_build: Whether to run build commands in the container.
        semaphore: Asyncio semaphore for controlling concurrent workers.
        lock: Asyncio lock for thread-safe file writes.

    Side Effects:
        - Updates the shared predictions dictionary
        - Writes predictions to the specified JSON file
        - Creates and cleans up Docker containers
        - Clones and removes Git repositories
    """
    async with semaphore:
        # Get Issue information
        repo_prefix = github_issue["repo"].split("/")[0]
        instance_id = github_issue["instance_id"].split("__")[-1]
        image_name = SWEBENCH_IMAGE_FORMAT.format(repo_prefix=repo_prefix, instance_id=instance_id)
        github_url = GITHUB_HTTPS_URL.format(repo_name=github_issue["repo"])
        commit_id = github_issue["base_commit"]
        problem_statement_lines = github_issue["problem_statement"].splitlines()
        issue_title = problem_statement_lines[0]
        issue_body = "\n".join(problem_statement_lines[1:])
        build_commands = get_build_commands(github_issue) if run_build else None

        # Reproduce the bug
        (
            reproduced_bug,
            reproduced_bug_file,
            reproduced_bug_commands,
            reproduced_bug_patch,
        ) = await reproduce_bug(
            issue_title,
            issue_body,
            [],
            github_url,
            github_token,
            commit_id,
            None,
            image_name,
            build_commands,
            None,
            run_build,
            "/testbed",
        )

        # Thread-safe update of predictions
        async with lock:
            predictions[github_issue["instance_id"]] = {
                "reproduced_bug": reproduced_bug,
                "reproduced_bug_file": str(reproduced_bug_file),
                "reproduced_bug_commands": reproduced_bug_commands,
                "reproduced_bug_patch": reproduced_bug_patch,
            }

            with open(file, "w", encoding="utf-8") as f:
                json.dump(predictions, f, indent=4, ensure_ascii=False)


async def async_main(
    dataset_name: str,
    github_token: str,
    file: str,
    run_build: bool,
    max_workers: int,
    instance_ids: list[str] | None = None,
):
    """Main asynchronous entry point for processing SWE-bench issues concurrently.

    Coordinates the parallel processing of multiple GitHub issues from a SWE-bench dataset,
    managing service lifecycle, concurrency limits, and progress tracking.

    Args:
        dataset_name: Name of the Hugging Face SWE-bench dataset to load.
        github_token: GitHub access token for repository operations.
        file: Path to JSON file for saving/loading predictions.
        run_build: Whether to execute build commands in Docker containers.
        max_workers: Maximum number of concurrent issue processing tasks.
        instance_ids: Optional list of specific instance IDs to process (None processes all).

    Workflow:
        1. Start all services (Neo4j, database, knowledge graph, etc.)
        2. Load and optionally filter the SWE-bench dataset
        3. Process issues concurrently with semaphore-based rate limiting
        4. Display progress bar using tqdm
        5. Save predictions incrementally to JSON file
        6. Close all services gracefully

    Side Effects:
        - Initializes and tears down database connections
        - Creates/removes Docker containers
        - Writes predictions to disk
        - Clones/removes Git repositories
    """
    # Starting services
    for service in services.values():
        # Start each service, handling both async and sync start methods
        if inspect.iscoroutinefunction(service.start):
            await service.start()
        else:
            service.start()

    dataset = load_dataset(dataset_name)
    filtered_dataset = dataset["test"]

    # Filter by instance_ids if provided
    if instance_ids:
        filtered_dataset = [
            issue for issue in filtered_dataset if issue["instance_id"] in instance_ids
        ]
        print(f"Dataset loaded: {dataset_name}, filtered to {len(filtered_dataset)} issues")
        print(f"Instance IDs: {instance_ids}")
    else:
        print(f"Dataset loaded: {dataset_name}, total {len(filtered_dataset)} issues")

    print(f"Max workers: {max_workers}")

    # Load existing predictions if file exists
    predictions = {}
    if Path(file).exists():
        with open(file, encoding="utf-8") as f:
            predictions = json.load(f)
        print(f"Loaded {len(predictions)} existing predictions from {file}")

    # Filter out already processed issues
    remaining_dataset = [
        issue for issue in filtered_dataset if issue["instance_id"] not in predictions
    ]

    if len(remaining_dataset) < len(filtered_dataset):
        print(f"Skipping {len(filtered_dataset) - len(remaining_dataset)} already processed issues")
        print(f"Remaining issues to process: {len(remaining_dataset)}")

    semaphore = asyncio.Semaphore(max_workers)
    lock = asyncio.Lock()

    # Create tasks for remaining issues only
    tasks = [
        process_issue(github_issue, github_token, predictions, file, run_build, semaphore, lock)
        for github_issue in remaining_dataset
    ]

    # Process tasks with progress bar
    for coro in async_tqdm.as_completed(tasks, total=len(tasks)):
        await coro

    # Closing services
    for service in services.values():
        # Close each service, handling both async and sync close methods
        if inspect.iscoroutinefunction(service.close):
            await service.close()
        else:
            service.close()


@click.command()
@click.option(
    "--dataset_name",
    "-d",
    required=True,
    help="Name of the SWE bench dataset generate patches",
)
@click.option(
    "--github_token",
    "-g",
    help="Github token to access private repositories",
    default=None,
)
@click.option(
    "--file",
    "-f",
    help="File to save the predictions or continue patch generating.",
    default=f"predictions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
)
@click.option(
    "--run_build",
    type=bool,
    help="Run build command inside the container",
    default=True,
)
@click.option(
    "--max_workers",
    "-w",
    help="Maximum number of concurrent workers",
    type=int,
    default=1,
)
@click.option(
    "--instance_id",
    "-i",
    multiple=True,
    help="Filter dataset by specific instance_id(s). Can be specified multiple times.",
)
def main(
    dataset_name: str,
    github_token: str,
    file: str,
    run_build: bool,
    max_workers: int,
    instance_id: tuple[str, ...],
):
    """CLI entry point for the Prometheus Bug Reproduction Agent.

    Converts command-line arguments to appropriate types and launches the async main function.

    Args:
        dataset_name: Name of the SWE-bench dataset from Hugging Face.
        github_token: GitHub personal access token.
        file: JSON file path for predictions.
        run_build: Flag to enable/disable build command execution.
        max_workers: Number of concurrent workers for parallel processing.
        instance_id: Tuple of instance IDs to filter (from --instance_id flags).
    """
    # Convert tuple of instance IDs to list (None if empty)
    instance_ids = list(instance_id) if instance_id else None
    # Run the async main function
    asyncio.run(async_main(dataset_name, github_token, file, run_build, max_workers, instance_ids))


if __name__ == "__main__":
    main()
