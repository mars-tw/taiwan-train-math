import Foundation
import UIKit
import Vision
import XCTest

final class SevenDistrictUITests: XCTestCase {
    private let gameBundleID = "tw.mars.sevendistrictreckoning"

    override func setUpWithError() throws {
        continueAfterFailure = false
    }

    func testRotateTapStartAndHoldForSimctlCapture() throws {
        let isPad = UIDevice.current.userInterfaceIdiom == .pad
        // The unchanged Godot Info.plist supports LandscapeLeft on iPhone and
        // LandscapeRight on iPad. A portrait simctl frame was the old failure.
        XCUIDevice.shared.orientation = isPad ? .landscapeRight : .landscapeLeft

        let game = XCUIApplication(bundleIdentifier: gameBundleID)
        game.activate() // activate the *already installed* Godot app; no test hook
        XCUIDevice.shared.orientation = isPad ? .landscapeRight : .landscapeLeft
        XCTAssertTrue(waitUntil(30) { game.state == .runningForeground },
                      "Installed Godot app did not become foreground")
        XCTAssertTrue(waitUntil(30) {
            let size = XCUIScreen.main.screenshot().image.size
            return size.width > size.height
        }, "Simulator screen stayed portrait after XCUIDevice rotation")

        // Godot Control text is drawn into the game surface and may have no
        // accessibility node. Locate the visibly rendered Start label by
        // on-device Vision OCR, then tap its actual normalized XCUI coordinate.
        var start: VNRecognizedTextObservation?
        XCTAssertTrue(waitUntil(300, every: 5) {
            guard let observations = try? self.readVisibleText() else { return false }
            start = observations.first { self.matches($0, "開始新遊戲") }
            return start != nil
        }, "No visible 開始新遊戲 control in the actual Simulator screenshot")
        guard let start else { return }
        let rect = start.boundingBox // Vision origin: lower left
        let x = rect.midX
        let y = 1 - rect.midY
        XCTAssertTrue((0.05...0.95).contains(x) && (0.05...0.95).contains(y),
                      "OCR Start center lies outside the tappable app region")

        let documents = try XCTUnwrap(
            FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first
        )
        let titleReady = documents.appendingPathComponent("seven-title-ready.txt")
        let titleCaptured = documents.appendingPathComponent("seven-title-captured.flag")
        try? FileManager.default.removeItem(at: titleCaptured)
        let titleEvidence = "bundle=\(gameBundleID)\nphase=title\norientation=\(isPad ? "landscapeRight" : "landscapeLeft")\nstartVisible=true\nstartTapNormalized=\(x),\(y)\n"
        try titleEvidence.write(to: titleReady, atomically: true, encoding: .utf8)
        XCTAssertTrue(waitUntil(120, every: 0.25) {
            FileManager.default.fileExists(atPath: titleCaptured.path)
        }, "Host did not acknowledge an actual raw title simctl screenshot")

        game.coordinate(withNormalizedOffset: CGVector(dx: x, dy: y)).tap()

        // The title may already show a dim MAIN-001 HUD behind its modal.
        // Require the Start control to disappear and MAIN-001 to remain visible
        // in two separate real screen reads before releasing the capture gate.
        var stableGameplayFrames = 0
        XCTAssertTrue(waitUntil(60, every: 3) {
            guard game.state == .runningForeground,
                  let observations = try? self.readVisibleText() else {
                stableGameplayFrames = 0
                return false
            }
            let titleStillVisible = observations.contains { self.matches($0, "開始新遊戲") }
            let missionVisible = observations.contains { self.matches($0, "MAIN-001") }
            stableGameplayFrames = (!titleStillVisible && missionVisible)
                ? stableGameplayFrames + 1 : 0
            return stableGameplayFrames >= 2
        }, "Start tap did not produce a stable visible MAIN-001 screen")

        let readyImage = XCUIScreen.main.screenshot()
        let attachment = XCTAttachment(screenshot: readyImage)
        attachment.name = "SevenDistrict-MAIN-001-before-simctl"
        attachment.lifetime = .keepAlways
        add(attachment)

        let ready = documents.appendingPathComponent("seven-main001-ready.txt")
        let captured = documents.appendingPathComponent("seven-main001-captured.flag")
        try? FileManager.default.removeItem(at: captured)
        let evidence = "bundle=\(gameBundleID)\norientation=\(isPad ? "landscapeRight" : "landscapeLeft")\nstartTapNormalized=\(x),\(y)\nmission=MAIN-001\n"
        try evidence.write(to: ready, atomically: true, encoding: .utf8)

        // The host polls the real Simulator runner container for `ready`, takes
        // `xcrun simctl io <UDID> screenshot`, then writes the captured flag.
        // Holding the XCTest open keeps the unchanged game in foreground.
        XCTAssertTrue(waitUntil(120, every: 0.25) {
            FileManager.default.fileExists(atPath: captured.path)
        }, "Host did not acknowledge an actual simctl screenshot")
    }

    private func waitUntil(_ timeout: TimeInterval,
                           every interval: TimeInterval = 0.25,
                           condition: () -> Bool) -> Bool {
        let deadline = Date().addingTimeInterval(timeout)
        repeat {
            if condition() { return true }
            Thread.sleep(forTimeInterval: interval)
        } while Date() < deadline
        return false
    }

    private func matches(_ observation: VNRecognizedTextObservation,
                         _ needle: String) -> Bool {
        observation.topCandidates(3).contains { candidate in
            let text = candidate.string
                .replacingOccurrences(of: " ", with: "")
                .replacingOccurrences(of: "－", with: "-")
                .replacingOccurrences(of: "—", with: "-")
            return text.contains(needle)
        }
    }

    private func readVisibleText() throws -> [VNRecognizedTextObservation] {
        let image = XCUIScreen.main.screenshot().image
        let format = UIGraphicsImageRendererFormat()
        format.scale = 1
        format.opaque = true
        // UIImage.draw normalizes any screenshot orientation metadata before
        // Vision returns its lower-left-origin normalized bounding boxes.
        let upright = UIGraphicsImageRenderer(size: image.size, format: format)
            .image { _ in image.draw(in: CGRect(origin: .zero, size: image.size)) }
        let cgImage = try XCTUnwrap(upright.cgImage)
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        request.recognitionLanguages = ["zh-Hant", "en-US"]
        request.usesLanguageCorrection = false
        try VNImageRequestHandler(cgImage: cgImage, options: [:]).perform([request])
        return request.results ?? []
    }
}
