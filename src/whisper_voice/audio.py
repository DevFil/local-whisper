# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""
Audio recording functionality for Local Whisper.
"""

import threading
import time

import numpy as np
import sounddevice as sd

from .config import get_config
from .utils import log


class Recorder:
    """Microphone audio recorder with thread-safe start/stop."""

    def __init__(self):
        self._recording = threading.Event()
        self._input_ready = threading.Event()
        self._chunks = []
        self._chunks_lock = threading.Lock()
        self._input_health_lock = threading.Lock()
        self._stream = None
        self._state_lock = threading.Lock()
        self._monitor_lock = threading.Lock()
        self._start_time = None
        self._current_rms: float = 0.0
        self._input_has_signal = False
        self._input_frames_seen = 0
        self._input_warmup_timeout = 0.45
        self._input_live_threshold = 1e-9
        self._start_retries = 2

        config = get_config()
        buf_size = int(config.audio.sample_rate * config.audio.pre_buffer) if config.audio.pre_buffer > 0 else 0
        self._pre_buffer: np.ndarray = np.zeros(buf_size, dtype=np.float32)
        self._pre_buffer_pos: int = 0
        self._monitor_stream = None

    @property
    def recording(self) -> bool:
        """Whether recording is currently active."""
        return self._recording.is_set()

    @property
    def duration(self) -> float:
        """Get current recording duration in seconds."""
        if self._start_time and self._recording.is_set():
            return time.time() - self._start_time
        return 0.0

    @property
    def rms_level(self) -> float:
        """Current audio RMS level (0.0-1.0), updated each callback."""
        return self._current_rms

    def start_monitoring(self):
        """Start the pre-recording monitor. Rebuilds a dead stream silently."""
        config = get_config()
        if config.audio.pre_buffer <= 0:
            return
        with self._monitor_lock:
            if self._monitor_stream is not None:
                try:
                    if self._monitor_stream.active:
                        return
                except Exception:
                    pass
                self._silent_close_monitor()
            try:
                self._monitor_stream = sd.InputStream(
                    samplerate=config.audio.sample_rate,
                    channels=1,
                    dtype=np.float32,
                    callback=self._monitor_callback,
                    blocksize=512
                )
                self._monitor_stream.start()
            except Exception as e:
                log(f"Monitor stream warning: {e}", "WARN")
                self._monitor_stream = None

    def stop_monitoring(self):
        """Stop the pre-recording monitor."""
        with self._monitor_lock:
            self._silent_close_monitor()

    def _silent_close_monitor(self):
        if self._monitor_stream:
            try:
                self._monitor_stream.stop()
                self._monitor_stream.close()
            except Exception:
                pass
            self._monitor_stream = None

    def heartbeat_monitoring(self):
        """Restart the monitor stream if it died."""
        config = get_config()
        if config.audio.pre_buffer <= 0:
            return
        if self.recording:
            return
        with self._monitor_lock:
            alive = False
            if self._monitor_stream is not None:
                try:
                    alive = bool(self._monitor_stream.active)
                except Exception:
                    alive = False
            if alive:
                return
            log("Audio monitor stream dead — restarting", "WARN")
            self._silent_close_monitor()
        self.start_monitoring()

    def _monitor_callback(self, data, frames, time_info, status):
        """Fill ring buffer with latest audio."""
        flat = data[:, 0]
        n = len(flat)
        buf_size = len(self._pre_buffer)
        if buf_size == 0:
            return
        if n >= buf_size:
            self._pre_buffer[:] = flat[-buf_size:]
            self._pre_buffer_pos = 0
        else:
            end = self._pre_buffer_pos + n
            if end <= buf_size:
                self._pre_buffer[self._pre_buffer_pos:end] = flat
            else:
                first = buf_size - self._pre_buffer_pos
                self._pre_buffer[self._pre_buffer_pos:] = flat[:first]
                self._pre_buffer[:n - first] = flat[first:]
            self._pre_buffer_pos = end % buf_size

    def start(self) -> bool:
        """Start recording audio from microphone."""
        config = get_config()
        with self._state_lock:
            if self._recording.is_set():
                return False
            self.stop_monitoring()
            with self._chunks_lock:
                if config.audio.pre_buffer > 0 and len(self._pre_buffer) > 0:
                    # Reassemble the ring buffer in one allocation instead of
                    # np.roll + .copy (which allocates twice).
                    buf_size = len(self._pre_buffer)
                    pos = self._pre_buffer_pos
                    pre = np.empty(buf_size, dtype=np.float32)
                    pre[:buf_size - pos] = self._pre_buffer[pos:]
                    pre[buf_size - pos:] = self._pre_buffer[:pos]
                    self._chunks = [pre]
                else:
                    self._chunks = []

            last_error: Exception | None = None
            for attempt in range(1, self._start_retries + 1):
                self._reset_input_health()
                self._recording.set()
                try:
                    self._stream = sd.InputStream(
                        samplerate=config.audio.sample_rate,
                        channels=1,
                        dtype=np.float32,
                        callback=self._callback,
                        blocksize=1024
                    )
                    self._stream.start()

                    if self._wait_for_live_input():
                        self._start_time = time.time()
                        return True

                    last_error = RuntimeError("microphone returned all-zero audio")
                    log("Mic returned silence during warm-up; resetting audio input", "WARN")
                except Exception as e:
                    last_error = e
                    if attempt < self._start_retries:
                        log(f"Mic start failed; resetting audio input ({e})", "WARN")

                self._recording.clear()
                self._silent_close_stream()
                with self._chunks_lock:
                    self._chunks = []
                if attempt < self._start_retries:
                    self.reset_audio_host(close_stream=False)
                    time.sleep(0.15)

            if last_error is None:
                last_error = RuntimeError("microphone did not become ready")
            log(f"Mic error: {last_error}", "ERR")
            self._recording.clear()
            return False

    def stop(self) -> np.ndarray:
        """Stop recording and return audio data."""
        with self._state_lock:
            if not self._recording.is_set():
                return np.array([], dtype=np.float32)
            self._recording.clear()
            self._silent_close_stream()
            with self._chunks_lock:
                if self._chunks:
                    audio = np.concatenate(self._chunks)
                    self._chunks = []
                    return audio
                self._chunks = []
                return np.array([], dtype=np.float32)

    def reset_audio_host(self, close_stream: bool = True):
        """Reset PortAudio after macOS leaves an input device in a stale state."""
        if close_stream:
            self._silent_close_stream()
        try:
            terminate = getattr(sd, "_terminate", None)
            initialize = getattr(sd, "_initialize", None)
            if callable(terminate):
                terminate()
            if callable(initialize):
                initialize()
        except Exception as e:
            log(f"Audio input reset warning: {e}", "WARN")

    def _reset_input_health(self):
        self._input_ready.clear()
        with self._input_health_lock:
            self._input_has_signal = False
            self._input_frames_seen = 0

    def _wait_for_live_input(self) -> bool:
        if self._input_warmup_timeout <= 0:
            return True
        if not self._input_ready.wait(timeout=self._input_warmup_timeout):
            return False
        with self._input_health_lock:
            return self._input_has_signal

    def _silent_close_stream(self):
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as e:
                log(f"Stream cleanup warning: {e}", "WARN")
            self._stream = None

    def _callback(self, data, frames, time_info, status):
        """Audio stream callback - accumulate chunks (thread-safe)."""
        flat = data[:, 0]
        self._current_rms = float(np.sqrt(np.mean(data ** 2)))

        with self._input_health_lock:
            self._input_frames_seen += len(flat)
            if np.any(np.abs(flat) > self._input_live_threshold):
                self._input_has_signal = True
            if self._input_has_signal or self._input_frames_seen >= 512:
                self._input_ready.set()

        # Check recording flag inside lock to prevent race with stop()
        with self._chunks_lock:
            if self._recording.is_set():
                self._chunks.append(flat.copy())
