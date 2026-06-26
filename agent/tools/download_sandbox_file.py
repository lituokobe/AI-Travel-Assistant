"""
Sandbox File Download Tool

Downloads a specified file from the sandbox to the local EXAMPLE_DIR/download/ directory.
"""
from __future__ import annotations
from pathlib import Path
from langchain_core.tools import tool


def create_download_tool(sandbox_backend, download_dir: Path):
    """
    Factory function to create the download_sandbox_file tool.

    Args:
        sandbox_backend: OpenSandboxBackend instance used to read files from the sandbox.
        download_dir: Local target directory for downloads (e.g., EXAMPLE_DIR/download/).

    Returns:
        The download_sandbox_file tool function.
    """
    # Ensure the local directory exists
    download_dir.mkdir(parents=True, exist_ok=True)

    @tool
    def download_sandbox_file(sandbox_path: str, local_filename: str = "") -> str:
        """
        Downloads a specified file from the sandbox to the local download/ directory.

        Use cases:
        - Download travel plans (/trave_plan_*.md)
        - Download any other files from the sandbox to the local machine

        Args:
            sandbox_path: Absolute file path in the sandbox (e.g., "/trave_plan_20260513.md")
            local_filename: Filename to save locally (optional; if empty, uses the original filename from the sandbox)

        Returns:
            Download confirmation message, including the local file path.
        """
        # 1. Validate path
        if not sandbox_path or not sandbox_path.startswith("/"):
            return f"Error: sandbox_path must be an absolute path (starting with /), received: {sandbox_path}"

        # 2. Download file from sandbox
        try:
            results = sandbox_backend.download_files([sandbox_path])
        except Exception as e:
            return f"Error: Failed to read file from sandbox: {e}"

        if not results:
            return f"Error: Download returned empty results"

        dl = results[0]
        if dl.error:
            return f"Error: File does not exist or cannot be read ({dl.error}), path: {sandbox_path}"

        content = dl.content
        if content is None:
            return f"Error: File content is empty, path: {sandbox_path}"

        # 3. Determine local filename
        if not local_filename:
            local_filename = Path(sandbox_path).name
        # Security check: prevent path traversal
        local_filename = Path(local_filename).name

        local_path = download_dir / local_filename

        # 4. Write to local file
        try:
            if isinstance(content, str):
                content_bytes = content.encode("utf-8")
            elif isinstance(content, bytes):
                content_bytes = content
            else:
                content_bytes = str(content).encode("utf-8")

            local_path.write_bytes(content_bytes)
        except Exception as e:
            return f"Error: Failed to write local file: {e}"

        # 5. Return result
        file_size = len(content_bytes)
        size_str = (
            f"{file_size} B" if file_size < 1024
            else f"{file_size / 1024:.1f} KB" if file_size < 1024 * 1024
            else f"{file_size / (1024 * 1024):.1f} MB"
        )

        return (
            f"✅ File downloaded to local\n"
            f"Sandbox path: {sandbox_path}\n"
            f"Local path: {local_path}\n"
            f"File size: {size_str}"
        )

    download_sandbox_file.name = "download_sandbox_file"
    return download_sandbox_file
