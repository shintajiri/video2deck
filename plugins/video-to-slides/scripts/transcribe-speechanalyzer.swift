import Foundation
import Speech
import AVFoundation

// =====================================================================
// transcribe-speechanalyzer
// Apple SpeechAnalyzer (on-device, macOS 26+) batch transcriber.
//
// usage:  transcribe-speechanalyzer <input audio/video> [output.txt] [locale]
//   locale defaults to ja-JP. output defaults to <input>.txt
//
// Output: one line per recognized segment, prefixed with [HH:MM:SS].
// All processing is fully local; no audio leaves the machine.
//
// Build:  swiftc -O transcribe-speechanalyzer.swift -o transcribe-speechanalyzer
// =====================================================================

func log(_ s: String) {
    FileHandle.standardError.write((s + "\n").data(using: .utf8)!)
}

@available(macOS 26.0, *)
func run() async throws {
    let args = CommandLine.arguments
    guard args.count >= 2 else {
        log("usage: transcribe-speechanalyzer <input> [output.txt] [locale]")
        exit(2)
    }
    let inputURL = URL(fileURLWithPath: args[1])
    let outputURL: URL = args.count >= 3
        ? URL(fileURLWithPath: args[2])
        : inputURL.deletingPathExtension().appendingPathExtension("txt")
    let localeID = args.count >= 4 ? args[3] : "ja-JP"
    let locale = Locale(identifier: localeID)

    let supported = await SpeechTranscriber.supportedLocales
    guard supported.contains(where: { $0.identifier(.bcp47) == Locale(identifier: localeID).identifier(.bcp47) }) else {
        log("locale \(localeID) not supported. Supported: \(supported.map { $0.identifier(.bcp47) }.joined(separator: ","))")
        exit(3)
    }

    let transcriber = SpeechTranscriber(
        locale: locale,
        transcriptionOptions: [],
        reportingOptions: [],
        attributeOptions: [.audioTimeRange]
    )

    // Download & install the on-device locale model if needed.
    if let installationRequest = try await AssetInventory.assetInstallationRequest(supporting: [transcriber]) {
        log("downloading \(localeID) model...")
        try await installationRequest.downloadAndInstall()
        log("model installed")
    }

    let analyzer = SpeechAnalyzer(modules: [transcriber])
    let audioFile = try AVAudioFile(forReading: inputURL)

    // Consume results concurrently while the analyzer feeds the file.
    let resultsTask = Task { () -> String in
        var lines: [String] = []
        for try await result in transcriber.results {
            let txt = String(result.text.characters)
            let start = result.range.start.seconds
            let h = Int(start) / 3600
            let m = (Int(start) % 3600) / 60
            let s = Int(start) % 60
            lines.append(String(format: "[%02d:%02d:%02d] ", h, m, s) + txt)
        }
        return lines.joined(separator: "\n")
    }

    log("analyzing \(inputURL.lastPathComponent) ...")
    if let lastSample = try await analyzer.analyzeSequence(from: audioFile) {
        try await analyzer.finalizeAndFinish(through: lastSample)
    } else {
        await analyzer.cancelAndFinishNow()
    }

    let text = try await resultsTask.value
    try text.write(to: outputURL, atomically: true, encoding: .utf8)
    log("DONE: \(text.count) chars -> \(outputURL.path)")
}

if #available(macOS 26.0, *) {
    let sema = DispatchSemaphore(value: 0)
    Task {
        do { try await run() }
        catch { log("ERROR: \(error)"); exit(1) }
        sema.signal()
    }
    sema.wait()
} else {
    log("requires macOS 26+ (SpeechAnalyzer)")
    exit(1)
}
