# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""Regression tests for model cache truth and inline download progress."""

from pathlib import Path
import threading
from types import SimpleNamespace
from unittest.mock import Mock


def test_engine_status_rejects_incomplete_huggingface_cache(monkeypatch, tmp_path):
    import whisper_voice.engines.status as status_mod

    monkeypatch.setattr(status_mod, "MODEL_DIR", tmp_path)
    cache = tmp_path / "models--mlx-community--parakeet-tdt-0.6b-v3"
    (cache / "refs").mkdir(parents=True)
    (cache / "refs" / "main").write_text("abc123", encoding="utf-8")

    state = status_mod.engine_model_status("parakeet_v3")

    assert state["downloaded"] is False
    assert state["download_status"] == "partial"
    assert state["size_mb"] > 0


def test_engine_status_requires_complete_snapshot_files(monkeypatch, tmp_path):
    import whisper_voice.engines.status as status_mod

    monkeypatch.setattr(status_mod, "MODEL_DIR", tmp_path)
    snapshot = (
        tmp_path
        / "models--mlx-community--parakeet-tdt-0.6b-v3"
        / "snapshots"
        / "abc123"
    )
    snapshot.mkdir(parents=True)
    (snapshot / "config.json").write_text("{}", encoding="utf-8")
    (snapshot / "model.safetensors").write_bytes(b"weights")

    state = status_mod.engine_model_status("parakeet_v3")

    assert state["downloaded"] is True
    assert state["download_status"] == "downloaded"
    assert state["size_mb"] > 0


def test_download_watcher_reports_aggregate_cache_bytes(tmp_path):
    from whisper_voice.engines.download_progress import DownloadWatcher

    cache = tmp_path / "models--org--model"
    cache.mkdir()
    (cache / "partial.bin").write_bytes(b"x" * 100)
    messages = []

    watcher = DownloadWatcher("test_model", cache, 200, messages.append)
    watcher.start()
    watcher.finish()

    first = messages[0]
    assert first["bytes"] == 100
    assert first["percent"] == 0.5


def test_download_watcher_has_distinct_canceled_phase(tmp_path):
    from whisper_voice.engines.download_progress import DownloadWatcher

    cache = tmp_path / "models--org--model"
    cache.mkdir()
    messages = []

    watcher = DownloadWatcher("test_model", cache, 0, messages.append)
    watcher.start()
    watcher.finish(error="Download canceled", phase="canceled")

    assert messages[-1]["phase"] == "canceled"
    assert messages[-1]["error"] == "Download canceled"


def test_transcription_panel_does_not_optimistically_mark_engine_active():
    root = Path(__file__).resolve().parents[1]
    panel = (
        root
        / "LocalWhisperUI"
        / "Sources"
        / "LocalWhisperUI"
        / "TranscriptionPanel.swift"
    ).read_text(encoding="utf-8")

    assert "appState.config.transcription.engine = id" not in panel
    assert 'sendAction("cancel_download"' in panel


def test_canceled_downloads_do_not_render_as_failed_selection_state():
    root = Path(__file__).resolve().parents[1]
    app_state = (
        root
        / "LocalWhisperUI"
        / "Sources"
        / "LocalWhisperUI"
        / "AppState.swift"
    ).read_text(encoding="utf-8")
    shared_views = (
        root
        / "LocalWhisperUI"
        / "Sources"
        / "LocalWhisperUI"
        / "SharedViews.swift"
    ).read_text(encoding="utf-8")

    assert 'progress.phase == "ready" || progress.phase == "canceled"' in app_state
    assert 'case "canceled":    return "Canceled"' in shared_views


def test_about_external_links_are_not_rendered_as_selected_state():
    root = Path(__file__).resolve().parents[1]
    about = (
        root
        / "LocalWhisperUI"
        / "Sources"
        / "LocalWhisperUI"
        / "AboutView.swift"
    ).read_text(encoding="utf-8")

    assert ".buttonStyle(.borderedProminent)" not in about


def test_permission_buttons_request_prompts_instead_of_only_opening_settings():
    root = Path(__file__).resolve().parents[1]
    onboarding = (
        root
        / "LocalWhisperUI"
        / "Sources"
        / "LocalWhisperUI"
        / "OnboardingView.swift"
    ).read_text(encoding="utf-8")
    advanced = (
        root
        / "LocalWhisperUI"
        / "Sources"
        / "LocalWhisperUI"
        / "AdvancedPanel.swift"
    ).read_text(encoding="utf-8")
    app_ipc = (root / "src" / "whisper_voice" / "app_ipc.py").read_text(encoding="utf-8")

    for source in (onboarding, advanced, app_ipc):
        assert "request_microphone_permission" in source
        assert "request_accessibility_permission" in source


