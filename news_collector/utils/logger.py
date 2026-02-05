"""로깅 설정 및 유틸리티"""

import logging
import logging.config
import os
from pathlib import Path
from typing import Optional

import yaml


def setup_logging(config_path: Optional[str] = None) -> None:
    """
    YAML 설정 파일 기반 로깅 초기화.

    Args:
        config_path: logging_config.yaml 경로. None이면 기본 경로 사용.
    """
    if config_path is None:
        config_path = str(
            Path(__file__).parent.parent / "config" / "logging_config.yaml"
        )

    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            log_config = yaml.safe_load(f)

        # logs 디렉토리 생성
        for handler in log_config.get("handlers", {}).values():
            if "filename" in handler:
                log_dir = os.path.dirname(handler["filename"])
                if log_dir:
                    os.makedirs(log_dir, exist_ok=True)

        logging.config.dictConfig(log_config)
    else:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        )


def get_logger(name: str) -> logging.Logger:
    """
    모듈별 로거 반환.

    Args:
        name: 로거 이름 (예: "news_collector.parsers.date_parser")
    """
    return logging.getLogger(name)
