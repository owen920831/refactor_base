# MVP Agent V2 Specifications

## 1. State & Artifacts Layout

```text
workspace/
  repo/                 # Original repo clone (read-only)
  worktrees/
    run_<timestamp>/    # Working tree for specific run
  state/
    index.json          # Repo Index (Symbols, Files)
    dep_graph.json      # Dependency Graph
    repomap.txt         # Compressed repository map
    rag_index/          # Vector store for chunks
    plan_history.jsonl  # History of plan execution
    runs/run_<id>.json  # Run metadata
  artifacts/
    run_<timestamp>/
      iter_<N>/
        eval.md
        plan.md
        logs/
        patches/
```

## 2. Index Formats

### Repo Index (index.json)

```json
{
  "repo_rev": "git_sha",
  "languages": ["python", "cpp"],
  "files": [
    {
      "path": "src/main.py",
      "lang": "python",
      "hash": "sha1",
      "symbols": [
        {
          "id": "sym:main.main",
          "kind": "function",
          "name": "main",
          "range": [10, 20]
        }
      ],
      "imports": ["src/utils.py"],
      "exports": ["main"]
    }
  ]
}
```

### Dependency Graph (dep_graph.json)

```json
{
  "nodes": [{ "id": "file:src/main.py", "type": "file" }],
  "edges": [
    { "src": "file:src/main.py", "dst": "file:src/utils.py", "type": "imports" }
  ]
}
```

### RAG Chunk DB

**Critical:** Chunks must have symbol/file/range to prevent hallucination.

```json
{
  "chunk_id": "ck_123",
  "path": "src/utils.py",
  "range": [50, 100],
  "symbol_ids": ["sym:utils.helper"],
  "text": "def helper(): ...",
  "embedding": [...]
}
```

## 3. Planning Schema (Task DAG)

**Planner Output:**

```json
{
  "iteration": 1,
  "milestones": [
    {
      "id": "M1",
      "goal": "baseline passed",
      "tasks": [
        {
          "id": "T1",
          "intent": "refactor_class",
          "retrieval": [
            { "kind": "repomap" },
            { "kind": "graph_neighbors", "node": "file:src/main.py", "hops": 1 }
          ],
          "edit_budget": { "max_files": 2 },
          "deliverables": ["src/main.cpp"]
        }
      ]
    }
  ]
}
```

## 4. Context Pack Contract

The Context Packer selects the most relevant information to fit within the token budget.

```json
{
  "task_id": "T1",
  "token_budget": 12000,
  "repomap_excerpt": "... (Global Skeleton) ...",
  "snippets": [{ "path": "src/main.py", "range": [10, 50], "text": "..." }],
  "evidence": [{ "type": "build_log", "text": "Error at line 12..." }]
}
```

## 5. Execution Contracts

### Worker Output

Workers must output either:

1. **JSON**: For plans, decisions, reports.
2. **Unified Diff**: For code changes (to be applied via `git apply`).

### Error Classification & Rollback

- **Build/Config Error**: Fix scaffold/CMake.
- **Compile Error**: Graph neighbor search + Fix types.
- **Test Failure**: RAG for logic + Fix implementation.
- **Max Retries**: 3 attempts per task -> Rollback or Reduce Scope.

## 6. Test/Build Interface

Adapters for different languages:

- **Python**: `pytest`, `pytest-cov`
- **C++**: `cmake`, `ctest`, `gtest`

## 7. Cost Control

- **Planner**: High intelligence model (e.g., Claude 3.5 Sonnet / GPT-4o)
- **Executor**: Coding model (e.g., GPT-4o / DeepSeek V3)
- **Reviewer**: Helper model (e.g., Haiku / GPT-4o-mini)