def test_settings_model_downloads_stay_out_of_overlay_phase():
    root = Path(__file__).resolve().parents[1]
    switching = (root / "src" / "whisper_voice" / "app_switching.py").read_text(encoding="utf-8")

    assert 'self._send_state_update("idle", status_text=text)' in switching
    assert "model downloads do not open the" in switching


def test_engine_switch_download_failure_keeps_current_engine_loaded(monkeypatch, tmp_path):
    import whisper_voice.app_switching as switching_mod
    from whisper_voice.app_switching import SwitchingMixin

    class FakeWatcher:
        def __init__(self, *args, **kwargs):
            self.finished = False

        def start(self):
            pass

        def set_phase(self, phase):
            pass

        def finish(self, error=None):
            self.finished = True

    class DummyApp(SwitchingMixin):
        pass

    old_transcriber = SimpleNamespace(close=Mock())
    app = DummyApp()
    app._busy = False
    app._state_lock = threading.Lock()
    app._download_cancel_lock = threading.Lock()
    app._download_cancel_events = {}
    app.config = SimpleNamespace(transcription=SimpleNamespace(engine="parakeet_v3"))
    app.transcriber = old_transcriber
    app.recorder = SimpleNamespace(recording=False)
    app.ipc = SimpleNamespace(send=Mock())
    app._current_status = "Ready"
    app._send_state_update = Mock()
    app._send_state_error = Mock()
    app._send_engines_status = Mock()
    app._send_config_snapshot = Mock()
    app._prefetch_hf_snapshot = Mock(return_value=(False, "network down"))

    monkeypatch.setattr(
        switching_mod,
        "engine_model_status",
        Mock(return_value={
            "downloaded": False,
            "cache_dir": str(tmp_path / "models--org--model"),
            "hf_repo": "org/model",
        }),
    )
    assert "expected_size_bytes" not in switching_mod.__dict__
    monkeypatch.setattr(switching_mod, "DownloadWatcher", FakeWatcher)

    app._switch_engine("qwen3_asr")

    old_transcriber.close.assert_not_called()
    assert app.transcriber is old_transcriber
    assert app._settings_operation_active is False
    assert app._busy is False
    app._send_state_error.assert_not_called()
    assert all(call.args[0] == "idle" for call in app._send_state_update.call_args_list)


def test_settings_operation_busy_snapshot_stays_idle():
    from whisper_voice.app_ipc import IPCMixin

    class DummyApp(IPCMixin):
        pass

    sent = []
    app = DummyApp()
    app.ipc = SimpleNamespace(send=sent.append)
    app.recorder = SimpleNamespace(recording=False, duration=0.0, rms_level=0.0)
    app._busy = True
    app._settings_operation_active = True
    app._current_status = "Downloading Qwen3-ASR model..."

    app._send_state_update()

    assert sent[-1]["phase"] == "idle"
    assert sent[-1]["status_text"] == "Downloading Qwen3-ASR model..."


def test_engine_switch_registers_cancel_before_first_progress(monkeypatch, tmp_path):
    import whisper_voice.app_switching as switching_mod
    from whisper_voice.app_switching import SwitchingMixin

    class DummyApp(SwitchingMixin):
        pass

    old_transcriber = SimpleNamespace(close=Mock())
    app = DummyApp()
    app._busy = False
    app._state_lock = threading.Lock()
    app._download_cancel_lock = threading.Lock()
    app._download_cancel_events = {}
    app.config = SimpleNamespace(transcription=SimpleNamespace(engine="parakeet_v3"))
    app.transcriber = old_transcriber
    app.recorder = SimpleNamespace(recording=False)
    app.ipc = SimpleNamespace(send=Mock())
    app._current_status = "Ready"
    app._send_state_update = Mock()
    app._send_state_error = Mock()
    app._send_engines_status = Mock()
    app._send_config_snapshot = Mock()

    class CancelOnFirstProgressWatcher:
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            app._cancel_download("qwen3_asr")

        def set_phase(self, phase):
            pass

        def finish(self, error=None, phase=None):
            pass

    def prefetch(_target, _repo, cancel_event):
        assert cancel_event.is_set()
        return False, "Download canceled"

    app._prefetch_hf_snapshot = Mock(side_effect=prefetch)
    monkeypatch.setattr(
        switching_mod,
        "engine_model_status",
        Mock(return_value={
            "downloaded": False,
            "cache_dir": str(tmp_path / "models--org--model"),
            "hf_repo": "org/model",
        }),
    )
    monkeypatch.setattr(switching_mod, "DownloadWatcher", CancelOnFirstProgressWatcher)

    app._switch_engine("qwen3_asr")

    old_transcriber.close.assert_not_called()
    assert app._settings_operation_active is False
    assert app._busy is False
    assert any("download canceled" in (call.kwargs.get("status_text") or "").lower()
               for call in app._send_state_update.call_args_list)
    assert app._download_cancel_events == {}
