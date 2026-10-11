"""Generate an unsigned, independent XCUITest host for the frozen Ashes UI.

This never writes inside the game project, evaluates JavaScript, or invokes a
game test API. The runner records genuine user-interface events only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import plistlib
from html.parser import HTMLParser
import xml.etree.ElementTree as ET

APP_ID = "tw.mars.ashesconvoy"
MANIFEST_SHA256 = "b778a8203bd0ff31b10baf5f63d92e3387ced346586dea2526c0254b2d7c8c53"
EXPECTED_CONTROLS = {
    "sortieBtn": ("button", "開始出勤"),
    "pauseBtn": ("button", "暫停"),
    "resumeBtn": ("button", "繼續遊戲"),
    "quitBtn": ("button", "結束本局並結算"),
    "garageBtn": ("button", "回車庫升級"),
    "touchSkillBtn": ("button", "補給技能"),
    "virtualJoystick": ("div", "虛擬搖桿"),
    "gameCanvas": ("canvas", "灰燼護航戰場"),
}
ACTION_SEQUENCE = (
    "launch", "garage-visible", "sortie-tap", "playing-visible",
    "aim-drag", "skill-tap", "pause-tap", "paused-visible",
    "resume-tap", "resumed-visible", "pause-again-tap", "quit-tap",
    "settlement-visible", "garage-tap", "garage-return-visible",
)


def add_object(objects, identity, isa, **values):
    if identity in objects:
        raise ValueError("Duplicate generated PBX object identity")
    objects[identity] = {"isa": isa, **values}
    return identity


def validate_object_references(objects):
    for value in objects.values():
        if value["isa"] == "PBXBuildFile":
            if objects.get(value.get("fileRef"), {}).get("isa") != "PBXFileReference":
                raise ValueError("Generated PBX build-file reference is not a file")
        elif value["isa"] == "PBXGroup":
            if any(objects.get(child, {}).get("isa") not in ("PBXGroup", "PBXFileReference") for child in value["children"]):
                raise ValueError("Generated PBX group contains a non-file/non-group reference")
        elif value["isa"] == "PBXSourcesBuildPhase":
            if any(objects.get(child, {}).get("isa") != "PBXBuildFile" for child in value["files"]):
                raise ValueError("Generated PBX source phase contains a non-build-file reference")


class Controls(HTMLParser):
    def __init__(self):
        super().__init__()
        self.controls = {}

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        identity = values.get("id")
        if identity in EXPECTED_CONTROLS:
            if identity in self.controls:
                raise ValueError("Duplicate required frozen UI control")
            self.controls[identity] = (tag, values.get("aria-label"))


def inspect_source(source):
    source = pathlib.Path(source).resolve()
    manifest = source / "bundle-manifest.json"
    if manifest.is_symlink() or not manifest.is_file():
        raise ValueError("Frozen manifest missing")
    raw = manifest.read_bytes()
    if hashlib.sha256(raw).hexdigest() != MANIFEST_SHA256:
        raise ValueError("Frozen manifest pin mismatch")
    metadata = json.loads(raw.decode("utf-8-sig"))
    if (metadata.get("projectId"), metadata.get("appId"), metadata.get("version"), metadata.get("build"), metadata.get("remoteServer")) != (
            "ashes-convoy", APP_ID, "1.0.1", 2, False):
        raise ValueError("Only the approved Ashes 1.0.1 build 2 payload is permitted")
    page = source / "web/index.html"
    if page.is_symlink() or not page.is_file():
        raise ValueError("Frozen HTML missing")
    parser = Controls()
    parser.feed(page.read_text(encoding="utf-8-sig"))
    if parser.controls != EXPECTED_CONTROLS:
        raise ValueError("Required frozen UI labels/tags are missing or changed")
    record = next((item for item in metadata["files"] if item["path"] == "index.html"), None)
    if not record or hashlib.sha256(page.read_bytes()).hexdigest() != record["sha256"]:
        raise ValueError("Frozen HTML payload hash mismatch")
    return {key: value[1] for key, value in parser.controls.items()}


SWIFT_TEST = r'''import XCTest
import UIKit
import CryptoKit

final class AshesCaptureUITests: XCTestCase {
    private let bundle = "tw.mars.ashesconvoy"
    private let labels: [String:String] = LABELS_JSON
    private var ordinal = 0
    private var origin = Date()
    private var lastScreenshotPointSize: CGSize = .zero

    private func event(_ action: String, _ facts: [String:Any] = [:]) {
        ordinal += 1
        var record = facts
        record["ordinal"] = ordinal
        record["action"] = action
        record["elapsedSeconds"] = Date().timeIntervalSince(origin)
        record["simulator"] = true
        if let raw = try? JSONSerialization.data(withJSONObject: record, options: [.sortedKeys]),
           let value = String(data: raw, encoding: .utf8) { print("ASHES_ACTION_JSON=" + value) }
    }

    private func visible(_ app: XCUIApplication, _ key: String, seconds: TimeInterval = 15) throws -> XCUIElement {
        guard let label = labels[key] else { throw NSError(domain: "AshesCapture", code: 1) }
        // Query the frozen aria-label, not arbitrary screen coordinates. The
        // hidden alternate start button is ignored: only hittable matches count.
        let query = app.descendants(matching: .any).matching(NSPredicate(format: "label == %@", label))
        let end = Date().addingTimeInterval(seconds)
        repeat {
            let matches = query.allElementsBoundByIndex.filter { $0.exists && $0.isHittable }
            if let element = matches.first, element.frame.width > 1, element.frame.height > 1,
               app.frame.contains(element.frame) { return element }
            Thread.sleep(forTimeInterval: 0.25)
        } while Date() < end
        XCTFail("FROZEN_VISIBLE_CONTROL_MISSING_" + key)
        throw NSError(domain: "AshesCapture", code: 2)
    }

    private func absent(_ app: XCUIApplication, _ key: String) -> Bool {
        let query = app.descendants(matching: .any).matching(NSPredicate(format: "label == %@", labels[key]!))
        return !query.allElementsBoundByIndex.contains { $0.exists && $0.isHittable }
    }

    private func checkpoint(_ name: String, app: XCUIApplication) {
        XCTAssertEqual(app.state, .runningForeground, "FROZEN_APP_NOT_FOREGROUND")
        let shot = XCUIScreen.main.screenshot()
        lastScreenshotPointSize = shot.image.size
        let attachment = XCTAttachment(screenshot: shot)
        attachment.name = "SIMULATOR-" + name
        attachment.lifetime = .keepAlways
        add(attachment)
        event(name, ["foreground": app.state == .runningForeground,
                     "screenshotSha256": SHA256.hash(data: shot.pngRepresentation).map { String(format: "%02x", $0) }.joined(),
                     "screenshotPointsWidth": shot.image.size.width,
                     "screenshotPointsHeight": shot.image.size.height])
        Thread.sleep(forTimeInterval: 1.5)
    }

    private func tap(_ app: XCUIApplication, _ key: String, action: String) throws {
        let element = try visible(app, key)
        element.tap()
        event(action, ["frozenControl": key, "label": labels[key]!, "inputMethod": "XCUITest.tap"])
    }

    private func dragBattlefield(_ app: XCUIApplication, pause: XCUIElement) throws {
        // The app frame already grounds every successfully found visible
        // control. Avoid querying the unreliable generic WebView AX subtree.
        let frame = app.frame
        let pauseFrame = pause.frame
        let size = lastScreenshotPointSize
        func number(_ value: CGFloat) -> Any { value.isFinite ? Double(value) as Any : NSNull() as Any }
        let geometry: [String:Any] = [
            "nativeAppFrame": [number(frame.minX), number(frame.minY), number(frame.width), number(frame.height)],
            "pauseFrame": [number(pauseFrame.minX), number(pauseFrame.minY), number(pauseFrame.width), number(pauseFrame.height)],
            "screenshotPointSize": [number(size.width), number(size.height)],
            "orientationRaw": XCUIDevice.shared.orientation.rawValue]
        if let raw = try? JSONSerialization.data(withJSONObject: geometry, options: [.sortedKeys]),
           let text = String(data: raw, encoding: .utf8) { print("ASHES_GEOMETRY_JSON=" + text) }
        guard app.state == .runningForeground, frame.width.isFinite, frame.height.isFinite,
              frame.width > 200, frame.width < 640, frame.height > 500, frame.height > frame.width,
              size.width > 0, size.height > size.width,
              abs(frame.width - size.width) < 1, abs(frame.height - size.height) < 1,
              pauseFrame.width > 0, pauseFrame.height > 0, frame.contains(pauseFrame) else {
            XCTFail("FROZEN_NATIVE_PLAYING_APP_VIEWPORT_UNVERIFIED")
            throw NSError(domain: "AshesCapture", code: 3)
        }
        // Pinned index.html: viewport initial-scale=1; body grid/center;
        // .app min(100vw,100svh*390/844) x min(100svh,100vw*844/390);
        // .battle-stage fills .app; #gameCanvas is absolute inset:0,100%/100%.
        // Native frame and actual screenshot sizes both prove portrait. These
        // source-derived expected bounds are not a claim to read DOM geometry.
        let width = min(frame.width, frame.height * 390.0 / 844.0)
        let height = min(frame.height, frame.width * 844.0 / 390.0)
        let stage = CGRect(x: frame.midX - width / 2, y: frame.midY - height / 2, width: width, height: height)
        let firstPoint = CGPoint(x: stage.minX + stage.width * 0.5, y: stage.minY + stage.height * 0.55)
        let lastPoint = CGPoint(x: stage.minX + stage.width * 0.72, y: stage.minY + stage.height * 0.60)
        let first = app.coordinate(withNormalizedOffset: CGVector(dx: (firstPoint.x - frame.minX) / frame.width, dy: (firstPoint.y - frame.minY) / frame.height))
        let last = app.coordinate(withNormalizedOffset: CGVector(dx: (lastPoint.x - frame.minX) / frame.width, dy: (lastPoint.y - frame.minY) / frame.height))
        let actualFirstPoint = first.screenPoint
        let actualLastPoint = last.screenPoint
        guard frame.contains(actualFirstPoint), frame.contains(actualLastPoint),
              stage.contains(actualFirstPoint), stage.contains(actualLastPoint),
              abs(actualFirstPoint.x - firstPoint.x) < 1, abs(actualFirstPoint.y - firstPoint.y) < 1,
              abs(actualLastPoint.x - lastPoint.x) < 1, abs(actualLastPoint.y - lastPoint.y) < 1,
              !pauseFrame.contains(actualFirstPoint), !pauseFrame.contains(actualLastPoint) else {
            XCTFail("FROZEN_BATTLEFIELD_INPUT_COORDINATE_CONTRACT_FAILED")
            throw NSError(domain: "AshesCapture", code: 4)
        }
        first.press(forDuration: 0.15, thenDragTo: last, withVelocity: .slow, thenHoldForDuration: 0.5)
        event("aim-drag", ["frozenControl": "gameCanvas", "label": labels["gameCanvas"]!,
            "inputMethod": "XCUITest.nativeAppViewportAnchoredPressAndDrag",
            "coordinateGrounding": "native-app-frame;actual-portrait-screenshot-size;frozen-centered-390-by-844-CSS;visible-playing-pause",
            "nativeAppFrame": [Double(frame.minX), Double(frame.minY), Double(frame.width), Double(frame.height)],
            "sourceDerivedExpectedCanvasFrame": [Double(stage.minX), Double(stage.minY), Double(stage.width), Double(stage.height)],
            "fromScreenPoint": [Double(actualFirstPoint.x), Double(actualFirstPoint.y)],
            "toScreenPoint": [Double(actualLastPoint.x), Double(actualLastPoint.y)],
            "canvasAccessibleLabelRequired": false, "actualDOMCanvasBoundsRead": false, "gameEffectVerified": false])
    }

    @MainActor func testContinuousLaunchSortieAndReturn() throws {
        continueAfterFailure = false
        origin = Date()
        // The test runner is independent. No launch arguments/environment,
        // JS evaluation, game state injection, test API or debug flag is used.
        XCUIDevice.shared.orientation = .portrait
        let app = XCUIApplication(bundleIdentifier: bundle)
        app.launch()
        event("launch", ["bundleIdentifier": bundle, "inputMethod": "XCUIApplication.launch"])
        _ = try visible(app, "sortieBtn", seconds: 90)
        checkpoint("garage-visible", app: app)
        try tap(app, "sortieBtn", action: "sortie-tap")
        let playingPause = try visible(app, "pauseBtn", seconds: 30)
        XCTAssertTrue(absent(app, "resumeBtn"), "PAUSED_BEFORE_GAMEPLAY")
        checkpoint("playing-visible", app: app)
        try dragBattlefield(app, pause: playingPause)
        try tap(app, "touchSkillBtn", action: "skill-tap")
        // Source action focuses an existing supply object; its effect may be
        // unavailable early in a run. This log proves input, not an effect.
        Thread.sleep(forTimeInterval: 3)
        try tap(app, "pauseBtn", action: "pause-tap")
        _ = try visible(app, "resumeBtn")
        _ = try visible(app, "quitBtn")
        checkpoint("paused-visible", app: app)
        try tap(app, "resumeBtn", action: "resume-tap")
        _ = try visible(app, "pauseBtn")
        XCTAssertTrue(absent(app, "resumeBtn"), "RESUME_PANEL_STILL_VISIBLE")
        checkpoint("resumed-visible", app: app)
        try tap(app, "pauseBtn", action: "pause-again-tap")
        _ = try visible(app, "quitBtn")
        try tap(app, "quitBtn", action: "quit-tap")
        _ = try visible(app, "garageBtn")
        XCTAssertTrue(absent(app, "resumeBtn"), "SETTLEMENT_DID_NOT_REPLACE_PAUSE")
        checkpoint("settlement-visible", app: app)
        try tap(app, "garageBtn", action: "garage-tap")
        _ = try visible(app, "sortieBtn")
        XCTAssertTrue(absent(app, "garageBtn"), "SETTLEMENT_STILL_VISIBLE_AFTER_RETURN")
        checkpoint("garage-return-visible", app: app)
        // Leave the genuine garage visible until the owned recorder finalizes.
    }
}
'''


def generate(root, source):
    root, source = pathlib.Path(root).resolve(), pathlib.Path(source).resolve()
    if root == source or root.is_relative_to(source):
        raise ValueError("Independent UI-test project must be outside the frozen game")
    labels = inspect_source(source)
    root.mkdir(parents=True, exist_ok=False)
    (root / "CaptureHost.swift").write_text("""import UIKit
