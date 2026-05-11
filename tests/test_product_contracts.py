# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""
Product contract checks for user-facing copy and source-of-truth metadata.
"""

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_apple_intelligence_requirement_is_consistent():
    """Apple Intelligence copy should match the public macOS 26+ requirement."""
    paths = [
        "setup.sh",
        "src/whisper_voice/backends/__init__.py",
        "src/whisper_voice/grammar.py",
        "src/whisper_voice/cli/doctor.py",
        "LocalWhisperUI/Sources/LocalWhisperUI/OnboardingView.swift",
        "LocalWhisperUI/Sources/LocalWhisperUI/GrammarPanel.swift",
    ]

    for path in paths:
        content = _read(path)
        assert "macOS 15+" not in content, path
        assert "macOS 26+" in content, path


def test_apple_intelligence_optional_install_is_gated_to_macos_26():
    """Setup and doctor should not install Foundation Models support on unsupported macOS versions."""
    setup = _read("setup.sh")
    doctor = _read("src/whisper_voice/cli/doctor.py")

    assert 'if [[ "$MACOS_MAJOR" -ge 26 ]]' in setup
    assert "macos_major >= 26" in doctor


def test_user_facing_privacy_copy_allows_setup_network_access():
    """Privacy copy should not imply setup, model downloads, or updates never use the network."""
    paths = [
        "src/whisper_voice/__init__.py",
        "LocalWhisperUI/Sources/LocalWhisperUI/AboutView.swift",
        "LocalWhisperUI/Sources/LocalWhisperUI/OnboardingView.swift",
    ]

    for path in paths:
        content = _read(path).lower()
        assert "no internet" not in content, path
        assert "everything runs on your mac" not in content, path


def test_configuration_reference_matches_generated_default_config():
    """The full TOML reference should stay aligned with generated config files."""
    from whisper_voice.config.schema import DEFAULT_CONFIG

    docs = _read("docs/configuration.md")
    match = re.search(r"```toml\n(.*?)\n```", docs, re.DOTALL)
    assert match is not None

    default_config = tomllib.loads(DEFAULT_CONFIG)
    documented_config = tomllib.loads(match.group(1))

    assert documented_config.keys() == default_config.keys()
    for section in default_config:
        assert documented_config[section].keys() == default_config[section].keys(), section


def test_github_actions_use_current_node24_ready_actions():
    """CI should avoid deprecated Node 20 GitHub Actions runtimes."""
    workflow = _read(".github/workflows/ci.yml")
    dependabot = _read(".github/dependabot.yml")

    assert "uses: actions/checkout@v6" in workflow
    assert "uses: actions/setup-python@v6" in workflow
    assert 'package-ecosystem: "github-actions"' in dependabot


def test_ci_runs_flutter_static_and_widget_gates():
    """The mobile app is a public product surface and should be covered by CI."""
    workflow = _read(".github/workflows/ci.yml")
    dependabot = _read(".github/dependabot.yml")

    assert "src/flutter/local_whisper" in workflow
    assert "flutter analyze" in workflow
    assert "flutter test" in workflow
    assert 'package-ecosystem: "pub"' in dependabot
    assert 'directory: "/src/flutter/local_whisper"' in dependabot


def test_android_keyboard_honors_quick_insert_setting():
    """The Android input method should match the app's keyboard quick-insert toggle."""
    keyboard = _read(
        "src/flutter/local_whisper/android/app/src/main/kotlin/info/gabrimatic/localwhisper/LocalWhisperInputMethodService.kt"
    )

    assert "quickInsertEnabled()" in keyboard
    assert "if (quickInsertEnabled())" in keyboard
    assert '"[Clean] "' in keyboard
    assert '"[Prompt] "' in keyboard
