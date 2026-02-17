<div align="center">

<img src="./docs/images/echo.jpg" alt="Echo Logo" width="200">
  <h1 style="border-bottom: none;">
    <b><a href="https://euni.ai/" target="_blank">Echo</a></b><br>
    ⚡ Automated Bug Reproduction Agent powered by LLMs & Knowledge Graphs ⚡
  </h1>

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org)
[![Docker](https://img.shields.io/badge/docker-required-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://www.docker.com)
[![Neo4j](https://img.shields.io/badge/neo4j-knowledge_graph-4581C3?style=for-the-badge&logo=neo4j&logoColor=white)](https://neo4j.com)

---

Echo analyzes GitHub issues, builds code knowledge graphs, and reproduces bugs in isolated Docker environments — all automatically.

</div>

## Highlights

- **Knowledge Graph Analysis** — Builds AST-based code knowledge graphs for deep codebase understanding
- **LLM-Powered Reasoning** — Leverages large language models to interpret issues and generate reproductions
- **Containerized Execution** — Runs all reproductions in isolated Docker environments
- **Batch Processing** — Supports SWE-bench datasets with parallel workers
- **Automatic Patch Generation** — Produces reproduction files, test commands, and diff patches

## Prerequisites

| Dependency | Version |
|------------|---------|
| Python | 3.11+ |
| Docker | Latest |
| Neo4j | Latest |
| Git | Latest |

## Quick Start

### 1. Install

```bash
pip install hatchling
pip install .
pip install git+https://github.com/SWE-bench/SWE-bench@v4.1.0
```

### 2. Start Services

<details>
<summary><b>PostgreSQL</b></summary>

```bash
docker run -d \
  -p 5432:5432 \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=password \
  -e POSTGRES_DB=postgres \
  postgres
```

</details>

<details>
<summary><b>Neo4j</b> (start before configuring)</summary>

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

</details>

### 3. Configure

Copy `example.env` to `.env` and fill in:

- **Neo4j** — URI, username, password
- **Database** — PostgreSQL connection string
- **LLM API Keys** — Anthropic / Gemini / OpenAI-compatible
- **Working Directory** — Path for logs and cloned repos

### 4. Create Working Directory

```bash
mkdir working_dir
```

### 5. Run

```bash
# Single instance
python -m app.main -d "princeton-nlp/SWE-bench_Lite" -i "instance_id"

# Multiple instances
python -m app.main -d "princeton-nlp/SWE-bench_Lite" -i "id_1" -i "id_2"

# Full dataset with parallel workers
python -m app.main -d "princeton-nlp/SWE-bench_Lite" -w 3

# With GitHub token
python -m app.main -d "dataset_name" -g "your_github_token"

# Resume from predictions file
python -m app.main -d "dataset_name" -f "predictions_20231215_143022.json"
```

## How It Works

```
GitHub Issue ─→ Clone Repo ─→ Build Knowledge Graph ─→ Init Container
                                                            │
                ┌───────────────────────────────────────────┘
                ▼
         LLM Analysis ─→ Generate Patch ─→ Execute in Container
                │                                    │
                │         ┌──────────────────────────┘
                │         ▼
                │    Bug Reproduced?
                │     ├─ Yes → Save Results (patch, tests, commands)
                └─────┤
                      └─ No  → Retry with refined context
```

## Project Structure

```
app/
├── main.py              # Entry point & async orchestration
├── configuration/       # Settings via pydantic-settings
├── docker/              # Container management (pexpect-based)
├── lang_graph/          # LangGraph state machines & nodes
│   └── nodes/           # Individual workflow nodes
└── services/            # Core services
    ├── knowledge_graph  # Neo4j knowledge graph builder
    ├── repository       # Git operations
    ├── llm              # Model initialization
    └── database         # PostgreSQL interactions
```

## Notes

- Docker must be running before starting Echo
- Provide a valid GitHub token for private repositories
- Large repositories may require more time and memory for analysis
- Knowledge graphs are cleared after each issue to manage Neo4j memory