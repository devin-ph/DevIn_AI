"""
System tools for DevIn.

Provides File System and Terminal execution tools to give DevIn hands.
Incorporates safety truncation for terminal outputs.
"""

import os
import re
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
        result = f"Success: Wrote {len(content)} characters to {filepath}."
        if filepath.endswith(".py"):
            check_res = self_check_file.invoke({"filepath": filepath})
            if "FAIL" in check_res:
                result += f"\nNote: self_check_file detected an issue:\n{check_res}"
        return result
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


@tool
def grep_search(query: str, dirpath: str = ".") -> str:
    """
    Search file contents by regex or exact text across a directory.
    Use this to find where functions are defined or variables are used.
    
    Args:
        query: The regex or string pattern to search for.
        dirpath: The directory to search in (defaults to current directory).
    """
    path = Path(dirpath)
    if not path.exists():
        return f"Error: Directory {dirpath} does not exist."
        
    try:
        # Use python's re to search efficiently without depending on system grep
        pattern = re.compile(query)
        results = []
        match_count = 0
        max_matches = 50
        
        for root, dirs, files in os.walk(path):
            # Skip common hidden/binary directories
            dirs[:] = [d for d in dirs if d not in ('.git', '__pycache__', '.venv', 'node_modules', 'dist', 'build')]
            
            for file in files:
                filepath = Path(root) / file
                # Skip known binary or large generated files
                if file.endswith(('.pyc', '.exe', '.dll', '.so', '.png', '.jpg', '.pdf', '.zip')):
                    continue
                    
                try:
                    content = filepath.read_text(encoding='utf-8')
                    for i, line in enumerate(content.splitlines(), 1):
                        if pattern.search(line):
                            try:
                                rel_path = filepath.absolute().relative_to(Path.cwd().absolute())
                            except ValueError:
                                rel_path = filepath
                            results.append(f"{rel_path}:{i}: {line.strip()}")
                            match_count += 1
                            if match_count >= max_matches:
                                results.append(f"\n... [TRUNCATED at {max_matches} matches] ...")
                                return "\n".join(results)
                except (UnicodeDecodeError, PermissionError):
                    continue
                    
        return "\n".join(results) if results else f"No matches found for '{query}'."
    except Exception as e:
        return f"Error during grep search: {e}"


@tool
def file_search(query: str, dirpath: str = ".") -> str:
    """
    Find files whose name matches a glob pattern.
    Use this to quickly locate files in the project.
    
    Args:
        query: The glob pattern to search for (e.g., '*.py', '**/tests/*').
        dirpath: The directory to search in (defaults to current directory).
    """
    path = Path(dirpath)
    if not path.exists():
        return f"Error: Directory {dirpath} does not exist."
        
    try:
        results = list(path.rglob(query))
        
        # Filter out hidden/venv stuff if possible
        filtered_results = []
        for r in results:
            parts = r.parts
            if any(p in ('.git', '__pycache__', '.venv', 'node_modules', 'dist', 'build') for p in parts):
                continue
            try:
                rel = r.absolute().relative_to(Path.cwd().absolute())
            except ValueError:
                rel = r
            filtered_results.append(str(rel))
            
        if not filtered_results:
            return f"No files matching '{query}' found."
            
        if len(filtered_results) > 100:
            return "\n".join(filtered_results[:100]) + f"\n\n... [TRUNCATED {len(filtered_results) - 100} more files]"
            
        return "\n".join(filtered_results)
    except Exception as e:
        return f"Error during file search: {e}"


@tool
def edit_file_replace(filepath: str, old_str: str, new_str: str) -> str:
    """
    Replace a specific string block in a file with new content.
    This is highly preferred over write_file to avoid overwriting large files.
    
    Args:
        filepath: Path to the file.
        old_str: The exact literal text to replace.
        new_str: The exact literal text to replace it with.
    """
    import re
    path = Path(filepath)
    if not path.exists():
        return f"Error: File {filepath} does not exist."
    if path.is_dir():
        return f"Error: {filepath} is a directory, not a file."
        
    try:
        content = path.read_text(encoding="utf-8")
        
        occurrences = content.count(old_str)
        if occurrences == 1:
            new_content = content.replace(old_str, new_str)
            path.write_text(new_content, encoding="utf-8")
            result = f"Success: Replaced 1 occurrence in {filepath}."
            if filepath.endswith(".py"):
                check_res = self_check_file.invoke({"filepath": filepath})
                if "FAIL" in check_res:
                    result += f"\nNote: self_check_file detected an issue:\n{check_res}"
            return result
            
        elif occurrences > 1:
            return f"Error: old_str found {occurrences} times in the file. Please provide a more specific old_str (include more surrounding lines)."
            
        print("Falling back to fuzzy match...")
        # Fallback to fuzzy matching
        tokens = old_str.split()
        if not tokens:
            return "Error: old_str is empty or just whitespace."
            
        escaped_tokens = [re.escape(t) for t in tokens]
        pattern = r'\s+'.join(escaped_tokens)
        matches = list(re.finditer(pattern, content))
        
        if len(matches) == 0:
            return "Error: old_str not found in the file. Ensure you copied the exact text, or the fuzzy matcher failed."
        elif len(matches) > 1:
            return f"Error: Fuzzy match found {len(matches)} times in the file. Please provide a more specific old_str."
            
        match_str = matches[0].group(0)
        new_content = content.replace(match_str, new_str)
        path.write_text(new_content, encoding="utf-8")
        
        result = f"Success: Replaced 1 occurrence using fuzzy match in {filepath}."
        if filepath.endswith(".py"):
            check_res = self_check_file.invoke({"filepath": filepath})
            if "FAIL" in check_res:
                result += f"\nNote: self_check_file detected an issue:\n{check_res}"
        return result
        
    except Exception as e:
        return f"Error editing file: {e}"

