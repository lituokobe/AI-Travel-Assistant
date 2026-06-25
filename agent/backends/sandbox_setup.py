"""
Initialization and file seeding module for the OpenSandbox sandbox.

Responsibilities:

1. Retrieve or create an OpenSandbox sandbox and wrap it as an `OpenSandboxBackend`.
2. Seed skill files (skill package `SKILL.md`).

Notes:
- `AGENTS.md` has been migrated to `StoreBackend` (globally shared) and no longer passes through the sandbox.
- Long-term user memories (`/memories/`) are routed by `CompositeBackend` to `StoreBackend` for persistence.
- Runtime incremental skill synchronization is handled by `SkillsSyncMiddleware`.
"""
from datetime import timedelta
from pathlib import Path
from opensandbox import SandboxSync
from agent.backends.custom_opensandbox import OpenSandboxBackend
from agent.config import SANDBOX_SKILLS_ROOT, LOCAL_SKILLS_DIR
from agent.logger import logger


def setup_sandbox(config, sandbox_id=None, image=None) -> OpenSandboxBackend:
    """
    Retrieve or create a sandbox and seed the required base files.

    Args:
        config: ConnectionConfigSync configuration.
        sandbox_id: Optional ID of an existing sandbox to connect to.
        image: Optional image used when creating a new sandbox.

    Returns:
        An OpenSandboxBackend instance.
    """
    if sandbox_id:
        logger.info(f"Connecting to existing sandbox: {sandbox_id}")
        try:
            sandbox = SandboxSync.connect(sandbox_id, connection_config=config)
            logger.info(f"Successful connection to sandbox: {sandbox_id}")
        except Exception as e:
            logger.warning(f"Failed to connect to sandbox: {e}, new sandbox will be created")
            sandbox_id = None

    if not sandbox_id:
        if not image:
            image = "sandbox-registry.cn-zhangjiakou.cr.aliyuncs.com/opensandbox/code-interpreter:v1.0.2"

        logger.info(f"Creating new sandbox with image: {image}")
        sandbox = SandboxSync.create(
            image,
            entrypoint=["/opt/opensandbox/code-interpreter.sh"],
            env={"PYTHON_VERSION": "3.11"},
            resource={"cpu": "2", "memory": "4Gi"},
            timeout=timedelta(minutes=30),
            connection_config=config,
            # network_policy=NetworkPolicy(  # 沙箱网络路由限制策略
            #     defaultAction="deny",
            #     egress=[
            #         NetworkRule(action="allow", target="pypi.org"),
            #         NetworkRule(action="allow", target="*.github.com"),
            #     ]
            # )
        )

    backend = OpenSandboxBackend(sandbox=sandbox)
    logger.info(f"Sandbox is ready,ID: {sandbox.id}")

    # seed base files（AGENTS.md、Skills）
    _seed_files(backend)

    return backend


def _seed_files(backend: OpenSandboxBackend) -> None:
    """
    Upload local files to sandbox

    AGENTS.md is migrated to StoreBackend（globally shared, no need sandbox）
    Only upload files that are not in sandbox, avoiding replacing updated content
    """
    file_mapping: list[tuple[Path, str]] = []

    # 遍历 skills 目录，添加所有技能文件
    skills_base = Path(LOCAL_SKILLS_DIR)
    if skills_base.exists():
        for skill_dir in skills_base.iterdir():
            if not skill_dir.is_dir():
                continue
            for local_file in skill_dir.rglob("*"):
                if local_file.is_file():
                    rel = local_file.relative_to(skills_base).as_posix()
                    sandbox_path = f"{SANDBOX_SKILLS_ROOT}/{rel}"
                    file_mapping.append((local_file, sandbox_path))

    # 收集需要上传的文件
    to_upload: list[tuple[str, bytes]] = []
    for local_path, sandbox_path in file_mapping:
        if not local_path.exists():
            continue
        local_content = local_path.read_bytes()
        # 用 test -f 检测文件是否存在（无 ERROR 日志），避免 download_files 对 404 打 ERROR
        check = backend.execute(f"test -f {sandbox_path}")
        if check.exit_code == 0:
            try:
                results = backend.download_files([sandbox_path])
                if results and results[0].content and not results[0].error:
                    remote_content = results[0].content
                    if isinstance(remote_content, str):
                        remote_content = remote_content.encode("utf-8")
                    if remote_content == local_content:
                        continue
            except Exception:
                pass
        to_upload.append((sandbox_path, local_content))

    if to_upload:
        print(f"[INFO] 正在上传 {len(to_upload)} 个基础文件...")
        backend.upload_files(to_upload)
        print("[INFO] 基础文件上传完成。")
    else:
        print("[INFO] 所有基础文件已就绪，无需上传。")