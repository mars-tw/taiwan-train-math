import Foundation
import ImageIO
import UIKit
import Vision
import XCTest

final class SevenDistrictUITests: XCTestCase {
    private let gameBundleID = "tw.mars.sevendistrictreckoning"

    private struct OCRFrame {
        let image: UIImage
        let observations: [VNRecognizedTextObservation]
    }

    private enum OCRFailure: Error {
        case missingCGImage
        case unsupportedImageOrientation
    }

    override func setUpWithError() throws {
        continueAfterFailure = false
    }

    func testRotateTapStartAndHoldForSimctlCapture() throws {
        let isPad = UIDevice.current.userInterfaceIdiom == .pad
        let targetOrientation: UIDeviceOrientation = isPad ? .landscapeRight : .landscapeLeft
        let orientationName = isPad ? "landscapeRight" : "landscapeLeft"
        // The unchanged Godot Info.plist supports LandscapeLeft on iPhone and
        // LandscapeRight on iPad. A portrait simctl frame was the old failure.
        XCUIDevice.shared.orientation = targetOrientation

        let game = XCUIApplication(bundleIdentifier: gameBundleID)
        game.activate() // activate the *already installed* Godot app; no test hook
        XCUIDevice.shared.orientation = targetOrientation
        XCTAssertTrue(waitUntil(30) { game.state == .runningForeground },
                      "Installed Godot app did not become foreground")
        XCTAssertTrue(waitUntil(30) {
            let size = XCUIScreen.main.screenshot().image.size
            return size.width > size.height && game.frame.width > game.frame.height
        }, "Simulator screenshot or app frame stayed portrait after rotation")

        let documents = try XCTUnwrap(
            FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first
        )
        let activatedImage = XCUIScreen.main.screenshot().image
        let activatedFrame = game.frame
        guard let activatedCGImage = activatedImage.cgImage,
              game.state == .runningForeground,
              activatedImage.size.width > activatedImage.size.height,
              activatedFrame.width > activatedFrame.height else {
            XCTFail("Cannot release activation gate without a foreground landscape screenshot and app frame")
            return
        }

        // The host captures a native Simulator frame before the first OCR.
        let activatedReady = documents.appendingPathComponent("seven-activated-ready.txt")
        let activatedCaptured = documents.appendingPathComponent("seven-activated-captured.flag")
        try? FileManager.default.removeItem(at: activatedCaptured)
        let activatedEvidence = """
        bundle=\(gameBundleID)
        phase=activated
        orientation=\(orientationName)
        screenshotUIImageSize=\(activatedImage.size.width),\(activatedImage.size.height)
        screenshotScale=\(activatedImage.scale)
        screenshotCGImagePixels=\(activatedCGImage.width),\(activatedCGImage.height)
        screenshotImageOrientation=\(activatedImage.imageOrientation)
        gameFrame=\(rectString(activatedFrame))

        """
        try activatedEvidence.write(to: activatedReady, atomically: true, encoding: .utf8)
        let activationAcknowledged = waitUntil(120, every: 0.25) {
            FileManager.default.fileExists(atPath: activatedCaptured.path)
        }
        XCTAssertTrue(activationAcknowledged,
                      "Host did not acknowledge an actual raw activation simctl screenshot")
        guard activationAcknowledged else { return }
        print("SEVEN_ACTIVATED orientation=\(orientationName) imagePoints=\(activatedImage.size.width)x\(activatedImage.size.height) scale=\(activatedImage.scale) nativePixels=\(activatedCGImage.width)x\(activatedCGImage.height) gameFrame=\(rectString(activatedFrame))")

        // Godot Control text may have no accessibility node. Locate the
        // visibly rendered Start label using full native screenshot pixels.
        var titleFrame: OCRFrame?
        var start: VNRecognizedTextObservation?
        var titleAttempt = 0
        XCTAssertTrue(waitUntil(420, every: 5) {
            titleAttempt += 1
            do {
                let frame = try self.readVisibleText(phase: "TITLE", attempt: titleAttempt)
                guard let found = frame.observations.first(where: {
                    self.matches($0, "開始新遊戲")
                }) else { return false }
                titleFrame = frame
                start = found
                return true
            } catch {
                self.logOCRError(error, phase: "TITLE", attempt: titleAttempt)
                return false
            }
        }, "No visible 開始新遊戲 control in the actual Simulator screenshot within 420 seconds")
        guard let start, let titleFrame else { return }

        // Vision returns a lower-left-origin box for the orientation-corrected
        // image. UIImage.size is the displayed point size; XCUITest uses a
        // top-left-origin frame in those same screen points.
        let box = start.boundingBox
        guard box.width > 0, box.height > 0,
              box.minX.isFinite, box.minY.isFinite,
              box.maxX.isFinite, box.maxY.isFinite,
              box.minX >= 0, box.minY >= 0,
              box.maxX <= 1, box.maxY <= 1 else {
            XCTFail("OCR Start box is not a finite in-screen rectangle: \(rectString(box))")
            return
        }
        let screenPoint = CGPoint(
            x: titleFrame.image.size.width * box.midX,
            y: titleFrame.image.size.height * (1 - box.midY)
        )
        let appFrame = game.frame
        guard game.state == .runningForeground,
              titleFrame.image.size.width > titleFrame.image.size.height,
              appFrame.width > 0, appFrame.height > 0,
              appFrame.contains(screenPoint) else {
            XCTFail("OCR Start point \(pointString(screenPoint)) is outside foreground app frame \(rectString(appFrame))")
            return
        }
        let x = (screenPoint.x - appFrame.minX) / appFrame.width
        let y = (screenPoint.y - appFrame.minY) / appFrame.height
        guard x.isFinite, y.isFinite,
              (0...1).contains(x), (0...1).contains(y) else {
            XCTFail("OCR Start point could not map into the app frame")
            return
        }
        guard game.exists else {
            XCTFail("Godot app element disappeared before reading the XCUI tap point")
            return
        }
        let tapCoordinate = game.coordinate(withNormalizedOffset: CGVector(dx: x, dy: y))
        let xcuiPoint = tapCoordinate.screenPoint
        let dx = xcuiPoint.x - screenPoint.x
        let dy = xcuiPoint.y - screenPoint.y
        let pointDistance = (dx * dx + dy * dy).squareRoot()
        guard xcuiPoint.x.isFinite, xcuiPoint.y.isFinite,
              appFrame.contains(xcuiPoint),
              pointDistance.isFinite, pointDistance <= 8 else {
            XCTFail("XCUI tap point \(pointString(xcuiPoint)) differs from OCR point \(pointString(screenPoint)) or leaves app frame \(rectString(appFrame))")
            return
        }
        print("SEVEN_START_BOX ocrBox=\(rectString(box)) appFrame=\(rectString(appFrame)) ocrPoint=\(pointString(screenPoint)) xcuiPoint=\(pointString(xcuiPoint)) errorPoints=\(pointDistance) normalized=\(x),\(y)")

        let titleReady = documents.appendingPathComponent("seven-title-ready.txt")
        let titleCaptured = documents.appendingPathComponent("seven-title-captured.flag")
        try? FileManager.default.removeItem(at: titleCaptured)
        let titleEvidence = """
        bundle=\(gameBundleID)
        phase=title
        orientation=\(orientationName)
        startVisible=true
        startOCRBox=\(rectString(box))
        screenshotUIImageSize=\(titleFrame.image.size.width),\(titleFrame.image.size.height)
        gameFrame=\(rectString(appFrame))
        startOCRScreenPoint=\(pointString(screenPoint))
        startXCUIScreenPoint=\(pointString(xcuiPoint))
        startTapScreenPoint=\(pointString(xcuiPoint))
        startCoordinateErrorPoints=\(pointDistance)
        startTapNormalized=\(x),\(y)

        """
        try titleEvidence.write(to: titleReady, atomically: true, encoding: .utf8)
        let titleAcknowledged = waitUntil(120, every: 0.25) {
            FileManager.default.fileExists(atPath: titleCaptured.path)
        }
        XCTAssertTrue(titleAcknowledged,
                      "Host did not acknowledge an actual raw title simctl screenshot")
        guard titleAcknowledged else { return }

        // XCUICoordinate is dynamic. Refuse the tap if the app frame moved
        // while the host captured its title screenshot.
        let currentXCUI = tapCoordinate.screenPoint
        let movedX = currentXCUI.x - xcuiPoint.x
        let movedY = currentXCUI.y - xcuiPoint.y
        let movedDistance = (movedX * movedX + movedY * movedY).squareRoot()
        let currentDX = currentXCUI.x - screenPoint.x
        let currentDY = currentXCUI.y - screenPoint.y
        let currentError = (currentDX * currentDX + currentDY * currentDY).squareRoot()
        guard game.state == .runningForeground,
              appFrame.contains(currentXCUI),
              movedDistance.isFinite, movedDistance <= 8,
              currentError.isFinite, currentError <= 8 else {
            XCTFail("XCUI Start coordinate moved after title capture: \(pointString(currentXCUI))")
            return
        }
        tapCoordinate.tap()

        // The title may already show a dim MAIN-001 HUD behind its modal.
        // Require the Start control to disappear and MAIN-001 to remain visible
        // in two separate real screen reads before releasing the capture gate.
        var stableGameplayFrames = 0
        var gameplayAttempt = 0
        let gameplayStable = waitUntil(60, every: 3) {
            gameplayAttempt += 1
            guard game.state == .runningForeground else {
                stableGameplayFrames = 0
                print("SEVEN_OCR_GAMEPLAY attempt=\(gameplayAttempt) error=app-not-foreground")
                return false
            }
            do {
                let frame = try self.readVisibleText(phase: "GAMEPLAY", attempt: gameplayAttempt)
                let titleStillVisible = frame.observations.contains {
                    self.matches($0, "開始新遊戲")
                }
                let missionVisible = frame.observations.contains {
                    self.matches($0, "MAIN-001")
                }
                stableGameplayFrames = (!titleStillVisible && missionVisible)
                    ? stableGameplayFrames + 1 : 0
                print("SEVEN_OCR_GAMEPLAY attempt=\(gameplayAttempt) start=\(titleStillVisible) main001=\(missionVisible) stable=\(stableGameplayFrames)")
                return stableGameplayFrames >= 2
            } catch {
                stableGameplayFrames = 0
                self.logOCRError(error, phase: "GAMEPLAY", attempt: gameplayAttempt)
                return false
            }
        }
        XCTAssertTrue(gameplayStable,
                      "Start tap did not produce two stable visible MAIN-001 screenshots")
        guard gameplayStable else { return }

        let readyImage = XCUIScreen.main.screenshot()
        let attachment = XCTAttachment(screenshot: readyImage)
        attachment.name = "SevenDistrict-MAIN-001-before-simctl"
        attachment.lifetime = .keepAlways
        add(attachment)

        let ready = documents.appendingPathComponent("seven-main001-ready.txt")
        let captured = documents.appendingPathComponent("seven-main001-captured.flag")
        try? FileManager.default.removeItem(at: captured)
        let evidence = "bundle=\(gameBundleID)\norientation=\(orientationName)\nstartTapNormalized=\(x),\(y)\nmission=MAIN-001\n"
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

    private func readVisibleText(phase: String, attempt: Int) throws -> OCRFrame {
        let image = XCUIScreen.main.screenshot().image
        guard let cgImage = image.cgImage else { throw OCRFailure.missingCGImage }
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        request.recognitionLanguages = ["zh-Hant", "en-US"]
        request.usesLanguageCorrection = false
        // Chinese does not support customWords. Vision gets all native pixels
        // plus the UIImage's explicit display orientation; no resampling.
        let handler = VNImageRequestHandler(
            cgImage: cgImage,
            orientation: try cgOrientation(for: image.imageOrientation),
            options: [:]
        )
        try handler.perform([request])
        let observations = request.results ?? []
        let top = observations.prefix(4).compactMap { $0.topCandidates(1).first?.string }
            .map { boundedLogText($0, limit: 48) }.joined(separator: " | ")
        print("SEVEN_OCR_\(phase) attempt=\(attempt) results=\(observations.count) top=\"\(top)\" nativePixels=\(cgImage.width)x\(cgImage.height) imageOrientation=\(image.imageOrientation)")
        return OCRFrame(image: image, observations: observations)
    }

    private func logOCRError(_ error: Error, phase: String, attempt: Int) {
        print("SEVEN_OCR_\(phase) attempt=\(attempt) error=\(boundedLogText(String(describing: error), limit: 160))")
    }

    private func boundedLogText(_ text: String, limit: Int) -> String {
        String(text.replacingOccurrences(of: "\n", with: " ")
            .replacingOccurrences(of: "\r", with: " ")
            .replacingOccurrences(of: "\"", with: "'")
            .prefix(limit))
    }

    private func cgOrientation(for orientation: UIImage.Orientation) throws -> CGImagePropertyOrientation {
        switch orientation {
        case .up: return .up
        case .upMirrored: return .upMirrored
        case .down: return .down
        case .downMirrored: return .downMirrored
        case .left: return .left
        case .leftMirrored: return .leftMirrored
        case .right: return .right
        case .rightMirrored: return .rightMirrored
        @unknown default: throw OCRFailure.unsupportedImageOrientation
        }
    }

    private func rectString(_ rect: CGRect) -> String {
        "\(rect.minX),\(rect.minY),\(rect.width),\(rect.height)"
    }

    private func pointString(_ point: CGPoint) -> String {
        "\(point.x),\(point.y)"
    }
}