@tool
def analyze_python_ast(filepath: str) -> str:
    """
    Extract classes, methods, functions, and their docstrings from a Python file using AST.
    This provides a lightweight overview of a file without reading its entire contents.
    
    Args:
        filepath: Path to the Python file to analyze.
    """
    import ast
    from pathlib import Path
    
    path = Path(filepath)
    if not path.exists():
        return f"Error: File {filepath} does not exist."
    if not path.is_file():
        return f"Error: {filepath} is not a file."
    if path.suffix != '.py':
        return f"Error: {filepath} is not a Python file."

    try:
        content = path.read_text(encoding="utf-8")
        tree = ast.parse(content)
        
        results = []
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                docstring = ast.get_docstring(node)
                doc_str = f"  \"\"\"{docstring}\"\"\"\n" if docstring else ""
                results.append(f"class {node.name}:\n{doc_str}")
                for item in node.body:
                    if isinstance(item, ast.FunctionDef):
                        item_doc = ast.get_docstring(item)
                        item_doc_str = f"    \"\"\"{item_doc}\"\"\"\n" if item_doc else ""
                        results.append(f"  def {item.name}(...):\n{item_doc_str}")
            elif isinstance(node, ast.FunctionDef):
                docstring = ast.get_docstring(node)
                doc_str = f"  \"\"\"{docstring}\"\"\"\n" if docstring else ""
                results.append(f"def {node.name}(...):\n{doc_str}")
                
        if not results:
            return f"No classes or functions found in {filepath}."
        return "\n".join(results)
    except SyntaxError as e:
        return f"Syntax Error parsing {filepath}: {e}"
    except Exception as e:
        return f"Error analyzing AST for {filepath}: {e}"


@tool
def search_code_bm25(query: str, dirpath: str = ".") -> str:
    """
    Search codebase using Okapi BM25 algorithm (pure Python).
    Highly token-efficient way to find relevant files based on keyword frequency.
    
    Args:
        query: Space-separated keywords to search for.
        dirpath: Directory to search in (defaults to current directory).
    """
    import math
    from collections import Counter
    import os
    import re
    from pathlib import Path
    
    path = Path(dirpath)
    if not path.exists() or not path.is_dir():
        return f"Error: Directory {dirpath} does not exist."
        
    try:
        # 1. Tokenize query
        query_terms = [t.lower() for t in re.findall(r'\w+', query)]
        if not query_terms:
            return "Error: Query must contain alphanumeric terms."
            
        # 2. Build corpus index
        corpus = {}
        doc_lengths = {}
        df = Counter()  # Document frequency
        total_docs = 0
        total_length = 0
        
        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if d not in ('.git', '__pycache__', '.venv', 'node_modules', 'dist', 'build', '.pytest_cache')]
            for file in files:
                if not file.endswith(('.py', '.md', '.txt', '.json', '.yaml', '.yml', '.ts', '.js', '.html', '.css', '.c', '.cpp', '.h', '.cs', '.java', '.go', '.rs')):
                    continue
                filepath = Path(root) / file
                try:
                    content = filepath.read_text(encoding='utf-8')
                    try:
                        rel_path = filepath.absolute().relative_to(Path.cwd().absolute())
                    except ValueError:
                        rel_path = filepath
                    terms = [t.lower() for t in re.findall(r'\w+', content)]
                    if terms:
                        doc_len = len(terms)
                        corpus[str(rel_path)] = Counter(terms)
                        doc_lengths[str(rel_path)] = doc_len
                        total_length += doc_len
                        total_docs += 1
                        for term in set(terms):
                            df[term] += 1
                except (UnicodeDecodeError, PermissionError):
                    continue
                    
        if total_docs == 0:
            return "No text documents found in directory."
            
        avgdl = total_length / total_docs
        k1 = 1.5
        b = 0.75
        
        # 3. Score documents
        scores = {}
        for doc_id, tf_dict in corpus.items():
            score = 0
            doc_len = doc_lengths[doc_id]
            for term in query_terms:
                if term not in tf_dict:
                    continue
                tf = tf_dict[term]
                n_q = df.get(term, 0)
                # IDF
                idf = math.log(((total_docs - n_q + 0.5) / (n_q + 0.5)) + 1.0)
                # TF normalization
                tf_norm = (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * (doc_len / avgdl)))
                score += idf * tf_norm
            if score > 0:
                scores[doc_id] = score
                
        # 4. Sort and return top results
        sorted_docs = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        if not sorted_docs:
            return f"No results found for query '{query}'."
            
        res = [f"Top results for '{query}':"]
        for doc_id, score in sorted_docs[:10]:
            res.append(f"- {doc_id} (Score: {score:.2f})")
            
        return "\n".join(res)
    except Exception as e:
        return f"Error during BM25 search: {e}"


