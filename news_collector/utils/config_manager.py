"""YAML 설정 관리자"""

import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from news_collector.utils.logger import get_logger

logger = get_logger(__name__)


class ConfigManager:
    """
    YAML 설정 파일 로드 및 관리.

    - dot-notation 접근: config.get("defaults.locale")
    - 환경변수 오버라이드: NEWS_COLLECTOR_DEFAULTS_LOCALE
    - 여러 YAML 파일 병합 관리
    """

    def __init__(self, config_dir: Optional[str] = None) -> None:
        """
        Args:
            config_dir: 설정 파일 디렉토리 경로. None이면 기본 경로 사용.
        """
        if config_dir is None:
            config_dir = str(Path(__file__).parent.parent / "config")

        self._config_dir = config_dir
        self._configs: Dict[str, Dict[str, Any]] = {}
        self._merged: Dict[str, Any] = {}
        self._load_all()

    def _load_all(self) -> None:
        """config 디렉토리의 모든 YAML 파일 로드."""
        config_path = Path(self._config_dir)
        if not config_path.exists():
            logger.warning("설정 디렉토리가 존재하지 않습니다: %s", self._config_dir)
            return

        for yaml_file in sorted(config_path.glob("*.yaml")):
            if yaml_file.name.startswith("logging"):
                continue  # 로깅 설정은 별도 처리
            try:
                data = self.load(str(yaml_file))
                filename = yaml_file.stem
                self._configs[filename] = data
                self._merged.update(data)
                logger.debug("설정 파일 로드 완료: %s", yaml_file.name)
            except Exception as e:
                logger.error("설정 파일 로드 실패: %s - %s", yaml_file.name, e)

    def load(self, filepath: str) -> Dict[str, Any]:
        """
        특정 YAML 파일 로드.

        Args:
            filepath: YAML 파일 절대/상대 경로.

        Returns:
            파싱된 딕셔너리.
        """
        with open(filepath, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data if data is not None else {}

    def get(self, key_path: str, default: Any = None) -> Any:
        """
        dot-notation으로 설정값 조회.
        환경변수 오버라이드를 우선 확인.

        Args:
            key_path: "defaults.locale" 형태의 키 경로.
            default: 키가 없을 때 반환할 기본값.

        Returns:
            설정값 또는 기본값.
        """
        env_value = self._env_override(key_path)
        if env_value is not None:
            return env_value

        keys = key_path.split(".")
        current = self._merged
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return default
        return current

    def get_section(self, section: str) -> Dict[str, Any]:
        """
        설정의 특정 섹션 반환.

        Args:
            section: 최상위 키 이름 (예: "defaults", "validation").

        Returns:
            해당 섹션 딕셔너리. 없으면 빈 딕셔너리.
        """
        return self._merged.get(section, {})

    def get_file_config(self, filename: str) -> Dict[str, Any]:
        """
        특정 파일의 설정 전체 반환.

        Args:
            filename: 파일명 (확장자 제외). 예: "config", "natural_language_mapping"

        Returns:
            해당 파일의 설정 딕셔너리. 없으면 빈 딕셔너리.
        """
        return self._configs.get(filename, {})

    def _env_override(self, key_path: str) -> Optional[str]:
        """
        환경변수 오버라이드 확인.
        "defaults.locale" → "NEWS_COLLECTOR_DEFAULTS_LOCALE"

        Args:
            key_path: dot-notation 키 경로.

        Returns:
            환경변수 값 또는 None.
        """
        env_key = "NEWS_COLLECTOR_" + key_path.upper().replace(".", "_")
        return os.environ.get(env_key)
