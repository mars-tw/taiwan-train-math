import Foundation
import UIKit
import Capacitor
import AVFoundation

@objc(OfflineSpeechPlugin)
public class OfflineSpeechPlugin: CAPPlugin, CAPBridgedPlugin {
    public let identifier = "OfflineSpeechPlugin"
    public let jsName = "OfflineSpeech"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "getStatus", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "speak", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "stop", returnType: CAPPluginReturnPromise)
    ]
    private let synthesizer = AVSpeechSynthesizer()
    private var voice: AVSpeechSynthesisVoice? {
        AVSpeechSynthesisVoice.speechVoices().first { $0.language == "zh-TW" && $0.quality == .default }
    }
    public override func load() {
        NotificationCenter.default.addObserver(self, selector: #selector(background), name: UIApplication.didEnterBackgroundNotification, object: nil)
    }
    @objc private func background() { synthesizer.stopSpeaking(at: .immediate) }
    @objc public func getStatus(_ call: CAPPluginCall) {
        DispatchQueue.main.async { call.resolve(["available": self.voice != nil, "offline": self.voice != nil, "language": "zh-TW"]) }
    }
    @objc public func speak(_ call: CAPPluginCall) {
        let text = (call.getString("text") ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        DispatchQueue.main.async {
            guard let voice = self.voice, !text.isEmpty, text.count <= 3000 else { call.reject("LOCAL_VOICE_UNAVAILABLE"); return }
            self.synthesizer.stopSpeaking(at: .immediate)
            let utterance = AVSpeechUtterance(string: text)
            utterance.voice = voice
            utterance.rate = 0.42
            self.synthesizer.speak(utterance)
            call.resolve()
        }
    }
    @objc public func stop(_ call: CAPPluginCall) {
        DispatchQueue.main.async { self.synthesizer.stopSpeaking(at: .immediate); call.resolve() }
    }
    deinit { NotificationCenter.default.removeObserver(self) }
}
