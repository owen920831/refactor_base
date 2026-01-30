# V2 Implementation Retrospective & Design Decisions

This document chronicles the technical challenges encountered while upgrading the MVP Refactoring Agent to support Repository-Scale Refactoring (Phase 5).

## 1. Scanner Challenge: Tree-sitting vs Regex

### Issue

During the implementation of `scanner.py`, we initially relied on `tree-sitter-python` (v0.25+) for robust parsing of import statements. However, we encountered significant API breaking changes:

- `Language.query()` was deprecated/removed.
- The `Query` object constructor changed signature.
- `Query.captures()` threw `AttributeError`, indicating methods were moved or renamed in the Python bindings without clear documentation in the installed version.

### Solution (Immediate Fix)

To unblock the feature, we implemented a **Regex Fallback** mechanism in `RepoScanner._extract_imports`.

- Pros: Immediate functionality for standard Python imports (`import x`, `from x import y`).
- Cons: Brittle for multi-line imports or commented-out code.
- Impact: Successfully built the dependency graph for `tests/repo_test`.

### Future Plan

Revisit `tree-sitter` integration once stable documentation/examples for the currently installed version (0.25.x) are available, or downgrade to a known stable version (0.21.x).

## 2. Dependency Graph & Context Management

### Design

We introduced `DependencyGraph` (using strict topological sort) and `ContextManager` (acting as a "Librarian").

- **Graph**: Correctly identifies that `main.py` depends on `utils.py`.
- **Context Injection**: When refactoring `main.py`, the agent retrieves the refactored C++ code of `utils.py`.

### Issue: Code Inlining

Currently, the `ContextManager` provides the **entire content** of the dependency (`utils.cpp`). The LLM, seeing the full implementation, tends to **inline** the dependency code (e.g., `class MathUtils`) directly into `main.cpp` to make it compile as a standalone unit.

- Result: Code duplication across files.
- Ideal: `main.cpp` should `#include "utils.hpp"`.

### Future Solution (Phase 6)

1.  **Header Separation**: Explciitly instruct the LLM to generate `.hpp` and `.cpp` files separately.
2.  **Interface Registry**: `ContextManager` should only store/provide the `.hpp` content (declarations), not the implementation.
3.  **Build System**: The agent must generate a `CMakeLists.txt` or `Makefile` to link the separate translation units.

## 3. Scalability: Context Window

For large files, injecting full dependency content will quickly exceed the context window (8k/32k tokens).

### Future Solution

Implement true **RAG with Vector DB**:

- Chunk files by function/class.
- Retrieve only the specific symbols used (e.g., retrieve `MathUtils::add` signature only, not the whole file).
