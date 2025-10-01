import asyncio
import inspect
import json
import logging
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
from app.lang_graph.subgraphs.bug_reproduction_subgraph import BugReproductionSubgraph
from app.services.database_service import DatabaseService
from app.services.knowledge_graph_service import KnowledgeGraphService
from app.services.llm_service import LLMService
from app.services.neo4j_service import Neo4jService
from app.services.repository_service import RepositoryService

SWEBENCH_IMAGE_FORMAT = "swebench/sweb.eval.x86_64.{repo_prefix}_1776_{instance_id}:v1"

GITHUB_HTTPS_URL = "https://github.com/{repo_name}.git"

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
    workdir: str = None,
) -> tuple[bool, None, None, None] | tuple[bool, str, str, str]:
    # Set up a dedicated logger for this thread
    logger = logging.getLogger(f"thread-{threading.get_ident()}.app")
    logger.setLevel(getattr(logging, settings.LOGGING_LEVEL))
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = LOG_DIR / f"{timestamp}_{threading.get_ident()}.log"
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

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

    # Clear the knowledge graph from Neo4j after use
    await knowledge_graph_service.clear_kg(knowledge_graph.root_node_id)
    # Clear the repository from the repository service
    repo_path.rmdir()

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


async def process_issue(
    github_issue: dict,
    github_token: str,
    predictions: dict,
    file: str,
    semaphore: asyncio.Semaphore,
    lock: asyncio.Lock,
):
    """Process a single GitHub issue with concurrency control."""
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
            None,
            None,
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
    max_workers: int,
    instance_ids: list[str] | None = None,
):
    """Async main function to process issues concurrently."""
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

    predictions = {}
    semaphore = asyncio.Semaphore(max_workers)
    lock = asyncio.Lock()

    # Create tasks for all issues
    tasks = [
        process_issue(github_issue, github_token, predictions, file, semaphore, lock)
        for github_issue in filtered_dataset
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
    max_workers: int,
    instance_id: tuple[str, ...],
):
    instance_ids = list(instance_id) if instance_id else None
    asyncio.run(async_main(dataset_name, github_token, file, max_workers, instance_ids))


if __name__ == "__main__":
    main()
