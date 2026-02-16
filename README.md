# Prometheus Bug Reproduction Agent

This agent is used for automatically reproducing software bugs by utilizing large language models (LLMs) and knowledge graphs to analyze issues in GitHub repositories and attempt to reproduce them.

## Features

* Automatically clones GitHub code repositories
* Builds and stores code knowledge graphs
* Uses LLMs to analyze issue descriptions
* Reproduces bugs in a containerized environment
* Generates bug reproduction files, commands, and patches
* Supports batch testing with the SWE-bench dataset

## Requirements

* Python 3.11+
* Neo4j database
* Docker
* Git

## 📦 Setup
1. ### Install dependencies:

   ```bash
   pip install hatchling
   pip install .
   pip install git+https://github.com/SWE-bench/SWE-bench@v4.1.0
   ```
2. ### Create the working directory to store logs and cloned repositories:

   ```bash
   mkdir working_dir
   ```

## Configuration

Before use, you need to set the following environment variables or configuration files:

* NEO4J related configurations (URI, username, password)
* LLM related API keys (OpenAI, Anthropic, Gemini, etc.)
* Working directory path
* GitHub access token (for private repositories)

## Usage

### Command-line execution

```bash
python -m app.main --dataset_name="your_dataset" --github_token="your_token"
```

### Parameter Description

* `--dataset_name`, `-d`: SWE-bench dataset name (required)
* `--github_token`, `-g`: GitHub access token (optional)
* `--file`, `-f`: File to save the prediction results (defaults to `predictions_XXX.json` with a timestamp)

## Start Services

### PostgreSQL Service

Start PostgreSQL using Docker:

```bash
docker run -d \
  -p 5432:5432 \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=password \
  -e POSTGRES_DB=postgres \
  postgres
```

### Neo4j Service

Start Neo4j using Docker:

```bash
docker run -d \
  -p 7474:7474 \
  -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/password \
  -e NEO4J_PLUGINS='["apoc"]' \
  -e NEO4J_dbms_memory_heap_initial__size=4G \
  -e NEO4J_dbms_memory_heap_max__size=8G \
  -e NEO4J_dbms_memory_pagecache_size=4G \
  neo4j
```

You should first start neo4j service then setting the config of you neo4j

## Workflow

1. Load test cases from the SWE-bench dataset
2. Clone the GitHub repository locally
3. Build the code knowledge graph
4. Initialize the container environment (user-defined or generic container)
5. Call the bug reproduction subgraph for analysis and reproduction
6. Save the reproduction results (success/failure, related files, commands, and patches)

## Project Structure

* `app/main.py`: Main program entry
* `app/configuration/`: Configuration-related code
* `app/docker/`: Docker container management code
* `app/lang_graph/`: Language graph-related code
* `app/services/`: Various service implementations (knowledge graph, repository, LLM, etc.)

## Notes

* Ensure Docker service is running
* For private repositories, provide a valid GitHub token
* Large repositories may require more time and memory for analysis
