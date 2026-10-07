"""Independent Phone screen-only XCTest capture; unchanged Godot game source."""
import importlib.util
import pathlib
import sys


def generate(root):
    here = pathlib.Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location("godot_capture_project", here / "create-godot-capture-project.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    root = pathlib.Path(root)
    module.generate(root, "crackveil-vanguard", "iphone")
    (root / "CaptureUITests.swift").write_text('''import XCTest
import UIKit
import ImageIO
import CryptoKit
final class CaptureUITests: XCTestCase {
    private func capture(_ stage: String) {
        print("STORE_SCREEN_PRE_CAPTURE=" + stage + ";deviceOrientation:" + String(XCUIDevice.shared.orientation.rawValue))
        let screenshot = XCUIScreen.main.screenshot()
        let image = screenshot.image
        let source = CGImageSourceCreateWithData(screenshot.pngRepresentation as CFData, nil)
        let properties = source.flatMap { CGImageSourceCopyPropertiesAtIndex($0, 0, nil) as? [String:Any] }
        let geometry: [String:Any] = ["stage":stage,"deviceOrientation":XCUIDevice.shared.orientation.rawValue,
            "imageOrientation":image.imageOrientation.rawValue,"imageWidth":image.size.width,"imageHeight":image.size.height,
            "imageScale":image.scale,"cgWidth":image.cgImage?.width ?? 0,"cgHeight":image.cgImage?.height ?? 0,
            "pngOrientation":properties?[kCGImagePropertyOrientation as String] ?? 0]
        if let data = try? JSONSerialization.data(withJSONObject:geometry,options:[.sortedKeys]),
           let text = String(data:data,encoding:.utf8) { print("STORE_SCREEN_GEOMETRY=" + text) }
        XCTAssertEqual(XCUIDevice.shared.orientation, .landscapeRight)
        XCTAssertGreaterThan(image.size.width, image.size.height)
        XCTAssertEqual(Int(image.size.width * image.scale), 2868)
        XCTAssertEqual(Int(image.size.height * image.scale), 1320)
        let raw = XCTAttachment(data:screenshot.pngRepresentation,uniformTypeIdentifier:"public.png")
        raw.name = "iphone-" + stage + "-raw"
        raw.lifetime = .keepAlways
        add(raw)
        let display = XCTAttachment(screenshot:screenshot)
        display.name = "iphone-" + stage
        display.lifetime = .keepAlways
        add(display)
        let digest = SHA256.hash(data:screenshot.pngRepresentation).map { String(format:"%02x",$0) }.joined()
        print("STORE_SCREEN_RAW_SHA256=" + stage + ";sha256:" + digest)
    }
    func testScreenOnlyColdAndWarm() {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier:"tw.mars.crackveilvanguard")
        print("STORE_SCREEN_PHASE=activate-own-game")
        app.activate()
        XCUIDevice.shared.orientation = .landscapeRight
        Thread.sleep(forTimeInterval:90)
        capture("cold90")
        print("STORE_SCREEN_PHASE=terminate-own-game")
        app.terminate()
        print("STORE_SCREEN_PHASE=relaunch-own-game")
        app.launch()
        XCUIDevice.shared.orientation = .landscapeRight
        Thread.sleep(forTimeInterval:90)
        capture("warm90")
    }
}
''', encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Only a fresh independent runner directory is accepted")
    generate(sys.argv[1])
