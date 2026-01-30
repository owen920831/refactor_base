
import unittest
import json
import tempfile
import shutil
from pathlib import Path
from mvp_agent.cognition.scanner import RepoScanner
from mvp_agent.cognition.graph import DependencyGraph

class TestJSONSchemas(unittest.TestCase):
    def setUp(self):
        # Create a temporary test repo
        self.test_dir = Path(tempfile.mkdtemp())
        self.src_dir = self.test_dir / "src"
        self.src_dir.mkdir()
        
        # Create dummy files
        (self.src_dir / "main.py").write_text("import utils\ndef main():\n    pass")
        (self.src_dir / "utils.py").write_text("def helper():\n    pass")
        (self.src_dir / "ignored.txt").write_text("ignored")

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_repo_index_schema(self):
        """Test strict adherence to agent_spec.md for Repo Index."""
        scanner = RepoScanner(self.test_dir)
        files = scanner.scan()
        # Parse first to populate internal state if needed (though export should ideally handle it)
        # Assuming export_index_json might trigger parse or use cached parsing
        # For now, let's manually parse so the scanner has data
        for f in files:
            scanner.parse_file(f)
            
        index_json = scanner.export_index_json()
        
        # Schema Validation
        self.assertIn("repo_rev", index_json)
        self.assertIn("files", index_json)
        self.assertIsInstance(index_json["files"], list)
        
        # Check main.py entry
        main_entry = next((f for f in index_json["files"] if f["path"] == "src/main.py"), None)
        self.assertIsNotNone(main_entry)
        self.assertEqual(main_entry["lang"], "python")
        self.assertIn("hash", main_entry)
        # Check imports
        # allow 'utils' or 'src.utils' depending on parser implementation
        self.assertTrue(any("utils" in imp for imp in main_entry["imports"]))
        
        # Check Symbols (Critical for V2)
        # main() symbol
        main_sym = next((s for s in main_entry["symbols"] if "main" in s["name"]), None)
        self.assertIsNotNone(main_sym, "Symbol 'main' not found")
        self.assertIn("id", main_sym)
        self.assertIn("kind", main_sym)
        self.assertIn("range", main_sym) # Critical field
        self.assertIsInstance(main_sym["range"], list)
        self.assertEqual(len(main_sym["range"]), 2)

    def test_graph_json_schema(self):
        """Test strict adherence to agent_spec.md for Dependency Graph."""
        scanner = RepoScanner(self.test_dir)
        files = scanner.scan()
        parsed = [scanner.parse_file(f) for f in files]
        
        graph = DependencyGraph(self.test_dir)
        graph.build(parsed)
        
        graph_json = graph.to_json()
        
        self.assertIn("nodes", graph_json)
        self.assertIn("edges", graph_json)
        
        # Verify Node IDs
        node_ids = [n["id"] for n in graph_json["nodes"]]
        self.assertIn("file:src/main.py", node_ids)
        self.assertIn("file:src/utils.py", node_ids)
        
        # Verify Edges
        # main imports utils
        edge = next((e for e in graph_json["edges"] if e["src"] == "file:src/main.py"), None)
        self.assertIsNotNone(edge)
        self.assertEqual(edge["dst"], "file:src/utils.py")
        self.assertEqual(edge["type"], "imports")

if __name__ == '__main__':
    unittest.main()
