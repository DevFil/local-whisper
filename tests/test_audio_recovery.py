# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""Regression tests for stale macOS audio input recovery."""

import threading
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np


class _ImmediateTimer:
    def __init__(self, *_args, **_kwargs):
        pass

    def start(self):
        pass


def test_hotkey_recording_resets_audio_host_after_all_zero_capture(monkeypatch):
    import whisper_voice.app_recording as recording_mod
    from whisper_voice.app_recording import RecordingMixin

    recorder = SimpleNamespace(
        recording=True,
        stop=Mock(return_value=np.zeros(32, dtype=np.float32)),
        start_monitoring=Mock(),
        reset_audio_host=Mock(),
    )

    class DummyApp(RecordingMixin):
        pass

    app = DummyApp()
    app._hold_recording = False
    app._key_interceptor = None
    app._max_timer = None
    app._state_lock = threading.Lock()
    app._busy = False
    app.recorder = recorder
    app.config = SimpleNamespace(audio=SimpleNamespace(sample_rate=16000, min_duration=0))
    app._send_state_error = Mock()
    app._reset_to_idle = Mock()

    monkeypatch.setattr(recording_mod, "play_sound", Mock())
    monkeypatch.setattr(recording_mod.threading, "Timer", _ImmediateTimer)

    app._stop_recording()

    recorder.reset_audio_host.assert_called_once_with(close_stream=False)
    app._send_state_error.assert_called_once_with("Mic permission?")


def test_cli_listen_resets_audio_host_after_all_zero_capture():
    from whisper_voice.app_commands import CommandsMixin

    recorder = SimpleNamespace(
        recording=False,
        stop=Mock(return_value=np.zeros(32, dtype=np.float32)),
        reset_audio_host=Mock(),
        start_monitoring=Mock(),
    )
    recorder.start = Mock(side_effect=lambda: setattr(recorder, "recording", True) or True)

    class DummyApp(CommandsMixin):
        def _touch_model_activity(self):
            pass

    app = DummyApp()
    app._state_lock = threading.Lock()
    app._busy = False
    app._ready = True
    app.recorder = recorder
    app.config = SimpleNamespace(audio=SimpleNamespace(sample_rate=16000))

    sent = []
    app._cmd_listen(
        {"max_duration": 0, "raw": True},
        sent.append,
        SimpleNamespace(wait=lambda timeout=None: None),
    )

    recorder.reset_audio_host.assert_called_once_with(close_stream=False)
    assert sent[-1] == {"type": "error", "message": "No audio captured"}
