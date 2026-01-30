"""Verifier for C++ code compilation and test execution.

Runs g++ compiler and test executables to validate generated code.
"""

from __future__ import annotations

import logging
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class VerificationResult:
    """Result of code verification."""

    compile_success: bool
    test_success: bool | None = None
    compile_error: str | None = None
    test_error: str | None = None
    test_output: str | None = None


class Verifier:
    """Verifies C++ code by compilation and test execution.

    Uses g++ for compilation and runs test executables.
    """

    def __init__(
        self,
        cpp_standard: str = "c++17",
        compiler: str = "g++",
        timeout: int = 30,
    ) -> None:
        """Initialize the verifier.

        Args:
            cpp_standard: C++ standard to use (default: c++17).
            compiler: Compiler command (default: g++).
            timeout: Timeout in seconds for commands.
        """
        self.cpp_standard = cpp_standard
        self.compiler = compiler
        self.timeout = timeout

    def check_compile(self, code: str, filename: str = "source.cpp") -> VerificationResult:
        """Check if C++ code compiles without errors.

        Args:
            code: C++ source code.
            filename: Filename for error messages.

        Returns:
            VerificationResult with compilation status.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            source_path = Path(tmpdir) / filename
            source_path.write_text(code, encoding="utf-8")

            try:
                result = subprocess.run(
                    [
                        self.compiler,
                        f"-std={self.cpp_standard}",
                        "-c",  # Compile only, don't link
                        "-Wall",
                        "-Wextra",
                        str(source_path),
                        "-o",
                        str(Path(tmpdir) / "output.o"),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                )

                if result.returncode == 0:
                    return VerificationResult(compile_success=True)

                return VerificationResult(
                    compile_success=False,
                    compile_error=result.stderr or result.stdout,
                )

            except subprocess.TimeoutExpired:
                return VerificationResult(
                    compile_success=False,
                    compile_error="Compilation timed out",
                )
            except FileNotFoundError:
                return VerificationResult(
                    compile_success=False,
                    compile_error=f"Compiler not found: {self.compiler}",
                )
            except Exception as e:
                return VerificationResult(
                    compile_success=False,
                    compile_error=str(e),
                )

    def compile_and_run_tests(
        self,
        source_code: str,
        test_code: str,
        source_filename: str = "source.cpp",
        test_filename: str = "test_source.cpp",
    ) -> VerificationResult:
        """Compile source and tests, then run tests.

        Args:
            source_code: Main C++ source code.
            test_code: Google Test test code.
            source_filename: Source filename.
            test_filename: Test filename.

        Returns:
            VerificationResult with compilation and test status.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Write source (as header for simplicity)
            header_path = tmpdir_path / source_filename.replace(".cpp", ".h")
            header_path.write_text(source_code, encoding="utf-8")

            # Write test file
            test_path = tmpdir_path / test_filename
            test_code_with_include = f'#include "{header_path.name}"\n{test_code}'
            test_path.write_text(test_code_with_include, encoding="utf-8")

            # Compile
            executable = tmpdir_path / "test_runner"
            try:
                compile_result = subprocess.run(
                    [
                        self.compiler,
                        f"-std={self.cpp_standard}",
                        str(test_path),
                        "-lgtest",
                        "-lgtest_main",
                        "-pthread",
                        "-o",
                        str(executable),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                    cwd=tmpdir,
                )

                if compile_result.returncode != 0:
                    return VerificationResult(
                        compile_success=False,
                        compile_error=compile_result.stderr or compile_result.stdout,
                    )

            except subprocess.TimeoutExpired:
                return VerificationResult(
                    compile_success=False,
                    compile_error="Test compilation timed out",
                )
            except Exception as e:
                return VerificationResult(
                    compile_success=False,
                    compile_error=str(e),
                )

            # Run tests
            try:
                test_result = subprocess.run(
                    [str(executable)],
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                    cwd=tmpdir,
                )

                return VerificationResult(
                    compile_success=True,
                    test_success=test_result.returncode == 0,
                    test_output=test_result.stdout,
                    test_error=test_result.stderr if test_result.returncode != 0 else None,
                )

            except subprocess.TimeoutExpired:
                return VerificationResult(
                    compile_success=True,
                    test_success=False,
                    test_error="Test execution timed out",
                )
            except Exception as e:
                return VerificationResult(
                    compile_success=True,
                    test_success=False,
                    test_error=str(e),
                )