@main final class CaptureApp: UIResponder, UIApplicationDelegate {
    var window: UIWindow?
    func application(_ application: UIApplication, didFinishLaunchingWithOptions options: [UIApplication.LaunchOptionsKey:Any]?) -> Bool {
        window = UIWindow(frame: UIScreen.main.bounds)
        window?.rootViewController = UIViewController()
        window?.backgroundColor = .black
        window?.makeKeyAndVisible()
        return true
    }
}
""", encoding="utf-8")
    # Swift dictionary syntax shares quoted literal syntax with this fixed JSON.
    literals = "[" + ", ".join(json.dumps(key) + ": " + json.dumps(value, ensure_ascii=False)
                              for key, value in sorted(labels.items())) + "]"
    (root / "AshesCaptureUITests.swift").write_text(SWIFT_TEST.replace("LABELS_JSON", literals), encoding="utf-8")
    objects = {}

    def ident(label):
        return hashlib.sha256(("ashes-simulator-" + label).encode()).hexdigest()[:24].upper()

    def obj(label, isa, **values):
        identity = ident(label)
        return add_object(objects, identity, isa, **values)

    host_source = obj("host-source", "PBXFileReference", lastKnownFileType="sourcecode.swift", path="CaptureHost.swift", sourceTree="<group>")
    tests_source = obj("test-source", "PBXFileReference", lastKnownFileType="sourcecode.swift", path="AshesCaptureUITests.swift", sourceTree="<group>")
    host_product = obj("host-product", "PBXFileReference", explicitFileType="wrapper.application", path="AshesCaptureHost.app", sourceTree="BUILT_PRODUCTS_DIR")
    tests_product = obj("test-product", "PBXFileReference", explicitFileType="wrapper.cfbundle", path="AshesCaptureUITests.xctest", sourceTree="BUILT_PRODUCTS_DIR")
    products = obj("products", "PBXGroup", children=[host_product, tests_product], name="Products", sourceTree="<group>")
    group = obj("main-group", "PBXGroup", children=[host_source, tests_source, products], sourceTree="<group>")
    common = {"SDKROOT": "iphonesimulator", "SUPPORTED_PLATFORMS": "iphonesimulator", "IPHONEOS_DEPLOYMENT_TARGET": "16.0", "SWIFT_VERSION": "5.0",
              "TARGETED_DEVICE_FAMILY": "1", "CODE_SIGNING_ALLOWED": "NO", "CODE_SIGNING_REQUIRED": "NO", "GENERATE_INFOPLIST_FILE": "YES"}

    def configs(name, values):
        items = [obj(name + "-" + mode, "XCBuildConfiguration", name=mode, buildSettings=dict(values)) for mode in ("Debug", "Release")]
        return obj(name + "-configs", "XCConfigurationList", buildConfigurations=items, defaultConfigurationIsVisible="0", defaultConfigurationName="Debug")

    project_config = configs("project", common)
    host_config = configs("host", dict(common, PRODUCT_BUNDLE_IDENTIFIER="tw.mars.simulatorcapture.ashes.host", PRODUCT_NAME="AshesCaptureHost",
        INFOPLIST_KEY_UILaunchScreen_Generation="YES", INFOPLIST_KEY_UISupportedInterfaceOrientations="UIInterfaceOrientationPortrait"))
    test_config = configs("tests", dict(common, PRODUCT_BUNDLE_IDENTIFIER="tw.mars.simulatorcapture.ashes.tests", PRODUCT_NAME="AshesCaptureUITests", TEST_TARGET_NAME="AshesCaptureHost"))

    def phase(label, file):
        ref = obj(label + "-build", "PBXBuildFile", fileRef=file)
        return obj(label + "-source-phase", "PBXSourcesBuildPhase", buildActionMask="2147483647", files=[ref], runOnlyForDeploymentPostprocessing="0")

    host_id, test_id = ident("host-target"), ident("test-target")
    proxy = obj("target-proxy", "PBXContainerItemProxy", containerPortal=ident("project"), proxyType="1", remoteGlobalIDString=host_id, remoteInfo="AshesCaptureHost")
    dependency = obj("test-host-dependency", "PBXTargetDependency", target=host_id, targetProxy=proxy)
    obj("host-target", "PBXNativeTarget", buildConfigurationList=host_config, buildPhases=[phase("host", host_source)],
        buildRules=[], dependencies=[], name="AshesCaptureHost", productName="AshesCaptureHost", productReference=host_product, productType="com.apple.product-type.application")
    obj("test-target", "PBXNativeTarget", buildConfigurationList=test_config, buildPhases=[phase("tests", tests_source)],
        buildRules=[], dependencies=[dependency], name="AshesCaptureUITests", productName="AshesCaptureUITests", productReference=tests_product, productType="com.apple.product-type.bundle.ui-testing")
    project_id = obj("project", "PBXProject", attributes={"LastUpgradeCheck": "2630", "TargetAttributes": {test_id: {"TestTargetID": host_id}}},
        buildConfigurationList=project_config, compatibilityVersion="Xcode 14.0", developmentRegion="en", hasScannedForEncodings="0",
        knownRegions=["en", "Base"], mainGroup=group, productRefGroup=products, projectDirPath="", projectRoot="", targets=[host_id, test_id])
    validate_object_references(objects)
    bundle = root / "AshesCapture.xcodeproj"
    bundle.mkdir()
    (bundle / "project.pbxproj").write_bytes(plistlib.dumps({"archiveVersion": "1", "classes": {}, "objectVersion": "56", "objects": objects, "rootObject": project_id}))
    scheme = ET.Element("Scheme", LastUpgradeVersion="2630", version="1.3")
    entries = ET.SubElement(ET.SubElement(scheme, "BuildAction", parallelizeBuildables="NO", buildImplicitDependencies="YES"), "BuildActionEntries")

    def reference(parent, identity, product, name):
        return ET.SubElement(parent, "BuildableReference", BuildableIdentifier="primary", BlueprintIdentifier=identity,
            BuildableName=product, BlueprintName=name, ReferencedContainer="container:AshesCapture.xcodeproj")

    for identity, product, name in [(host_id, "AshesCaptureHost.app", "AshesCaptureHost"), (test_id, "AshesCaptureUITests.xctest", "AshesCaptureUITests")]:
        entry = ET.SubElement(entries, "BuildActionEntry", buildForTesting="YES", buildForRunning="NO", buildForProfiling="NO", buildForArchiving="NO", buildForAnalyzing="YES")
        reference(entry, identity, product, name)
    test = ET.SubElement(scheme, "TestAction", buildConfiguration="Debug", selectedDebuggerIdentifier="Xcode.DebuggerFoundation.Debugger.LLDB",
        selectedLauncherIdentifier="Xcode.IDEFoundation.Launcher.LLDB", shouldUseLaunchSchemeArgsEnv="NO")
    testable = ET.SubElement(ET.SubElement(test, "Testables"), "TestableReference", skipped="NO", parallelizable="NO")
    reference(testable, test_id, "AshesCaptureUITests.xctest", "AshesCaptureUITests")
    schemes = bundle / "xcshareddata/xcschemes"
    schemes.mkdir(parents=True)
    ET.ElementTree(scheme).write(schemes / "AshesCapture.xcscheme", encoding="utf-8", xml_declaration=True)
    record = {"appId": APP_ID, "version": "1.0.1", "build": 2, "manifestSha256": MANIFEST_SHA256,
              "controls": labels, "actionSequence": ACTION_SEQUENCE, "independentTestHost": True,
              "inputCoordinateContract": {"anchor": "native-XCUIApplication-frame-matching-actual-screenshot-points", "portraitSourceCssAspect": [390, 844],
                  "portraitProvedByFrameAndScreenshotAspect": True, "nativeAppAndScreenshotSizeMustMatchWithinPoints": 1,
                  "nativeAppWidthMinimumExclusive": 200, "nativeAppWidthMaximumExclusive": 640,
                  "nativeAppHeightMinimumExclusive": 500,
                  "webViewAXTreeRequired": False, "orientationEnumEqualityRequired": False,
                  "pauseVisibleRequired": True, "resumeAbsentRequired": True, "playingCheckpointBeforeInput": True,
                  "canvasAXLabelRequired": False, "genericJoystickAXStepUsed": False, "actualDOMCanvasBoundsRead": False,
                  "fromNormalizedExpectedCanvas": [0.5, 0.55], "toNormalizedExpectedCanvas": [0.72, 0.60],
                  "gameInputEffectVerified": False},
              "sourceModified": False, "simulatorOnly": True, "physicalDeviceTested": False,
              "ApplePhysicalRequirementSatisfied": False}
    (root / "capture-contract.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return record


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=pathlib.Path)
    parser.add_argument("--app-source", required=True, type=pathlib.Path)
    args = parser.parse_args()
    generate(args.root, args.app_source)
