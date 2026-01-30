
import os
import logging
from pathlib import Path
from typing import List, Dict, Optional, Set
import networkx as nx
import tree_sitter_python
import tree_sitter_cpp
from tree_sitter import Language, Parser

logger = logging.getLogger(__name__)

class RepoScanner:
    """
    Recursively scans a repository, parsing files to understand structure and dependencies.
    """
    def __init__(self, root_path: Path):
        self.root_path = root_path.resolve()
        self.ignore_dirs = {'.git', 'venv', '.venv', '__pycache__', 'node_modules', 'build', 'dist', '.idea', '.vscode'}
        
        # Initialize Parsers
        self.parsers = {}
        try:
            py_lang = Language(tree_sitter_python.language())
            cpp_lang = Language(tree_sitter_cpp.language())
            
            self.parsers['.py'] = Parser()
            self.parsers['.py'].language = py_lang
            
            self.parsers['.cpp'] = Parser()
            self.parsers['.cpp'].language = cpp_lang
            self.parsers['.hpp'] = Parser()
            self.parsers['.hpp'].language = cpp_lang
            self.parsers['.h'] = Parser()
            self.parsers['.h'].language = cpp_lang
        except Exception as e:
            logger.warning(f"Failed to initialize tree-sitter parsers: {e}")

    def scan(self) -> List[Path]:
        """
        Recursively find all source files in the repository.
        """
        source_files = []
        for root, dirs, files in os.walk(self.root_path):
            # Modify dirs in-place to prune ignored directories
            dirs[:] = [d for d in dirs if d not in self.ignore_dirs]
            
            for file in files:
                file_path = Path(root) / file
                if file_path.suffix in ['.py', '.cpp', '.hpp', '.h', '.java']:
                    source_files.append(file_path)
        
        logger.info(f"Scanned {len(source_files)} source files in {self.root_path}")
        return source_files

    def parse_file(self, file_path: Path) -> Dict:
        """
        Parse a single file to extract imports and symbols.
        """
        if not file_path.exists():
            return {}

        ext = file_path.suffix
        if ext not in self.parsers:
            return {"path": file_path, "imports": [], "symbols": []}

        content = file_path.read_bytes()
        tree = self.parsers[ext].parse(content)
        root_node = tree.root_node
        
        imports = self._extract_imports(root_node, ext)
        symbols = self._extract_symbols(root_node, ext)
        
        return {
            "path": file_path,
            "imports": imports,
            "symbols": symbols
        }

    def _extract_imports(self, node, ext: str) -> List[str]:
        # Regex fallback because tree-sitter-python bindings structure is unclear/changed
        # and causing AttributeErrors.
        imports = []
        if ext == '.py':
            import re
            content = node.text.decode('utf-8')
            
            # Matches: from utils import MathUtils -> utils
            from_imports = re.findall(r'from\s+([\w\.]+)\s+import', content)
            imports.extend(from_imports)
            
            # Matches: import os, sys -> os, sys (needs split)
            # Simplified: Matches 'import os' (one line)
            direct_imports = re.findall(r'^import\s+([^\n]+)', content, re.MULTILINE)
            for imp_str in direct_imports:
                for x in imp_str.split(','):
                    imports.append(x.strip())
        
        return imports

    def export_index_json(self) -> Dict:
        """
        Export the repository index matching the V2 Schema.
        """
        import hashlib
        
        repo_data = {
            "repo_rev": "HEAD", # Placeholder, ideally get from git
            "languages": ["python", "cpp"],
            "files": []
        }
        
        # We need to re-scan or use cached data. Ideally parse_file caches results.
        # For MVP, we'll scan and parse on demand if not cached, but here we assume caller manages flow.
        # Let's iterate over all known files. 
        # Since scan() returns a list, we might want to store state.
        # But to be stateless-ish, let's just re-scan if we don't have internal storage.
        # The V2 design implies the scanner maintains some state or returns this big object.
        
        # Let's scan now 
        files = self.scan()
        for f in files:
            data = self.parse_file(f)
            
            # Compute Hash
            content_bytes = f.read_bytes()
            content_hash = hashlib.sha1(content_bytes).hexdigest()
            
            # Format according to Schema
            file_entry = {
                "path": str(f.relative_to(self.root_path)),
                "lang": "python" if f.suffix == '.py' else "cpp",
                "hash": content_hash,
                "symbols": data.get("symbols", []),
                "imports": data.get("imports", []),
                "exports": [] # simplifying for now
            }
            repo_data["files"].append(file_entry)
            
        return repo_data

    def _extract_symbols(self, node, ext: str) -> List[Dict]:
        """
        Extracts symbols with V2 Schema (id, kind, name, range).
        """
        symbols = []
        import re
        
        if ext == '.py':
            content = node.text.decode('utf-8')
            lines = content.splitlines()
            
            # Regex is weak for ranges, but tree-sitter node would be better if fully used.
            # However, `node` passed here IS the tree-sitter root_node.
            # Let's try to use tree-sitter queries if possible, else regex with simulated ranges.
            
            # Since the current implementation used regex, and tree-sitter boilerplate is heavy, 
            # I will upgrade to basic Tree-Sitter usage if I can find the children.
            # But the `node` object is available!
            
            def traverse(n):
                if n.type in ('function_definition', 'class_definition'):
                    name_node = n.child_by_field_name('name')
                    name = name_node.text.decode('utf-8') if name_node else "anonymous"
                    
                    kind = "function" if n.type == 'function_definition' else "class"
                    # Range: [start_line, end_line] (0-indexed in TS, but usually we want 1-indexed or 0-indexed consistent)
                    # Agent Spec example used [120, 220]. Let's use 0-indexed start, end line.
                    rng = [n.start_point[0], n.end_point[0]]
                    
                    # ID: kind:name
                    sym_id = f"sym:{name}" 
                    
                    symbols.append({
                        "id": sym_id,
                        "kind": kind,
                        "name": name,
                        "range": rng,
                        "signature": name + "(...)" # Simplified signature
                    })
                
                for child in n.children:
                    traverse(child)

            try:
                traverse(node)
            except Exception as e:
                logger.warning(f"Tree-sitter traversal failed: {e}, falling back to regex")
                # Fallback Regex (Range is harder here, mocking 0-0)
                classes = re.findall(r'class\s+(\w+)', content)
                for c in classes:
                    symbols.append({"id": f"sym:{c}", "kind": "class", "name": c, "range": [0,0]})
                funcs = re.findall(r'def\s+(\w+)', content)
                for f in funcs:
                    symbols.append({"id": f"sym:{f}", "kind": "function", "name": f, "range": [0,0]})
                    
        return symbols

    def build_dependency_graph(self, files: List[Path]) -> nx.DiGraph:
        """
        Builds a NetworkX DiGraph representing file dependencies.
        """
        graph = nx.DiGraph()
        
        # Add nodes
        for f in files:
            graph.add_node(str(f.relative_to(self.root_path)))

        # Add edges (Naive name matching for now, improve with detailed import resolution)
        # TODO: Implement full import resolution logic
        
        return graph
