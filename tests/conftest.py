from __future__ import annotations

import os


def pytest_configure() -> None:
    """测试运行时强制 deterministic 策略，避免依赖 .env 中的 LLM 配置。"""
    os.environ.setdefault("INTAKE_AGENT_STRATEGY", "deterministic")
    os.environ.setdefault("DIAGNOSIS_AGENT_STRATEGY", "deterministic")
    os.environ.setdefault("SUPPORT_REPLY_AGENT_STRATEGY", "deterministic")
