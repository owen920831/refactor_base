
import logging
import subprocess
import shutil
from abc import ABC, abstractmethod
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, List

logger = logging.getLogger(__name__)

@dataclass
class CommandResult:
    success: bool
    stdout: str
    stderr: str
    return_code: int

class BuildAdapter(ABC):
    """Abstract interface for build systems."""
    
    @abstractmethod
    def build(self, target_path: Path) -> CommandResult:
        pass

class TestAdapter(ABC):
    """Abstract interface for test runners."""
    
    @abstractmethod
    def run_tests(self, target_path: Path) -> CommandResult:
        pass

class CMakeAdapter(BuildAdapter):
    def build(self, target_path: Path) -> CommandResult:
        """
        Assumes target_path is the project root containing CMakeLists.txt
        """
        build_dir = target_path / "build"
        build_dir.mkdir(exist_ok=True)
        
        # Configure
        try:
            subprocess.run(
                ["cmake", ".."],
                cwd=build_dir,
                check=True,
                capture_output=True,
                text=True
            )
            # Build
            proc = subprocess.run(
                ["cmake", "--build", "."],
                cwd=build_dir,
                check=False,
                capture_output=True,
                text=True
            )
            return CommandResult(
                success=proc.returncode == 0,
                stdout=proc.stdout,
                stderr=proc.stderr,
                return_code=proc.returncode
            )
        except subprocess.CalledProcessError as e:
            return CommandResult(False, e.stdout or "", e.stderr or str(e), e.returncode)

class MakeAdapter(BuildAdapter):
    def build(self, target_path: Path) -> CommandResult:
        """Run make in target_path."""
        try:
            proc = subprocess.run(
                ["make"],
                cwd=target_path,
                check=False,
                capture_output=True,
                text=True
            )
            return CommandResult(
                success=proc.returncode == 0,
                stdout=proc.stdout,
                stderr=proc.stderr,
                return_code=proc.returncode
            )
        except Exception as e:
            return CommandResult(False, "", str(e), -1)

class PyTestAdapter(TestAdapter):
    def run_tests(self, target_path: Path) -> CommandResult:
        try:
            # Run pytest on the directory
            proc = subprocess.run(
                ["pytest", str(target_path)],
                check=False,
                capture_output=True,
                text=True
            )
            return CommandResult(
                success=proc.returncode == 0,
                stdout=proc.stdout,
                stderr=proc.stderr,
                return_code=proc.returncode
            )
        except Exception as e:
            return CommandResult(False, "", str(e), -1)
