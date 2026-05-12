# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""
Unit tests for memory-conscious audio handling.
"""

from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np
from conftest import import_with_stubs


def _fake_config():
    return SimpleNamespace(audio=SimpleNamespace(sample_rate=16000, pre_buffer=0.0))


class TestRecorderMemory:
    def test_stop_clears_accumulated_chunks(self):
        fake_sd = SimpleNamespace(InputStream=Mock())
        with patch.dict("sys.modules", {"sounddevice": fake_sd}):
            import whisper_voice.audio as audio_mod

        with patch.object(audio_mod, "get_config", return_value=_fake_config()):
            recorder = audio_mod.Recorder()

        recorder._recording.set()
        recorder._chunks = [
            np.array([0.1, 0.2], dtype=np.float32),
            np.array([0.3], dtype=np.float32),
        ]

        audio = recorder.stop()

        assert np.allclose(audio, np.array([0.1, 0.2, 0.3], dtype=np.float32))
        assert recorder._chunks == []

    def test_start_retries_after_dead_zero_input(self):
        streams = []

        class FakeStream:
            def __init__(self, *_, callback=None, **__):
                self.callback = callback
                self.active = False
                self.closed = False
                streams.append(self)

            def start(self):
                self.active = True
                value = 0.0 if len(streams) == 1 else 0.01
                data = np.full((16, 1), value, dtype=np.float32)
                self.callback(data, len(data), None, None)

            def stop(self):
                self.active = False

            def close(self):
                self.closed = True

        fake_sd = SimpleNamespace(
            InputStream=FakeStream,
            _terminate=Mock(),
            _initialize=Mock(),
        )
        with patch.dict("sys.modules", {"sounddevice": fake_sd}):
            import whisper_voice.audio as audio_mod

        with patch.object(audio_mod, "get_config", return_value=_fake_config()):
            recorder = audio_mod.Recorder()
            recorder._input_warmup_timeout = 0.01

        assert recorder.start() is True
        assert len(streams) == 2
        assert streams[0].closed is True
        assert recorder.recording is True
        assert fake_sd._terminate.called
        assert fake_sd._initialize.called

    def test_start_retries_after_portaudio_open_error(self):
        calls = {"count": 0}

        class FakeStream:
            def __init__(self, *_, callback=None, **__):
                calls["count"] += 1
                if calls["count"] == 1:
                    raise RuntimeError("Error opening InputStream: Internal PortAudio error")
                self.callback = callback
                self.active = False

            def start(self):
                self.active = True
                data = np.full((16, 1), 0.01, dtype=np.float32)
                self.callback(data, len(data), None, None)

            def stop(self):
                self.active = False

            def close(self):
                pass

        fake_sd = SimpleNamespace(
            InputStream=FakeStream,
            _terminate=Mock(),
            _initialize=Mock(),
        )
        with patch.dict("sys.modules", {"sounddevice": fake_sd}):
            import whisper_voice.audio as audio_mod

        with patch.object(audio_mod, "get_config", return_value=_fake_config()):
            recorder = audio_mod.Recorder()
            recorder._input_warmup_timeout = 0.01

        assert recorder.start() is True
        assert calls["count"] == 2
        assert recorder.recording is True
        assert fake_sd._terminate.called
        assert fake_sd._initialize.called


class TestAudioProcessorMemory:
    def test_raw_audio_reuses_original_float32_buffer(self):
        mod = import_with_stubs("whisper_voice.audio_processor")
        cfg = SimpleNamespace(audio=SimpleNamespace(
            vad_enabled=False,
            noise_reduction=False,
            normalize_audio=False,
        ))
        proc = mod.AudioProcessor(cfg)
        audio = np.array([0.1, -0.2, 0.3], dtype=np.float32)

        result = proc.process(audio, 16000)

        assert result.raw_audio is audio
        assert np.allclose(result.audio, audio)

    def test_segment_long_audio_reuses_float32_views(self):
        mod = import_with_stubs("whisper_voice.audio_processor")
        cfg = SimpleNamespace(audio=SimpleNamespace(
            vad_enabled=False,
            noise_reduction=False,
            normalize_audio=False,
        ))
        proc = mod.AudioProcessor(cfg)
        sample_rate = 16000
        audio = np.zeros(304 * sample_rate, dtype=np.float32)

        chunks = proc.segment_long_audio(audio, sample_rate)

        assert len(chunks) == 2
        assert all(chunk.dtype == np.float32 for chunk in chunks)
        assert all(np.shares_memory(chunk, audio) for chunk in chunks)
