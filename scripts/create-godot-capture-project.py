"""Create an independent unsigned Simulator UI-test runner, never a game target."""
import hashlib
import pathlib
import plistlib
import sys
import xml.etree.ElementTree as ET

PROJECTS = {"crackveil-vanguard": ("tw.mars.crackveilvanguard", "開始出擊"),
            "seven-district-reckoning": ("tw.mars.sevendistrictreckoning", "開始新遊戲")}


def generate(root, project, kind):
    if project not in PROJECTS or kind not in ("iphone", "ipad"):
        raise ValueError("Explicit approved game/device required")
    root = pathlib.Path(root)
    root.mkdir(parents=True, exist_ok=False)
    app_id, label = PROJECTS[project]
    (root / "CaptureHost.swift").write_text('''import UIKit
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
''', encoding="utf-8")
    swift = '''import XCTest
import Vision
import UIKit
final class CaptureUITests: XCTestCase {
    private let bundle = "APP_ID"
    private let startLabel = "START_LABEL"
    private let kind = "DEVICE_KIND"
    private func capture(_ name: String) {
        let attachment = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        attachment.name = kind + "-" + name
        attachment.lifetime = .keepAlways
        add(attachment)
    }
    private func startPoint(_ screen: XCUIScreenshot) -> CGVector? {
        guard let image = screen.image.cgImage else { return nil }
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        request.recognitionLanguages = ["zh-Hant", "en-US"]
        request.usesLanguageCorrection = false
        do {
            try VNImageRequestHandler(cgImage: image, options: [:]).perform([request])
            for observation in request.results ?? [] {
                guard let text = observation.topCandidates(1).first else { continue }
                let value = text.string.filter { !$0.isWhitespace }
                if value == startLabel && text.confidence >= 0.3 {
                    return CGVector(dx: observation.boundingBox.midX, dy: 1 - observation.boundingBox.midY)
                }
            }
        } catch { print("CAPTURE_OCR_UNAVAILABLE") }
        return nil
    }
    @MainActor func testNativeMenuAndStart() throws {
        print("CAPTURE_TEST_METHOD_ENTERED=" + kind)
        continueAfterFailure = false
        // The original game supports LandscapeLeft on phone, Right on iPad.
        // Device orientation and interface orientation are opposite here.
        XCUIDevice.shared.orientation = kind == "iphone" ? .landscapeRight : .landscapeLeft
        let app = XCUIApplication(bundleIdentifier: bundle)
        app.activate()
        Thread.sleep(forTimeInterval: 90)
        capture("menu90")
        print("CAPTURE_MENU90_FOREGROUND=" + String(app.state == .runningForeground))
        XCTAssertEqual(app.state, .runningForeground, "OWN_GAME_NOT_FOREGROUND")
        let button = app.buttons[startLabel]
        var method = "accessibility-button"
        if button.exists && button.isHittable {
            button.tap()
        } else if let point = startPoint(XCUIScreen.main.screenshot()) {
            method = "visible-label-vision"
            app.coordinate(withNormalizedOffset: point).tap()
        } else {
            XCTFail("OWN_GAME_START_LABEL_NOT_VISIBLE_AFTER_90_SECONDS")
            return
        }
        Thread.sleep(forTimeInterval: 20)
        capture("after-start")
        XCTAssertEqual(app.state, .runningForeground, "OWN_GAME_EXITED_AFTER_START")
        print("CAPTURE_START_INPUT_METHOD=" + method)
        app.terminate()
        app.launch()
        Thread.sleep(forTimeInterval: 90)
        capture("relaunch90")
        XCTAssertEqual(app.state, .runningForeground, "OWN_GAME_NOT_FOREGROUND_AFTER_RELAUNCH")
    }
}
'''
    swift = swift.replace("APP_ID", app_id).replace("START_LABEL", label).replace("DEVICE_KIND", kind)
    (root / "CaptureUITests.swift").write_text(swift, encoding="utf-8")
    objects = {}

    def identifier(name):
        return hashlib.sha256(name.encode()).hexdigest()[:24].upper()

    def obj(label, isa, **values):
        key = identifier(label)
        objects[key] = {"isa": isa, **values}
        return key

    host_source = obj("host-source", "PBXFileReference", lastKnownFileType="sourcecode.swift", path="CaptureHost.swift", sourceTree="<group>")
    tests_source = obj("test-source", "PBXFileReference", lastKnownFileType="sourcecode.swift", path="CaptureUITests.swift", sourceTree="<group>")
    host_product = obj("host-product", "PBXFileReference", explicitFileType="wrapper.application", path="CaptureHost.app", sourceTree="BUILT_PRODUCTS_DIR")
    tests_product = obj("test-product", "PBXFileReference", explicitFileType="wrapper.cfbundle", path="CaptureUITests.xctest", sourceTree="BUILT_PRODUCTS_DIR")
    products = obj("products", "PBXGroup", children=[host_product, tests_product], name="Products", sourceTree="<group>")
    group = obj("main-group", "PBXGroup", children=[host_source, tests_source, products], sourceTree="<group>")
    common = {"SDKROOT": "iphonesimulator", "IPHONEOS_DEPLOYMENT_TARGET": "16.0", "SWIFT_VERSION": "5.0",
              "TARGETED_DEVICE_FAMILY": "1,2", "CODE_SIGNING_ALLOWED": "NO", "GENERATE_INFOPLIST_FILE": "YES"}

    def configurations(name, settings):
        configurations = []
        for mode in ("Debug", "Release"):
            configurations.append(obj(name + "-" + mode, "XCBuildConfiguration", name=mode, buildSettings=dict(settings)))
        return obj(name + "-config-list", "XCConfigurationList", buildConfigurations=configurations,
                   defaultConfigurationIsVisible="0", defaultConfigurationName="Debug")

    project_config = configurations("project", common)
    host_config = configurations("host", dict(common, PRODUCT_BUNDLE_IDENTIFIER="tw.mars.capture.host", PRODUCT_NAME="CaptureHost",
        INFOPLIST_KEY_UILaunchScreen_Generation="YES", INFOPLIST_KEY_UISupportedInterfaceOrientations="UIInterfaceOrientationPortrait UIInterfaceOrientationLandscapeLeft UIInterfaceOrientationLandscapeRight"))
    test_config = configurations("tests", dict(common, PRODUCT_BUNDLE_IDENTIFIER="tw.mars.capture.tests", PRODUCT_NAME="CaptureUITests", TEST_TARGET_NAME="CaptureHost"))

    def source_phase(name, file):
        build_file = obj(name + "-build-file", "PBXBuildFile", fileRef=file)
        return obj(name + "-source-phase", "PBXSourcesBuildPhase", buildActionMask="2147483647", files=[build_file], runOnlyForDeploymentPostprocessing="0")

    host_id = identifier("host-target")
    test_id = identifier("test-target")
    proxy = obj("target-proxy", "PBXContainerItemProxy", containerPortal=identifier("project"), proxyType="1", remoteGlobalIDString=host_id, remoteInfo="CaptureHost")
    dependency = obj("test-host-dependency", "PBXTargetDependency", target=host_id, targetProxy=proxy)
    obj("host-target", "PBXNativeTarget", buildConfigurationList=host_config, buildPhases=[source_phase("host", host_source)],
        buildRules=[], dependencies=[], name="CaptureHost", productName="CaptureHost", productReference=host_product, productType="com.apple.product-type.application")
    obj("test-target", "PBXNativeTarget", buildConfigurationList=test_config, buildPhases=[source_phase("test", tests_source)],
        buildRules=[], dependencies=[dependency], name="CaptureUITests", productName="CaptureUITests", productReference=tests_product, productType="com.apple.product-type.bundle.ui-testing")
    project_id = obj("project", "PBXProject", attributes={"LastUpgradeCheck": "1600", "TargetAttributes": {test_id: {"TestTargetID": host_id}}},
        buildConfigurationList=project_config, compatibilityVersion="Xcode 14.0", developmentRegion="en", hasScannedForEncodings="0",
        knownRegions=["en", "Base"], mainGroup=group, productRefGroup=products, projectDirPath="", projectRoot="", targets=[host_id, test_id])
    bundle = root / "Capture.xcodeproj"
    bundle.mkdir()
    (bundle / "project.pbxproj").write_bytes(plistlib.dumps({"archiveVersion": "1", "classes": {}, "objectVersion": "56", "objects": objects, "rootObject": project_id}))
    scheme = ET.Element("Scheme", LastUpgradeVersion="1600", version="1.3")
    build = ET.SubElement(scheme, "BuildAction", parallelizeBuildables="NO", buildImplicitDependencies="YES")
    entries = ET.SubElement(build, "BuildActionEntries")

    def reference(parent, key, product, name):
        return ET.SubElement(parent, "BuildableReference", BuildableIdentifier="primary", BlueprintIdentifier=key,
                             BuildableName=product, BlueprintName=name, ReferencedContainer="container:Capture.xcodeproj")

    for key, product, name in [(host_id, "CaptureHost.app", "CaptureHost"), (test_id, "CaptureUITests.xctest", "CaptureUITests")]:
        entry = ET.SubElement(entries, "BuildActionEntry", buildForTesting="YES", buildForRunning="NO", buildForProfiling="NO", buildForArchiving="NO", buildForAnalyzing="YES")
        reference(entry, key, product, name)
    test = ET.SubElement(scheme, "TestAction", buildConfiguration="Debug", selectedDebuggerIdentifier="Xcode.DebuggerFoundation.Debugger.LLDB",
                         selectedLauncherIdentifier="Xcode.IDEFoundation.Launcher.LLDB", shouldUseLaunchSchemeArgsEnv="YES")
    testables = ET.SubElement(test, "Testables")
    testable = ET.SubElement(testables, "TestableReference", skipped="NO")
    reference(testable, test_id, "CaptureUITests.xctest", "CaptureUITests")
    schemes = bundle / "xcshareddata/xcschemes"
    schemes.mkdir(parents=True)
    ET.ElementTree(scheme).write(schemes / "Capture.xcscheme", encoding="utf-8", xml_declaration=True)


if __name__ == "__main__":
    generate(sys.argv[1], sys.argv[2], sys.argv[3])
