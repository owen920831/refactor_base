"""Agent for generating CMake build files for refactored C++ code."""

import logging
from pathlib import Path
from typing import List
from mvp_agent.core.llm_client import LLMClient

logger = logging.getLogger(__name__)

class CMakeGenerator:
    """Generates CMakeLists.txt files for a refactored repository."""

    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client

    def generate_root_cmake(self, output_dir: Path, source_files: List[Path]) -> str:
        """Generate a root CMakeLists.txt file.
        
        Args:
            output_dir: The root of the refactored project.
            source_files: List of all generated C++ files (relative to output_dir).
        """
        # Group files into potential executables or libraries
        # Simple heuristic: one executable per directory or just one big project
        
        file_list_str = "\n".join([f"    {str(f)}" for f in source_files if f.suffix in ('.cpp', '.cc', '.c') or f.suffix in ('.hpp', '.h')])
        
        user_prompt = f"""Generate a modern CMakeLists.txt for a C++ project.
        
        # Project Structure
        The project contains the following files:
        {file_list_str}
        
        # Requirements
        1. Use C++17 or higher.
        2. Include Google Test (via FetchContent) and add tests for files starting with 'test_'.
        3. Create a single library or multiple targets as appropriate for the structure.
        4. Use `target_include_directories` to handle the hierarchy.
        5. The project name should be 'RefactoredKatas'.
        
        Return ONLY the content of the CMakeLists.txt file. No markdown fences.
        """
        
        response = self.llm_client.generate_with_retry(
            prompt=user_prompt,
            system_prompt="You are a CMake architecture expert. Generate clean, modular CMakeLists.txt files."
        )
        
        if response.error:
            logger.error(f"Failed to generate CMakeLists.txt: {response.error}")
            return ""
            
        content = response.content.strip()
        # Basic cleanup if fences are included
        if content.startswith("```"):
            lines = content.split("\n")
            if lines[0].startswith("```"): lines = lines[1:]
            if lines[-1].startswith("```"): lines = lines[:-1]
            content = "\n".join(lines).strip()
            
        cmake_file = output_dir / "CMakeLists.txt"
        cmake_file.write_text(content, encoding="utf-8")
        logger.info(f"Generated root CMakeLists.txt at {cmake_file}")
        return content
