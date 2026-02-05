"""공유 테스트 fixture"""

import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, Any
from zoneinfo import ZoneInfo

import pytest
import yaml

from news_collector.utils.config_manager import ConfigManager


# 테스트 기준 시각 (결정론적 테스트용)
REFERENCE_TIME = datetime(2026, 2, 5, 14, 0, 0, tzinfo=ZoneInfo("Asia/Seoul"))


@pytest.fixture
def reference_time() -> datetime:
    """고정된 기준 시각."""
    return REFERENCE_TIME


@pytest.fixture
def config_dir() -> str:
    """실제 config 디렉토리 경로."""
    return str(Path(__file__).parent.parent / "config")


@pytest.fixture
def config_manager(config_dir: str) -> ConfigManager:
    """실제 설정 파일 기반 ConfigManager."""
    return ConfigManager(config_dir=config_dir)


@pytest.fixture
def defaults(config_manager: ConfigManager) -> Dict[str, Any]:
    """기본값 딕셔너리."""
    return config_manager.get_section("defaults")


@pytest.fixture
def nl_config(config_manager: ConfigManager) -> Dict[str, Any]:
    """자연어 매핑 설정."""
    return config_manager.get_file_config("natural_language_mapping")


@pytest.fixture
def tmp_config_dir():
    """임시 config 디렉토리 (단위 테스트용)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_data = {
            "defaults": {
                "locale": "ko_KR",
                "timezone": "Asia/Seoul",
                "country": "KR",
                "language": "ko",
                "market": "ko_KR",
                "popularity_type": "latest",
                "group_by": "none",
                "limit": 20,
                "offset": 0,
                "verified_sources_only": False,
                "diversity": True,
            },
            "validation": {
                "max_limit": 100,
                "min_limit": 1,
                "allowed_popularity_types": ["trending", "popular", "latest", "quality"],
                "allowed_group_by": ["day", "source", "none"],
            },
        }
        config_path = os.path.join(tmpdir, "config.yaml")
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(config_data, f, allow_unicode=True)

        yield tmpdir
