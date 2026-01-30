
import logging
import json
import subprocess
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

@dataclass
class ValidationResult:
    valid: bool
    error: Optional[str] = None

class ResultValidator:
    """
    Validates results from LLM execution:
    1. Syntax Check (Language specific)
    2. JSON Schema Check (Structured output)
    3. Diff Validation (Patch cleanliness)
    """

    def check_syntax(self, file_path: Path, language: str) -> ValidationResult:
        """
        Check if the file has valid syntax.
        """
        if not file_path.exists():
            return ValidationResult(False, f"File not found: {file_path}")

        try:
            if language.lower() == "python":
                # python -m py_compile <file>
                subprocess.run(
                    [shutil.which("python3") or "python", "-m", "py_compile", str(file_path)],
                    check=True,
                    capture_output=True,
                    text=True
                )
            elif language.lower() in ("cpp", "c++", ".cpp", ".hpp"):
                # gcc -fsyntax-only <file>
                subprocess.run(
                    ["g++", "-fsyntax-only", str(file_path)],
                    check=True,
                    capture_output=True,
                    text=True
                )
            return ValidationResult(True)
            
        except subprocess.CalledProcessError as e:
            return ValidationResult(False, f"Syntax Error: {e.stderr}")
        except Exception as e:
            return ValidationResult(False, f"Validation Failed: {e}")

    def validate_json(self, content: str, schema: Dict[str, Any] = None) -> ValidationResult:
        """
        Validate content is valid JSON and optionally matches a schema.
        Note: Requires 'jsonschema' package for schema validation.
        """
        try:
            data = json.loads(content)
            
            if schema:
                try:
                    import jsonschema
                    jsonschema.validate(instance=data, schema=schema)
                except ImportError:
                    logger.warning("jsonschema not installed, skipping schema validation")
                except jsonschema.ValidationError as e:
                     return ValidationResult(False, f"Schema Validation Error: {e.message}")

            return ValidationResult(True)
            
        except json.JSONDecodeError as e:
            return ValidationResult(False, f"Invalid JSON: {e}")
            
    def validate_diff(self, original_content: str, patch: str) -> ValidationResult:
        """
        Check if a patch can be applied cleanly.
        (Placeholder for unified diff logic)
        """
        # TODO: Implement patch application simulation
        return ValidationResult(True)
