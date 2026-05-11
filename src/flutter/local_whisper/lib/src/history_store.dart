import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import 'models.dart';

class HistoryStore {
  static const _historyKey = 'history.v1';
  static const _settingsKey = 'settings.v1';
  static const _modesKey = 'modes.v1';
  static const _modelsKey = 'models.v1';
  static const _onboardingKey = 'onboarding.v1';

  Future<List<TranscriptEntry>> loadHistory() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_historyKey);
    if (raw == null || raw.isEmpty) return const [];
    try {
      final decoded = jsonDecode(raw) as List<dynamic>;
      return decoded
          .whereType<Map>()
          .map((entry) => Map<String, Object?>.from(entry))
          .map(TranscriptEntry.fromJson)
          .toList(growable: false);
    } catch (_) {
      return const [];
    }
  }

  Future<void> saveHistory(List<TranscriptEntry> entries) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(
      _historyKey,
      jsonEncode(entries.map((entry) => entry.toJson()).toList()),
    );
  }

  Future<void> deleteHistoryEntry(String id) async {
    final entries = await loadHistory();
    await saveHistory(
      entries.where((entry) => entry.id != id).toList(growable: false),
    );
  }

  Future<void> clearHistory() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_historyKey);
  }

  static String exportMarkdown(List<TranscriptEntry> entries) {
    final buffer = StringBuffer()
      ..writeln('# Local Whisper History')
      ..writeln();
    if (entries.isEmpty) {
      buffer.writeln('No local transcriptions exported.');
      return buffer.toString().trimRight();
    }

    for (final entry in entries) {
      buffer
        ..writeln('## ${_exportDate(entry.createdAt)}')
        ..writeln()
        ..writeln('- Mode: ${entry.modeName}')
        ..writeln('- Locale: ${entry.localeId}')
        ..writeln('- Duration: ${entry.duration.toStringAsFixed(1)}s')
        ..writeln()
        ..writeln('### Final')
        ..writeln()
        ..writeln(entry.finalText.trim())
        ..writeln()
        ..writeln('### Raw')
        ..writeln()
        ..writeln(entry.rawText.trim())
        ..writeln();
    }
    return buffer.toString().trimRight();
  }

  static String _exportDate(DateTime value) {
    final utc = value.toUtc();
    String two(int number) => number.toString().padLeft(2, '0');
    return '${utc.year}-${two(utc.month)}-${two(utc.day)} '
        '${two(utc.hour)}:${two(utc.minute)} UTC';
  }

  Future<AppSettings> loadSettings() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_settingsKey);
    if (raw == null || raw.isEmpty) return const AppSettings();
    try {
      return AppSettings.fromJson(jsonDecode(raw) as Map<String, Object?>);
    } catch (_) {
      return const AppSettings();
    }
  }

  Future<void> saveSettings(AppSettings settings) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_settingsKey, jsonEncode(settings.toJson()));
  }

  Future<bool> loadOnboardingComplete() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getBool(_onboardingKey) ?? false;
  }

  Future<void> saveOnboardingComplete(bool complete) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_onboardingKey, complete);
  }

  Future<List<DictationMode>> loadModes() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_modesKey);
    if (raw == null || raw.isEmpty) return DictationMode.defaults;
    try {
      final decoded = jsonDecode(raw) as List<dynamic>;
      final custom = decoded
          .whereType<Map>()
          .map((mode) => Map<String, Object?>.from(mode))
          .map(DictationMode.fromJson)
          .toList(growable: false);
      return custom.isEmpty ? DictationMode.defaults : custom;
    } catch (_) {
      return DictationMode.defaults;
    }
  }

  Future<void> saveModes(List<DictationMode> modes) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(
      _modesKey,
      jsonEncode(modes.map((mode) => mode.toJson()).toList()),
    );
  }

  Future<Map<String, LocalModel>> loadModelState() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_modelsKey);
    if (raw == null || raw.isEmpty) return const {};
    try {
      final decoded = jsonDecode(raw) as List<dynamic>;
      return {
        for (final model
            in decoded
                .whereType<Map>()
                .map((item) => Map<String, Object?>.from(item))
                .map(LocalModel.fromJson))
          model.id: model,
      };
    } catch (_) {
      return const {};
    }
  }

  Future<void> saveModelState(List<LocalModel> models) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(
      _modelsKey,
      jsonEncode(models.map((model) => model.toJson()).toList()),
    );
  }
}
