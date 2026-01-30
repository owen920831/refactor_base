"""Baseline verification module.

Generates and runs reproduction scripts (harnesses) to establish ground truth behavior.
"""
from __future__ import annotations

import logging
import subprocess
import time
from pathlib import Path
from typing import Any

from mvp_agent.llm_client import LLMClient

logger = logging.getLogger(__name__)


class BaselineVerifier:
    """Verifies baseline behavior of source code."""

    def __init__(self, llm_client: LLMClient, output_dir: Path) -> None:
        """Initialize the verifier.

        Args:
            llm_client: Client for LLM interactions.
            output_dir: Directory for generated harnesses.
        """
        self.llm_client = llm_client
        self.output_dir = output_dir

    def verify(self, source_path: Path) -> bool:
        """Run baseline verification.

        Args:
            source_path: Path to the source file.

        Returns:
            True if baseline verification passed (harness ran successfully).
        """
        logger.info("Starting baseline verification for %s", source_path)
        source_code = source_path.read_text(encoding="utf-8")

        # 1. Generate Harness
        harness_code, harness_ext, run_cmd = self._generate_harness(source_code, source_path)
        
        if not harness_code:
            logger.error("Failed to generate harness")
            return False

        # 2. Save Harness
        harness_file = self.output_dir / f"baseline_harness{harness_ext}"
        harness_file.write_text(harness_code, encoding="utf-8")
        logger.info("Saved baseline harness to %s", harness_file)

        # 3. Run Harness
        result = self._run_harness(harness_file, run_cmd)
        
        # 4. Save Result
        self._save_result(result)

        return result["success"]

    def _generate_harness(self, source_code: str, source_path: Path) -> tuple[str, str, str]:
        """Generate a reproduction script using LLM.

        Returns:
            Tuple of (harness_code, file_extension, run_command_template).
        """
        prompt = f"""
Analyze the following source code and create a standalone reproduction script (harness) 
in the SAME LANGUAGE that tests the main functionality and edge cases.
The script must:
1. Import or include the necessary parts from the source file (assume same directory).
2. Run inputs that cover critical paths.
3. Print 'Baseline: PASS' to stdout if all checks pass.
4. Exit with code 0 on success, non-zero on failure.
5. If the source file is a script, import it as a module if possible, or simulate its execution.
6. When importing the source file, use a unique module name (e.g. 'source_src') to avoid conflicts.
7. IMPORTANT: Use the FULL ABSOLUTE PATH provided below for loading the module. Do not use relative paths.
8. If the source code uses common globals (e.g. 'cache', 'List', 'Optional') without importing them, you MUST inject them into the module's namespace BEFORE executing it.
   Example injection:
   ```python
   import functools, typing
   module.__dict__["cache"] = functools.cache
   module.__dict__["List"] = typing.List
   spec.loader.exec_module(module)
   ```

Source File: {source_path}
Code:
```
{source_code[:4000]}
```

Return JSON format:
{{
  "code": "full harness code",
  "extension": ".py" (or .cpp, .js etc),
  "run_command": "command to run the script. IMPORTANT: Use '{{file}}' as placeholder for the filename. Example: 'python {{file}}' or 'g++ {{file}} -o runner && ./runner'."
}}
"""
        response = self.llm_client.generate_with_retry(prompt)
        if response.error:
            return "", "", ""

        # Simple manual parsing if JSON is wrapped in markdown
        content = response.content.strip()
        if content.startswith("```json"):
            content = content[7:-3]
        elif content.startswith("```"):
            content = content[3:-3]
        
        import json
        try:
            data = json.loads(content)
            return data["code"], data["extension"], data["run_command"]
        except Exception as e:
            logger.error("Failed to parse LLM response: %s", e)
            return "", "", ""

    def _run_harness(self, harness_file: Path, run_cmd_template: str) -> dict[str, Any]:
        """Execute the harness."""
        cmd = run_cmd_template.replace("{file}", str(harness_file))
        # Handle python specific: add current dir to pythonpath
        env = None
        if "python" in cmd:
            import os
            env = os.environ.copy()
            env["PYTHONPATH"] = str(harness_file.parent.parent) # Assuming structure output/intermediate/..
        
        logger.info("Running baseline command: %s", cmd)
        try:
            start_time = time.time()
            proc = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
                env=env
            )
            duration = time.time() - start_time
            
            success = proc.returncode == 0 and "Baseline: PASS" in proc.stdout
            
            if not success:
                logger.warning("Baseline output: %s", proc.stdout)
                logger.warning("Baseline error: %s", proc.stderr)
            
            return {
                "success": success,
                "command": cmd,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "return_code": proc.returncode,
                "duration": duration
            }
        except subprocess.TimeoutExpired:
             return {
                "success": False,
                "error": "Timeout"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def _save_result(self, result: dict[str, Any]) -> None:
        """Save verification result to JSON."""
        result_file = self.output_dir / "baseline_result.json"
        
        import json
        with open(result_file, "w") as f:
            json.dump(result, f, indent=2)
