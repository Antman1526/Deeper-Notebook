"""v0.8.67r — Native tool for executing code using the opencode CLI.

Wraps the opencode CLI tool in a LangChain StructuredTool for the chat tool loop.
This implements the secure local/cloud code-computer execution feature.
"""

from __future__ import annotations

import asyncio
import os
import shutil
from typing import Optional

from langchain_core.tools import StructuredTool
from loguru import logger
from pydantic import BaseModel, Field

OPENCODE_TOOL_NAME = "opencode_run"


def opencode_bin_path() -> str:
    """Find the path to the opencode binary."""
    # Check environment variable first
    env_path = os.environ.get("OPENCODE_BIN")
    if env_path:
        return env_path

    # Try to find in PATH
    which_path = shutil.which("opencode")
    if which_path:
        return which_path

    # Default fallback locations
    defaults = [
        "/opt/homebrew/bin/opencode",
        "/usr/local/bin/opencode",
        os.path.expanduser("~/.local/bin/opencode"),
    ]
    for path in defaults:
        if os.path.exists(path) and os.access(path, os.X_OK):
            return path

    return "opencode"  # Fallback to bare command name


def opencode_enabled() -> bool:
    """True if opencode is installed and accessible on the host."""
    bin_path = opencode_bin_path()
    if bin_path == "opencode":
        return shutil.which("opencode") is not None
    return os.path.exists(bin_path) and os.access(bin_path, os.X_OK)


async def run_opencode(
    prompt: str,
    project: Optional[str] = None,
    model: Optional[str] = None,
    continue_session: Optional[bool] = None,
) -> str:
    """Execute the opencode CLI tool with the given arguments."""
    bin_path = opencode_bin_path()
    args = [bin_path, "run", prompt]

    if model:
        args.extend(["--model", model])
    if continue_session:
        args.append("--continue")

    # Default to current directory if project path is not provided
    cwd = project or os.getcwd()

    logger.info(f"Running opencode command: {' '.join(args)} in {cwd}")

    try:
        # Run process asynchronously with a 5-minute timeout
        process = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env={**os.environ, "NO_COLOR": "1", "TERM": "dumb"},
        )

        stdout, stderr = await process.communicate()

        stdout_str = stdout.decode().strip()
        stderr_str = stderr.decode().strip()

        if process.returncode == 0:
            return stdout_str
        else:
            logger.warning(
                f"opencode failed with exit code {process.returncode}: {stderr_str}"
            )
            return f"Error: {stderr_str}\n{stdout_str}".strip()

    except Exception as e:
        logger.error(f"Failed to execute opencode: {e}")
        return f"Error executing opencode: {e}"


class OpenCodeRunInput(BaseModel):
    prompt: str = Field(
        ...,
        description="The prompt/instruction to send to OpenCode to run/execute code or perform a task.",
    )
    project: Optional[str] = Field(
        None,
        description="Absolute path to the project directory (defaults to current working directory).",
    )
    model: Optional[str] = Field(
        None,
        description="Model to use in provider/model format (e.g., 'openai/gpt-4o').",
    )
    continueSession: Optional[bool] = Field(
        None, description="Continue the last session instead of starting a new one."
    )


def build_opencode_tool(captures: list | None = None) -> StructuredTool:
    """Build the StructuredTool for the chat model to bind and invoke."""

    async def _invoke(
        prompt: str,
        project: Optional[str] = None,
        model: Optional[str] = None,
        continueSession: Optional[bool] = None,
    ) -> str:
        result = await run_opencode(
            prompt=prompt,
            project=project,
            model=model,
            continue_session=continueSession,
        )

        if captures is not None:
            captures.append(
                {
                    "index": len(captures) + 1,
                    "name": OPENCODE_TOOL_NAME,
                    "args": {
                        "prompt": prompt,
                        "project": project,
                        "model": model,
                        "continueSession": continueSession,
                    },
                    "text": result[:4000],
                    "blocks": [],
                }
            )
        return result

    return StructuredTool.from_function(
        coroutine=_invoke,
        name=OPENCODE_TOOL_NAME,
        description=(
            "Run OpenCode AI agent to execute code, run scripts, edit files, or perform terminal commands "
            "locally on the workspace. Returns the agent's stdout and response. Use this whenever the "
            "user asks to run code, write and test script outputs, or perform complex local terminal commands."
        ),
        args_schema=OpenCodeRunInput,
    )
