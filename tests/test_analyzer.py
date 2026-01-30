"""Tests for Python analyzer."""

from pathlib import Path

import pytest

from mvp_agent.analyzer import Analyzer, ClassInfo, FunctionInfo, ModuleInfo


class TestAnalyzer:
    """Tests for the Analyzer class."""

    def test_analyze_simple_function(self) -> None:
        """Test analyzing a simple function."""
        source = '''
def hello(name: str) -> str:
    """Say hello."""
    return f"Hello, {name}"
'''
        analyzer = Analyzer()
        result = analyzer.analyze_source(source)

        assert len(result.functions) == 1
        func = result.functions[0]
        assert func.name == "hello"
        assert "name: str" in func.args
        assert func.return_type == "str"

    def test_analyze_class(self) -> None:
        """Test analyzing a class."""
        source = '''
class Greeter:
    """A greeter class."""

    def __init__(self, name: str):
        self.name = name

    def greet(self) -> str:
        return f"Hello, {self.name}"
'''
        analyzer = Analyzer()
        result = analyzer.analyze_source(source)

        assert len(result.classes) == 1
        cls = result.classes[0]
        assert cls.name == "Greeter"
        assert len(cls.methods) == 2

    def test_analyze_imports(self) -> None:
        """Test analyzing imports."""
        source = '''
import os
from pathlib import Path
'''
        analyzer = Analyzer()
        result = analyzer.analyze_source(source)

        assert "os" in result.imports
        assert "pathlib.Path" in result.imports

    def test_to_summary(self) -> None:
        """Test summary generation."""
        source = '''
class Calculator:
    def add(self, a: int, b: int) -> int:
        return a + b
'''
        analyzer = Analyzer()
        result = analyzer.analyze_source(source)
        summary = analyzer.to_summary(result)

        assert "Calculator" in summary
        assert "add" in summary
