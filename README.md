# MVP Refactoring Agent

An autonomous agent that converts Python code to C++ using LLM (Ollama).

## Features

- Python → C++ language conversion
- Auto unit test generation
- Git branch isolation + rollback
- Debug logging

## Usage

```bash
cd MVP_agent
uv sync
uv run python -m mvp_agent.main --source <python_file> --output ./output
```

## Architecture

- `llm_client.py`: Ollama API wrapper
- `analyzer.py`: Python AST analysis
- `planner.py`: Task planning
- `executor.py`: C++ code generation
- `test_generator.py`: Unit test generation
- `verifier.py`: Compile & test verification
- `git_manager.py`: Git operations for rollback
