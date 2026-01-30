
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
            # Simplified: Matches 'import os'
            direct_imports = re.findall(r'^import\s+([\w\.,\s]+)', content, re.MULTILINE)
            for imp_str in direct_imports:
                for x in imp_str.split(','):
                    imports.append(x.strip())
        
        return imports

    def _extract_symbols(self, node, ext: str) -> List[str]:
        symbols = []
        if ext == '.py':
            import re
            content = node.text.decode('utf-8')
            classes = re.findall(r'class\s+(\w+)', content)
            funcs = re.findall(r'def\s+(\w+)', content)
            symbols.extend(classes)
            symbols.extend(funcs)
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
