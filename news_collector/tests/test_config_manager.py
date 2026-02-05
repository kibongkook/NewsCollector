"""ConfigManager 테스트"""

import os
import tempfile

import pytest
import yaml

from news_collector.utils.config_manager import ConfigManager


class TestConfigManagerLoad:
    """설정 파일 로드 테스트."""

    def test_load_real_config(self, config_manager: ConfigManager) -> None:
        """실제 config.yaml 로드 확인."""
        locale = config_manager.get("defaults.locale")
        assert locale == "ko_KR"

    def test_load_natural_language_mapping(self, config_manager: ConfigManager) -> None:
        """natural_language_mapping.yaml 로드 확인."""
        nl_config = config_manager.get_file_config("natural_language_mapping")
        assert "intent_patterns" in nl_config
        assert "category_keywords" in nl_config

    def test_load_missing_directory(self) -> None:
        """존재하지 않는 디렉토리 처리."""
        config = ConfigManager(config_dir="/nonexistent/path")
        assert config.get("anything") is None

    def test_load_empty_directory(self) -> None:
        """빈 디렉토리 처리."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = ConfigManager(config_dir=tmpdir)
            assert config.get("anything") is None


class TestConfigManagerGet:
    """dot-notation 접근 테스트."""

    def test_get_nested_value(self, config_manager: ConfigManager) -> None:
        """중첩 키 접근."""
        tz = config_manager.get("defaults.timezone")
        assert tz == "Asia/Seoul"

    def test_get_top_level(self, config_manager: ConfigManager) -> None:
        """최상위 키 접근."""
        defaults = config_manager.get("defaults")
        assert isinstance(defaults, dict)
        assert "locale" in defaults

    def test_get_missing_key_returns_default(self, config_manager: ConfigManager) -> None:
        """존재하지 않는 키는 기본값 반환."""
        result = config_manager.get("nonexistent.key", "fallback")
        assert result == "fallback"

    def test_get_missing_key_returns_none(self, config_manager: ConfigManager) -> None:
        """기본값 미지정 시 None 반환."""
        result = config_manager.get("nonexistent.key")
        assert result is None

    def test_get_deeply_nested(self, config_manager: ConfigManager) -> None:
        """깊은 중첩 접근."""
        value = config_manager.get("scoring.source_diversity.max_same_source_in_top_n")
        assert value == 3


class TestConfigManagerEnvOverride:
    """환경변수 오버라이드 테스트."""

    def test_env_override(self, config_manager: ConfigManager) -> None:
        """환경변수가 설정값을 오버라이드."""
        os.environ["NEWS_COLLECTOR_DEFAULTS_LOCALE"] = "en_US"
        try:
            result = config_manager.get("defaults.locale")
            assert result == "en_US"
        finally:
            del os.environ["NEWS_COLLECTOR_DEFAULTS_LOCALE"]

    def test_env_override_not_set(self, config_manager: ConfigManager) -> None:
        """환경변수 미설정 시 YAML 값 사용."""
        result = config_manager.get("defaults.locale")
        assert result == "ko_KR"


class TestConfigManagerSection:
    """섹션 접근 테스트."""

    def test_get_section(self, config_manager: ConfigManager) -> None:
        """섹션 전체 반환."""
        defaults = config_manager.get_section("defaults")
        assert defaults["locale"] == "ko_KR"
        assert defaults["limit"] == 20

    def test_get_missing_section(self, config_manager: ConfigManager) -> None:
        """없는 섹션은 빈 딕셔너리."""
        result = config_manager.get_section("nonexistent")
        assert result == {}

    def test_get_file_config(self, config_manager: ConfigManager) -> None:
        """특정 파일 설정 반환."""
        nl = config_manager.get_file_config("natural_language_mapping")
        assert "intent_patterns" in nl

    def test_get_missing_file_config(self, config_manager: ConfigManager) -> None:
        """없는 파일은 빈 딕셔너리."""
        result = config_manager.get_file_config("nonexistent_file")
        assert result == {}
