"""
System tools for DevIn.

Provides File System and Terminal execution tools to give DevIn hands.
Incorporates safety truncation for terminal outputs.
"""

import os
import subprocess
from pathlib import Path

from langchain_core.tools import tool

from devin.settings import settings


@tool
def read_file(filepath: str) -> str:
    """
    Read the contents of a local file.
    Use this to explore the codebase and read configurations.
    
    Args:
        filepath: Absolute or relative path to the file.
    """
    path = Path(filepath)
    if not path.exists():
        return f"Error: File {filepath} does not exist."
    if path.is_dir():
        return f"Error: {filepath} is a directory, not a file."
        
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return f"Error: {filepath} appears to be a binary file."
    except Exception as e:
        return f"Error reading file: {e}"


@tool
def write_file(filepath: str, content: str) -> str:
    """
    Create or overwrite a local file with new content.
    WARNING: This completely overwrites the file if it exists.
    
    Args:
        filepath: Path to the file to create/overwrite.
        content: The exact content to write into the file.
    """
    path = Path(filepath)
    try:
        # Ensure parents exist
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return f"Success: Wrote {len(content)} characters to {filepath}."
    except Exception as e:
        return f"Error writing file: {e}"


@tool
def list_directory(dirpath: str) -> str:
    """
    List contents of a directory.
    
    Args:
        dirpath: Path to the directory.
    """
    path = Path(dirpath)
    if not path.exists():
        return f"Error: Directory {dirpath} does not exist."
    if not path.is_dir():
        return f"Error: {dirpath} is not a directory."
        
    try:
        entries = []
        for entry in path.iterdir():
            icon = "📁" if entry.is_dir() else "📄"
            entries.append(f"{icon} {entry.name}")
        return "\n".join(entries) if entries else "Directory is empty."
    except Exception as e:
        return f"Error viewing directory: {e}"


@tool
def execute_command(command: str) -> str:
    """
    Execute a shell/terminal command (e.g., python tests.py, git status).
    Outputs over 50 lines are truncated to prevent context overflow.
    
    Args:
        command: The terminal command to execute.
    """
    try:
        # Note: In a production environment, we would use a PTY or wait for confirmation here.
        result = subprocess.run(
            command, shell=True, text=True, capture_output=True, timeout=60
        )
        
        output = result.stdout + "\n" + result.stderr
        output = output.strip()
        
        if not output:
            return f"Command executed successfully (Exit code {result.returncode}), but produced no output."
        
        # --- Context Overflow Truncation ---
        lines = output.splitlines()
        max_lines = 50
        if len(lines) > max_lines:
            truncated_output = "\n".join(lines[:15])
            truncated_output += f"\n\n... [TRUNCATED {len(lines) - max_lines} LINES] ...\n\n"
            truncated_output += "\n".join(lines[-35:])
            return f"Exit code: {result.returncode}\nOutput (Truncated):\n{truncated_output}"
        
        return f"Exit code: {result.returncode}\nOutput:\n{output}"
    except subprocess.TimeoutExpired:
        return "Error: Command timed out after 60 seconds."
    except Exception as e:
        return f"Error executing command: {e}"
