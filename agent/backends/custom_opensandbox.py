"""OpenSandbox sandbox backend implementation, conforming to the SandboxBackendProtocol."""
from __future__ import annotations
from collections.abc import Callable
from typing import cast

from opensandbox import SandboxSync
from opensandbox.models import WriteEntry

from deepagents.backends.protocol import (
    ExecuteResponse,
    FileDownloadResponse,
    FileUploadResponse,
)
from deepagents.backends.sandbox import BaseSandbox

from agent.logger import logger

SyncPollingInterval = float | Callable[[float], float]
PollingStrategy = Callable[[float], float]


class OpenSandboxBackend(BaseSandbox):
    """OpenSandbox-based sandbox backend.

    Inherits file operation methods from BaseSandbox; only implements execute, download_files, and upload_files.
    """

    def __init__(
            self,
            *,
            sandbox: SandboxSync,
            timeout: int = 60 * 60,
            sync_polling_interval: SyncPollingInterval = 0.1,
    ) -> None:
        """Create a backend instance wrapping an existing OpenSandbox sandbox.

        Args:
            sandbox: The existing OpenSandbox sandbox instance to wrap.
            timeout: Default command timeout in seconds when `execute()` is called
                without an explicit `timeout`.
            sync_polling_interval: Interval in seconds for polling OpenSandbox command
                completion on the synchronous execution path; may also be a callable
                that receives elapsed seconds and returns the next polling delay.
        """
        logger.info(f"正在初始化 OpenSandbox，沙盒 ID: {sandbox.id}")
        self._sandbox = sandbox
        # sandbox.kill()  # Manually shut down the sandbox
        self._default_timeout = timeout

        # Handle polling strategy
        if callable(sync_polling_interval):
            polling_strategy = cast("PollingStrategy", sync_polling_interval)
        else:
            def polling_strategy(_elapsed: float) -> float:
                return sync_polling_interval

        self._sync_polling_interval = polling_strategy
        logger.debug(f"OpenSandbox 初始化完成，默认超时时间={timeout}秒")

    @property
    def id(self) -> str:
        """Return the OpenSandbox sandbox ID."""
        sandbox_id = self._sandbox.id
        logger.debug(f"获取沙盒 ID: {sandbox_id}")
        return sandbox_id

    # Non-interactive shells in the sandbox do not load /etc/profile; inject env vars manually
    SANDBOX_PATH = (
        "/opt/python/versions/cpython-3.11.14-linux-x86_64-gnu/bin:"
        "/opt/go/1.25.5/bin:"
        "/opt/node/v22.2.0/bin:"
        "/usr/lib/jvm/java-21-openjdk-amd64/bin:"
        "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
    )

    def execute(
            self,
            command: str,
            *,
            timeout: int | None = None,
    ) -> ExecuteResponse:
        """Execute a shell command inside the sandbox.

        Args:
            command: Shell command string to execute.
            timeout: Maximum time in seconds to wait for command completion.
                If None, uses the backend default timeout.
        """
        effective_timeout = timeout if timeout is not None else self._default_timeout
        # Non-interactive shell does not source /etc/profile; inject PATH so pip/python are available
        wrapped = f'export PATH="{self.SANDBOX_PATH}:$PATH" && {command}'
        logger.debug(f"准备执行命令：{command[:100]}...（超时时间={effective_timeout}秒）")
        return self._execute_command(wrapped, timeout=effective_timeout)

    def _execute_command(
            self,
            command: str,
            *,
            timeout: int,
    ) -> ExecuteResponse:
        """Execute a command via the OpenSandbox API."""
        try:
            logger.debug(f"通过 OpenSandbox API 执行命令：{command}")
            result = self._sandbox.commands.run(command)
            logger.debug(f"命令执行完成，退出码：{result.exit_code}")

            # Extract stdout and stderr
            stdout = ""
            stderr = ""

            if result.logs.stdout:
                stdout = "\n".join([log.text for log in result.logs.stdout])
                logger.debug(f"命令标准输出长度：{len(stdout)} 字符")

            if result.logs.stderr:
                stderr = "\n".join([log.text for log in result.logs.stderr])
                logger.debug(f"命令标准错误长度：{len(stderr)} 字符")

            # Merge output
            output = stdout
            if stderr and stderr.strip():
                output += f"\n<stderr>{stderr.strip()}</stderr>"

            logger.info(f"命令执行成功，退出码：{result.exit_code or 0}")
            return ExecuteResponse(
                output=output,
                exit_code=result.exit_code or 0,
                truncated=False,
            )

        except Exception as e:
            error_msg = str(e)
            logger.error(f"执行命令时发生错误：{error_msg}", exc_info=True)

            if "timeout" in error_msg.lower():
                logger.warning(f"命令在 {timeout} 秒后超时")
                return ExecuteResponse(
                    output=f"命令在 {timeout} 秒后超时",
                    exit_code=124,
                    truncated=False,
                )

            return ExecuteResponse(
                output=f"执行命令时出错：{error_msg}",
                exit_code=1,
                truncated=False,
            )

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        """Download specified files from the sandbox.

        Args:
            paths: List of absolute file paths in the sandbox.

        Returns:
            Responses in the same order as paths, containing file content or error info.
        """
        responses: list[FileDownloadResponse] = []

        for path in paths:
            if not path.startswith("/"):
                responses.append(
                    FileDownloadResponse(path=path, content=None, error="invalid_path")
                )
                continue
            try:
                content = self._sandbox.files.read_file(path)
                # Normalize to bytes
                content_bytes = content.encode("utf-8") if isinstance(content, str) else content
                responses.append(
                    FileDownloadResponse(path=path, content=content_bytes, error=None)
                )
            except Exception:
                responses.append(
                    FileDownloadResponse(path=path, content=None, error="file_not_found")
                )

        return responses

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        """Upload files to the sandbox.

        Args:
            files: List of (absolute path, file content bytes) tuples.

        Returns:
            Responses in the same order as files, with error info (None on success).
        """
        responses: list[FileUploadResponse] = []
        upload_entries: list[WriteEntry] = []

        for path, content in files:
            if not path.startswith("/"):
                responses.append(FileUploadResponse(path=path, error="invalid_path"))
                continue
            try:
                # Convert bytes to string for writing
                if isinstance(content, bytes):
                    try:
                        content_str = content.decode("utf-8")
                    except UnicodeDecodeError:
                        content_str = content.decode("latin-1")
                else:
                    content_str = str(content)
                upload_entries.append(WriteEntry(path=path, data=content_str, mode=0o644))
                responses.append(FileUploadResponse(path=path, error=None))
            except Exception as e:
                responses.append(FileUploadResponse(path=path, error=str(e)))

        if upload_entries:
            try:
                self._sandbox.files.write_files(upload_entries)
            except Exception as e:
                # If the write fails, mark all successfully prepared but not yet uploaded entries as errors
                for resp in responses:
                    if resp.error is None:
                        resp.error = f"upload_failed: {e}"

        return responses