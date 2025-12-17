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
* Docker
* Git
* **Prometheus-Context-Retrieval-Agent** (required dependency for context retrieval functionality)

## 📦 Setup

### 1. Install Prometheus-Context-Retrieval-Agent (Required)

This project depends on the Prometheus-Context-Retrieval-Agent service for context retrieval functionality. You need to set up and run this service first.

Please follow the setup instructions at: [Prometheus-Context-Retrieval-Agent Repository](https://github.com/EuniAI/Prometheus-Context-Collector.git)

Make sure the Context Retrieval Agent service is running and accessible before proceeding.

### 2. Install dependencies:

   ```bash
   pip install hatchling
   pip install .
   pip install git+https://github.com/SWE-bench/SWE-bench@v4.1.0
   ```

### 3. Create the working directory to store logs and cloned repositories:

   ```bash
   mkdir working_dir
   ```

## Configuration

Before use, you need to set the following environment variables or configuration files:

* **Context Retrieval Agent URL**: `PROMETHEUS_CRA_BASE_URL` - Base URL for the Prometheus-Context-Retrieval-Agent service
* LLM related API keys (OpenAI, Anthropic, Gemini, DeepSeek, etc.)
* Working directory path: `PROMETHEUS_WORKING_DIRECTORY`
* GitHub access token (for private repositories)
* Model configurations:
  - `PROMETHEUS_ADVANCED_MODEL`: Advanced model name (e.g., "deepseek-chat", "gpt-4")
  - `PROMETHEUS_BASE_MODEL`: Base model name
  - Temperature settings for both models (optional)

Example `.env` file:
```bash
PROMETHEUS_CRA_BASE_URL=http://localhost:8000
PROMETHEUS_WORKING_DIRECTORY=/path/to/working_dir
PROMETHEUS_ADVANCED_MODEL=deepseek-chat
PROMETHEUS_BASE_MODEL=deepseek-chat
PROMETHEUS_OPENAI_FORMAT_BASE_URL=https://api.deepseek.com
PROMETHEUS_OPENAI_FORMAT_API_KEY=your_api_key_here
```

## Usage

### Command-line execution

```bash
python -m app.main \
  --dataset_name "princeton-nlp/SWE-bench_Lite" \
  --patch_file "patches.json" \
  --instance_id "django__django-11999" \
  --max_workers 1
```

### Parameter Description

* `--dataset_name`, `-d`: SWE-bench dataset name (required)
* `--patch_file`, `-p`: Path to patches.json file containing model patches (required)
* `--instance_id`, `-i`: Filter dataset by specific instance ID(s). Can be specified multiple times (optional)
* `--max_workers`, `-w`: Maximum number of concurrent workers (default: 1)
* `--github_token`, `-g`: GitHub access token (optional)
* `--file`, `-f`: File to save the prediction results (defaults to `predictions_XXX.json` with a timestamp)
* `--run_build`: Whether to run build commands in the container (default: true)

### Examples

Test a single instance:
```bash
python -m app.main -d "princeton-nlp/SWE-bench_Lite" -p "patches.json" -i "django__django-11999"
```

Test multiple instances with 3 workers:
```bash
python -m app.main \
  -d "princeton-nlp/SWE-bench_Lite" \
  -p "patches.json" \
  -i "django__django-11999" \
  -i "astropy__astropy-14365" \
  -w 3
```

Process entire dataset:
```bash
python -m app.main -d "princeton-nlp/SWE-bench_Lite" -p "patches.json" -w 5
```

## Required Services

This project requires the following services to be running:

### 1. Prometheus-Context-Retrieval-Agent Service

The Context Retrieval Agent must be running and accessible. This service handles:
- Neo4j database for knowledge graph storage
- Code context retrieval functionality
- Repository upload and processing

Refer to the [Prometheus-Context-Retrieval-Agent documentation](https://github.com/your-org/Prometheus-Context-Retrieval-Agent) for setup instructions.

### 2. Docker Service

Ensure Docker is running on your system for container-based bug reproduction.

## Workflow

1. Load test cases from the SWE-bench dataset and patches from patches.json
2. Clone the GitHub repository locally
3. Upload repository to Context Retrieval Agent for knowledge graph construction
4. Initialize the container environment (SWE-bench specific or generic container)
5. Call the bug reproduction subgraph for analysis and reproduction:
   - Retrieve relevant code context using the Context Retrieval Agent
   - Generate bug reproduction code using LLM with the provided patch
   - Execute the reproduction in Docker container
   - Verify if the bug is properly reproduced
6. Save the reproduction results (success/failure, related files, commands, and patches)

## Project Structure

* `app/main.py`: Main program entry
* `app/configuration/`: Configuration-related code
* `app/docker/`: Docker container management code
* `app/lang_graph/`: Language graph-related code
* `app/services/`: Various service implementations (knowledge graph, repository, LLM, etc.)

## Notes

* **IMPORTANT**: Ensure the Prometheus-Context-Retrieval-Agent service is running and accessible before starting bug reproduction
* Ensure Docker service is running
* Neo4j service must be running and accessible by the Context Retrieval Agent
* For private repositories, provide a valid GitHub token
* Large repositories may require more time and memory for analysis
* The `patches.json` file must contain patches for all instances you want to test
* Patches format: `{"instance_id": {"model_patch": "diff content", ...}}`
