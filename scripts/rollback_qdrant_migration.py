"""
Qdrant 迁移回滚脚本

功能：
1. 停止 Qdrant 服务（Docker）
2. 清理 Qdrant 数据
3. 恢复系统到迁移前状态

用法：
    python scripts/rollback_qdrant_migration.py
    python scripts/rollback_qdrant_migration.py --keep-data
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import subprocess
import sys
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
QDRANT_DATA_DIR = PROJECT_ROOT / "qdrant_storage"
DOCKER_COMPOSE_FILE = PROJECT_ROOT / "docker-compose.yml"


def check_docker_available() -> bool:
    try:
        subprocess.run(
            ["docker", "--version"],
            capture_output=True,
            check=True,
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def get_qdrant_container_name() -> str:
    return "math-ai-qdrant"


def stop_qdrant_container() -> bool:
    container_name = get_qdrant_container_name()
    logger.info(f"停止 Qdrant 容器: {container_name}")

    try:
        result = subprocess.run(
            ["docker", "ps", "-q", "-f", f"name={container_name}"],
            capture_output=True,
            text=True,
        )

        if not result.stdout.strip():
            logger.info("Qdrant 容器未运行")
            return True

        subprocess.run(
            ["docker", "stop", container_name],
            capture_output=True,
            check=True,
        )
        logger.info("Qdrant 容器已停止")
        return True

    except subprocess.CalledProcessError as e:
        logger.error(f"停止 Qdrant 容器失败: {e}")
        return False


def remove_qdrant_container() -> bool:
    container_name = get_qdrant_container_name()
    logger.info(f"删除 Qdrant 容器: {container_name}")

    try:
        result = subprocess.run(
            ["docker", "ps", "-a", "-q", "-f", f"name={container_name}"],
            capture_output=True,
            text=True,
        )

        if not result.stdout.strip():
            logger.info("Qdrant 容器不存在")
            return True

        subprocess.run(
            ["docker", "rm", container_name],
            capture_output=True,
            check=True,
        )
        logger.info("Qdrant 容器已删除")
        return True

    except subprocess.CalledProcessError as e:
        logger.error(f"删除 Qdrant 容器失败: {e}")
        return False


def clean_qdrant_data() -> bool:
    if not QDRANT_DATA_DIR.exists():
        logger.info("Qdrant 数据目录不存在")
        return True

    logger.warning(f"删除 Qdrant 数据目录: {QDRANT_DATA_DIR}")
    try:
        shutil.rmtree(QDRANT_DATA_DIR)
        logger.info("Qdrant 数据已清理")
        return True
    except Exception as e:
        logger.error(f"清理 Qdrant 数据失败: {e}")
        return False


def update_docker_compose(remove_qdrant: bool = True) -> bool:
    if not DOCKER_COMPOSE_FILE.exists():
        logger.info("docker-compose.yml 不存在，跳过")
        return True

    logger.info("更新 docker-compose.yml...")
    try:
        content = DOCKER_COMPOSE_FILE.read_text(encoding="utf-8")

        if "qdrant" not in content.lower():
            logger.info("docker-compose.yml 中没有 Qdrant 配置，跳过")
            return True

        backup_file = DOCKER_COMPOSE_FILE.with_suffix(".yml.bak_qdrant_rollback")
        backup_file.write_text(content, encoding="utf-8")
        logger.info(f"已备份原始文件: {backup_file}")

        logger.info(
            "注意: 请手动编辑 docker-compose.yml 移除 Qdrant 服务配置，"
            "或使用备份文件恢复"
        )
        return True

    except Exception as e:
        logger.error(f"更新 docker-compose.yml 失败: {e}")
        return False


def check_system_status() -> dict:
    logger.info("检查系统状态...")

    status = {
        "docker_available": check_docker_available(),
        "qdrant_container_running": False,
        "qdrant_data_exists": QDRANT_DATA_DIR.exists(),
    }

    if status["docker_available"]:
        container_name = get_qdrant_container_name()
        try:
            result = subprocess.run(
                ["docker", "ps", "-q", "-f", f"name={container_name}"],
                capture_output=True,
                text=True,
            )
            status["qdrant_container_running"] = bool(result.stdout.strip())
        except Exception:
            pass

    return status


def main():
    parser = argparse.ArgumentParser(description="Qdrant 迁移回滚脚本")
    parser.add_argument(
        "--keep-data",
        action="store_true",
        help="保留 Qdrant 数据目录（仅停止服务）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅检查状态，不执行回滚",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="跳过确认，直接执行回滚",
    )

    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("Qdrant 迁移回滚工具")
    print("=" * 60)

    status = check_system_status()
    print("\n当前状态:")
    print(json.dumps(status, ensure_ascii=False, indent=2))

    if args.dry_run:
        print("\n[Dry Run] 仅检查状态，不执行回滚")
        return

    if not args.force:
        print("\n警告：此操作将停止 Qdrant 服务并可能删除数据！")
        confirm = input("确认执行回滚？(yes/no): ").strip().lower()
        if confirm not in ("yes", "y"):
            print("已取消回滚操作")
            return

    print("\n" + "=" * 60)
    print("开始回滚...")
    print("=" * 60)

    start_time = time.time()
    success = True
    steps = []

    if status["qdrant_container_running"]:
        step_ok = stop_qdrant_container()
        steps.append(("停止 Qdrant 容器", step_ok))
        if not step_ok:
            success = False

        step_ok = remove_qdrant_container()
        steps.append(("删除 Qdrant 容器", step_ok))
        if not step_ok:
            success = False
    else:
        steps.append(("Qdrant 容器检查", True))
        logger.info("Qdrant 容器未运行，跳过停止步骤")

    if not args.keep_data:
        step_ok = clean_qdrant_data()
        steps.append(("清理 Qdrant 数据", step_ok))
        if not step_ok:
            success = False
    else:
        steps.append(("保留 Qdrant 数据", True))
        logger.info("使用 --keep-data，保留数据目录")

    step_ok = update_docker_compose()
    steps.append(("更新 docker-compose.yml", step_ok))

    elapsed = time.time() - start_time

    print("\n" + "=" * 60)
    print("回滚结果:")
    print("-" * 60)
    for step_name, step_ok in steps:
        status_icon = "✓" if step_ok else "✗"
        print(f"  {status_icon} {step_name}")
    print("-" * 60)
    print(f"总耗时: {elapsed:.2f}s")
    print(f"最终状态: {'成功' if success else '部分失败'}")
    print("=" * 60)

    if success:
        print("\n回滚完成！系统已恢复到迁移前状态。")
        print("\n后续步骤:")
        print("  1. 确认系统正常运行")
        print("  2. 如有需要，手动从 docker-compose.yml 移除 Qdrant 配置")
        print("  3. 验证数据库中 Question 表数据完整性")
    else:
        print("\n回滚过程中出现部分问题，请检查日志。")
        sys.exit(1)


if __name__ == "__main__":
    main()
