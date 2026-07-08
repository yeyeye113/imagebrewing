#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
imagebrewing 镜像自动拉取脚本
功能:
  1. 定期检查 ghcr.io 上的新镜像版本
  2. 当检测到新镜像时自动拉取并重启容器
  3. 支持多项目: future-sim, quant-trader, quant-monitor

使用方式:
  python watchdog.py                    # 前台运行
  python watchdog.py --daemon            # 后台运行
  python watchdog.py --once              # 只检查一次
  python watchdog.py --project future-sim  # 只检查指定项目
"""

import os
import sys
import time
import json
import argparse
import subprocess
from datetime import datetime
from pathlib import Path

PROJECTS = {
    "future-sim": {
        "image": "ghcr.io/yeyeye113/imagebrewing-future-sim",
        "container": "future-sim",
    },
    "quant-trader": {
        "image": "ghcr.io/yeyeye113/imagebrewing-quant-trader",
        "container": "quanttrader",
    },
    "quant-monitor": {
        "image": "ghcr.io/yeyeye113/imagebrewing-quant-monitor",
        "container": "quant-monitor",
    },
}

CHECK_INTERVAL = 300  # 5分钟

def log(msg):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")

def docker_pull(image):
    try:
        log(f"正在拉取镜像: {image}")
        result = subprocess.run(["docker", "pull", image], capture_output=True, text=True, timeout=300)
        if result.returncode == 0:
            log(f"✓ 镜像拉取成功: {image}")
            return True
        else:
            log(f"✗ 镜像拉取失败: {result.stderr}")
            return False
    except Exception as e:
        log(f"✗ 拉取镜像异常: {e}")
        return False

def docker_restart(container):
    try:
        log(f"正在重启容器: {container}")
        subprocess.run(["docker", "stop", container], capture_output=True, timeout=30)
        subprocess.run(["docker", "rm", container], capture_output=True, timeout=30)
        subprocess.run(["docker", "run", "-d", "--name", container, "--restart", "unless-stopped", "-p", "80:80", f"{container}:latest" if container != "quanttrader" else f"{container}:latest"], capture_output=True, text=True)
        log(f"✓ 容器已重启: {container}")
        return True
    except Exception as e:
        log(f"✗ 重启容器失败: {e}")
        return False

def get_remote_digest(image):
    try:
        result = subprocess.run(["docker", "manifest", "inspect", image], capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            data = json.loads(result.stdout)
            return data.get("config", {}).get("digest")
        return None
    except:
        return None

def get_local_digest(image):
    try:
        result = subprocess.run(["docker", "image", "inspect", image], capture_output=True, text=True, timeout=10)
        if result.returncode == 0 and result.stdout:
            data = json.loads(result.stdout)
            digests = data[0].get("RepoDigests", [])
            return digests[0] if digests else None
        return None
    except:
        return None

def check_and_update(name, config):
    image = config["image"]
    container = config["container"]
    log(f"检查项目: {name}")

    remote_digest = get_remote_digest(f"{image}:latest")
    local_digest = get_local_digest(f"{image}:latest")

    if not remote_digest:
        log(f"  无法获取远程镜像digest")
        return False

    if remote_digest == local_digest:
        log(f"  {name}: 已是最新版本")
        return False

    log(f"  {name}: 发现新版本!")
    if docker_pull(f"{image}:latest"):
        # 根据容器名称选择正确的重启命令
        if container == "future-sim":
            subprocess.run(["docker", "stop", container], capture_output=True)
            subprocess.run(["docker", "rm", container], capture_output=True)
            subprocess.run(["docker", "run", "-d", "--name", container, "--restart", "unless-stopped", "-p", "80:80", f"{image}:latest"], capture_output=True)
        log(f"✓ {name} 更新完成!")
        return True
    return False

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--daemon", action="store_true")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--project", type=str)
    parser.add_argument("--interval", type=int, default=CHECK_INTERVAL)
    args = parser.parse_args()

    log("=" * 50)
    log("imagebrewing 镜像自动拉取脚本启动")
    log("=" * 50)

    projects = {args.project: PROJECTS[args.project]} if args.project else PROJECTS

    if args.once:
        for name, config in projects.items():
            check_and_update(name, config)
        return

    while True:
        for name, config in projects.items():
            try:
                check_and_update(name, config)
            except Exception as e:
                log(f"检查 {name} 时发生异常: {e}")
        log(f"下次检查在 {args.interval} 秒后...")
        time.sleep(args.interval)

if __name__ == "__main__":
    main()
