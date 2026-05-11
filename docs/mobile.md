# Mobile Apps

The Flutter app is Local Whisper's mobile speech-to-text surface. It gives iOS and Android a recorder app, local model packs, searchable history, modes, and a native keyboard for text fields.

Record in the app, keep data on the device, and use modes to shape the finished text. The iOS keyboard extension and Android input method bring Local Whisper actions into other apps.

iOS transcribes locally with WhisperKit/Core ML. Android records local WAV audio and transcribes on-device through `sherpa_onnx`. Parakeet-TDT v3 INT8 ONNX is the recommended Android pack; Qwen3-ASR 0.6B INT8 ONNX is the broader multilingual pack.

<p align="center">
  <img src="../assets/ios-hero-record.png" width="760" alt="Local Whisper iOS record screen">
</p>

<p align="center">
  <img src="../assets/ios-important-screens.png" width="860" alt="Local Whisper iOS record, history, and modes screens">
</p>

## Status

| Surface | Status | Notes |
|---------|--------|-------|
| iOS app + keyboard | Native transcription wired | Record and transcribe locally with `AVAudioEngine` plus WhisperKit/Core ML. The keyboard extension gives text fields Local Whisper modes, punctuation, haptics, and setup verification. |
| Android app + keyboard | Native transcription wired | Record local WAV audio, transcribe with sherpa-onnx model packs, and verify the native input method in a real text field. The app keeps history, modes, and model packs on device. |

## Product Flow

First launch shows setup before the tab shell:

1. Welcome
2. Recommended model install
3. Microphone permission
4. Keyboard setup and practice
5. Finish

Replay setup from Settings. The progress indicator is read-only; move with explicit actions. Optional model choices open in place instead of sending you to another tab.

<p align="center">
  <img src="../assets/ios-setup-settings.png" width="760" alt="Local Whisper iOS setup and settings screens">
</p>

## Architecture

Flutter owns the app shell, local model-pack management, local history, modes, settings, clipboard output, and deterministic cleanup.

Native iOS uses:

- `ios/Runner/LocalSpeechBridge.swift`: microphone recording plus WhisperKit/Core ML bridge.
- `ios/LocalWhisperKeyboard/`: native keyboard extension with mode buttons, punctuation, haptics, and Verify.

Native Android uses:

- `android/app/src/main/kotlin/info/gabrimatic/localwhisper/MainActivity.kt`: microphone status, 16 kHz mono WAV recording, levels, app settings, input-method settings, keyboard status, keyboard verification, and keyboard preference sync.
- `android/app/src/main/kotlin/info/gabrimatic/localwhisper/LocalWhisperInputMethodService.kt`: Verify, mode markers, punctuation, space, new-line, delete, settings, haptics, and quick-insert visibility.
- `android/app/src/main/AndroidManifest.xml`: microphone, haptics, app identity, launcher identity, and input-method service.

Flutter owns Android transcription through `lib/src/sherpa_speech_service.dart`. The service runs sherpa-onnx in a background isolate, loads the installed model folder, reads the recorded WAV file, and returns the transcript through the same `NativeSpeechService` result shape used by iOS.

## History And Keyboard Control

History stays on the device. The History tab shows how many entries are saved, total recorded duration, and an approximate saved-history size. You can export the full history as Markdown to the clipboard, delete one transcript, or clear all history after confirmation.

The Models tab shows installed pack count and model storage. Installed packs can be removed from the device when you no longer need them.

The iOS keyboard reads haptics and quick-insert settings from the shared app group. The Android keyboard reads the same settings from setup preferences: turning off quick insert keeps Verify, Space, New line, and Delete available, while hiding mode and punctuation shortcuts.

## Model Packs

The model manager installs Local Whisper model families from Hugging Face snapshots, retries transient manifest and file-download failures, and verifies installed files against a local manifest before a pack becomes available.

WhisperKit Large v3 is wired for iOS transcription. Android uses sherpa-onnx model packs. Qwen3-ASR, Parakeet-TDT v3, WhisperKit, and Kokoro are local model families; they are not hosted APIs and they are not sent to a cloud speech service.

| Pack | Approx size | Notes |
|------|-------------|-------|
| Parakeet-TDT v3 INT8 ONNX | 640 MB | Default Android local ASR pack through sherpa-onnx. |
| Qwen3-ASR 0.6B INT8 ONNX | 940 MB | Android multilingual ASR pack through sherpa-onnx. |
| Qwen3-ASR MLX | 3.8 GB | Desktop/iOS-family local ASR pack. |
| Parakeet-TDT v3 MLX | 2.3 GB | Desktop/iOS-family local ASR pack. |
| Kokoro-82M TTS | 371 MB | Local text-to-speech model. |
| WhisperKit Large v3 | 550 MB | Wired iOS Core ML folder. |

## Android Notes

Android debug QA can seed the recommended pack and interaction data:

```bash
flutter run --dart-define=LOCAL_WHISPER_QA_SEED=true
```

Android requests microphone permission, records local WAV audio, shows levels, stores data locally, verifies the native input method, and transcribes with the installed sherpa-onnx model pack. Debug QA seeds interaction state so emulator passes can exercise the app and keyboard flow without downloading a large model each time.

Large model downloads can fail on flaky networks or temporary Hugging Face edge responses. The app retries transient manifest and file failures automatically. If the install still fails, tap Download again after the connection is stable.

## Checks

Run from `src/flutter/local_whisper`:

```bash
flutter pub get
flutter analyze
flutter test
flutter build ios --simulator --debug
flutter build apk --debug

# after a WhisperKit pack is installed in the simulator:
flutter test integration_test/native_transcription_test.dart -d <simulator-id> --dart-define=LOCAL_WHISPER_MODEL_PATH=<installed-model-folder>
```