@tool
def read_function_only(filepath: str, function_name: str) -> str:
    """
    Extract exact source code of a specific function or class from a Python file.
    Saves thousands of tokens compared to reading the whole file.
    
    Args:
        filepath: Path to the Python file.
        function_name: Name of the function or class to extract.
    """
    import ast
    from pathlib import Path
    
    path = Path(filepath)
    if not path.exists():
        return f"Error: File {filepath} does not exist."
    if path.suffix != '.py':
        return f"Error: {filepath} is not a Python file."

    try:
        content = path.read_text(encoding="utf-8")
        tree = ast.parse(content)
        lines = content.splitlines()
        
        class FuncFinder(ast.NodeVisitor):
            def __init__(self, target):
                self.target = target
                self.found_node = None
                
            def visit_FunctionDef(self, node):
                if node.name == self.target:
                    self.found_node = node
                self.generic_visit(node)
                
            def visit_AsyncFunctionDef(self, node):
                if node.name == self.target:
                    self.found_node = node
                self.generic_visit(node)
                
            def visit_ClassDef(self, node):
                if node.name == self.target:
                    self.found_node = node
                self.generic_visit(node)
                
        finder = FuncFinder(function_name)
        finder.visit(tree)
        
        if not finder.found_node:
            return f"Error: Function/Class '{function_name}' not found in {filepath}."
            
        node = finder.found_node
        
        # ast objects in python 3.8+ have end_lineno
        if hasattr(node, "end_lineno") and node.end_lineno is not None:
            start = node.lineno - 1
            # Add decorators
            if hasattr(node, "decorator_list") and node.decorator_list:
                start = node.decorator_list[0].lineno - 1
            end = node.end_lineno
            return "\n".join(lines[start:end])
        else:
            return f"Error: Unable to determine bounds of '{function_name}'."
            
    except SyntaxError as e:
        return f"Syntax Error parsing {filepath}: {e}"
    except Exception as e:
        return f"Error extracting function from {filepath}: {e}"

@tool
def git_diff(filepath: str = "") -> str:
    """
    Show git diff for a specific file or entire working directory.
    Use before editing to understand current state.
    
    Args:
        filepath: Specific file to diff, or empty string for full diff.
    """
    import subprocess
    from pathlib import Path
    
    cmd = ["git", "diff", "HEAD"]
    if filepath:
        cmd.append(filepath)
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            # Not a git repo or no commits yet
            return f"Git diff unavailable: {result.stderr.strip()}"
        output = result.stdout.strip()
        if not output:
            return "No changes detected (working tree clean)."
        # Truncate very large diffs
        lines = output.splitlines()
        if len(lines) > 100:
            output = "\n".join(lines[:100]) + f"\n... [{len(lines)-100} more lines]"
        return output
    except FileNotFoundError:
        return "Git not available in this environment."
    except Exception as e:
        return f"Error running git diff: {e}"


@tool
def git_status() -> str:
    """Show current git status — which files are modified, staged, or untracked."""
    import subprocess
    try:
        result = subprocess.run(["git", "status", "--short"], capture_output=True, text=True, timeout=10)
        return result.stdout.strip() or "Working tree clean."
    except Exception as e:
        return f"Error: {e}"


@tool
def self_check_file(filepath: str) -> str:
    """
    Instantly validate a Python file after writing.
    Runs py_compile for syntax + basic import check.
    Returns PASS or FAIL with exact error location.
    
    Args:
        filepath: Path to the Python file to check.
    """
    import sys
    import subprocess
    from pathlib import Path
    
    path = Path(filepath)
    if not path.exists():
        return f"FAIL — File {filepath} does not exist."
    if path.suffix != ".py":
        return "SKIP — Not a Python file, no syntax check needed."
    
    # Step 1: Syntax check
    result = subprocess.run(
        [sys.executable, "-m", "py_compile", filepath],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        return f"FAIL — Syntax error:\n{result.stderr.strip()}"
    
    # Step 2: flake8 if available (style + unused imports)
    flake_result = subprocess.run(
        [sys.executable, "-m", "flake8", "--max-line-length=100", "--select=E9,F8", filepath],
        capture_output=True, text=True
    )
    if flake_result.returncode != 0 and flake_result.stdout.strip():
        return f"PASS (syntax) but WARN — style issues:\n{flake_result.stdout.strip()[:300]}"
    
    return f"PASS — {filepath} is syntactically valid."
