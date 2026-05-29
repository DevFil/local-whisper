import SwiftUI
import AppKit

// MARK: - Advanced panel (storage + diagnostics)

struct AdvancedPanel: View {
    @Environment(AppState.self) private var appState

    var body: some View {
        ScrollView {
            Form {
                connectionSection
                permissionsSection
                storageSection
                lifecycleSection
                diagnosticsSection
                dangerSection
            }
            .formStyle(.grouped)
        }
    }

    // MARK: - Connection

    private var connectionSection: some View {
        Section {
            LabeledContent("Service") {
                StatusPill(text: appState.connectionState.label, tone: appState.connectionState.tone)
            }
            LabeledContent("Engine") {
                Text(engineDisplay)
                    .font(Theme.Typography.body)
                    .foregroundStyle(.secondary)
            }
            LabeledContent("Grammar") {
                Text(backendDisplay)
                    .font(Theme.Typography.body)
                    .foregroundStyle(.secondary)
            }
        } header: {
            SettingsSectionHeader(
                symbol: "antenna.radiowaves.left.and.right",
                title: "Live status",
                description: "What the running service is doing right now."
            )
        }
    }

    private var engineDisplay: String {
        switch appState.config.transcription.engine {
        case "parakeet_v3": return "Parakeet-TDT v3"
        case "qwen3_asr":   return "Qwen3-ASR"
        case "whisperkit":  return "WhisperKit"
        default:            return appState.config.transcription.engine
        }
    }

    private var backendDisplay: String {
        guard appState.config.grammar.enabled else { return "Disabled" }
        switch appState.config.grammar.backend {
        case "apple_intelligence": return "Apple Intelligence"
        case "ollama":             return "Ollama"
        case "lm_studio":          return "LM Studio"
        default:                   return appState.config.grammar.backend
        }
    }

    // MARK: - Permissions

    private var permissionsSection: some View {
        Section {
            HStack(spacing: Theme.Spacing.s) {
                Button {
                    appState.ipcClient?.sendAction("request_microphone_permission")
                } label: {
                    Label("Request microphone", systemImage: "mic.fill")
                }
                Button {
                    appState.ipcClient?.sendAction("request_accessibility_permission")
                } label: {
                    Label("Request accessibility", systemImage: "keyboard.fill")
                }
            }

            InlineNotice(
                kind: .info,
                text: "Use these when macOS did not show the prompt during setup. If access was denied before, the matching System Settings page opens."
            )
        } header: {
            SettingsSectionHeader(
                symbol: "lock.shield",
                title: "Permissions",
                description: "Ask macOS for the access needed by global dictation."
            )
        }
    }

    // MARK: - Storage

    private var storageSection: some View {
        Section {
            LabeledContent("Backup directory") {
                DeferredTextField(label: "~/.whisper", initialValue: appState.config.backup.directory) { v in
                    appState.config.backup.directory = v
                    appState.ipcClient?.sendConfigUpdate(section: "backup", key: "directory", value: v)
                }
                .textFieldStyle(.roundedBorder)
                .frame(maxWidth: 320)
            }

            HStack(spacing: Theme.Spacing.s) {
                Button {
                    NSWorkspace.shared.open(URL(fileURLWithPath: AppDirectories.whisper))
                } label: {
                    Label("Open backup folder", systemImage: "folder")
                }
                Button {
                    NSWorkspace.shared.selectFile(AppDirectories.config, inFileViewerRootedAtPath: "")
                } label: {
                    Label("Reveal config.toml", systemImage: "doc.text.magnifyingglass")
                }
            }

            InlineNotice(
                kind: .info,
                text: "Path where transcription history and audio recordings are stored. Restart required after changing."
            )
        } header: {
            SettingsSectionHeader(
                symbol: "internaldrive",
                title: "Storage",
                description: "Where Local Whisper writes audio backups, transcripts, and config."
            )
        }
    }

    // MARK: - Lifecycle

    private var lifecycleSection: some View {
        Section {
            LabeledContent("Unload models after idle") {
                HStack {
                    Stepper("", value: Binding(
                        get: { appState.config.service.idleUnloadMinutes },
                        set: { value in
                            appState.config.service.idleUnloadMinutes = value
                            appState.ipcClient?.sendConfigUpdate(section: "service", key: "idle_unload_minutes", value: value)
                        }
                    ), in: 0...240, step: 5)
                    .labelsHidden()
                    Text(idleUnloadLabel)
                        .monoStat(width: 90)
                }
            }
            .help("Unload transcription and speech models after this many idle minutes. 0 keeps models loaded.")

            InlineNotice(
                kind: .info,
                text: "Lower values free memory sooner. Higher values make the next dictation start faster."
            )
        } header: {
            SettingsSectionHeader(
                symbol: "memorychip",
                title: "Model lifecycle",
                description: "Balance memory pressure against first-word latency."
            )
        }
    }

    private var idleUnloadLabel: String {
        let minutes = appState.config.service.idleUnloadMinutes
        return minutes == 0 ? "Never" : "\(minutes)m"
    }

    // MARK: - Diagnostics

    private var diagnosticsSection: some View {
        Section {
            HStack(spacing: Theme.Spacing.s) {
                Button {
                    let path = (NSHomeDirectory() as NSString).appendingPathComponent(".whisper/service.log")
                    NSWorkspace.shared.open(URL(fileURLWithPath: path))
                } label: {
                    Label("Open service log", systemImage: "doc.plaintext")
                }
                Button {
                    runWhInTerminal("doctor")
                } label: {
                    Label("Run wh doctor", systemImage: "stethoscope")
                }
            }

            InlineNotice(
                kind: .info,
                text: "If something feels off, the doctor command checks deps, models, permissions, and the service."
            )
        } header: {
            SettingsSectionHeader(
                symbol: "stethoscope",
                title: "Diagnostics",
                description: "Inspect the running service and its environment."
            )
        }
    }

    // MARK: - Danger zone

    private var dangerSection: some View {
        Section {
            HStack(spacing: Theme.Spacing.s) {
                Button(role: .destructive) {
                    appState.ipcClient?.sendAction("restart")
                } label: {
                    Label("Restart service", systemImage: "arrow.clockwise.circle")
                }
            }
            InlineNotice(
                kind: .info,
                text: "To update Local Whisper, run `wh update` in Terminal. It only works when installed from a git clone."
            )
        } header: {
            SettingsSectionHeader(
                symbol: "exclamationmark.triangle",
                title: "Service control",
                description: "Restart cleanly reloads models."
            )
        }
    }

    private func runWhInTerminal(_ command: String) {
        let script = """
        tell application "Terminal"
            activate
            do script "wh \(command)"
        end tell
        """
        if let appleScript = NSAppleScript(source: script) {
            var error: NSDictionary?
            appleScript.executeAndReturnError(&error)
        }
    }
}
