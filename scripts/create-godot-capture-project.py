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
import ImageIO
import CryptoKit
final class CaptureUITests: XCTestCase {
    private let bundle = "APP_ID"
    private let startLabel = "START_LABEL"
    private let kind = "DEVICE_KIND"
    private func capture(_ name: String, app: XCUIApplication) {
        print("CAPTURE_PRE_QUERY=" + kind + "-" + name + ";query=app-state")
        print("CAPTURE_BEFORE_SCREENSHOT=" + kind + "-" + name + ";foreground=" + String(app.state == .runningForeground))
        print("CAPTURE_PRE_QUERY=" + kind + "-" + name + ";query=app-frame")
        let frame = app.frame
        print("CAPTURE_PRE_FRAME=" + kind + "-" + name + ";x:" + String(Double(frame.minX)) + ";y:" + String(Double(frame.minY)) + ";w:" + String(Double(frame.width)) + ";h:" + String(Double(frame.height)) + ";deviceOrientation:" + String(XCUIDevice.shared.orientation.rawValue))
        print("CAPTURE_PRE_QUERY=" + kind + "-" + name + ";query=screen-screenshot")
        let screen = XCUIScreen.main.screenshot()
        let image = screen.image
        let source = CGImageSourceCreateWithData(screen.pngRepresentation as CFData, nil)
        let properties = source.flatMap { CGImageSourceCopyPropertiesAtIndex($0, 0, nil) as? [String:Any] }
        let geometry: [String:Any] = ["stage":kind + "-" + name,"deviceOrientation":XCUIDevice.shared.orientation.rawValue,
            "imageOrientation":image.imageOrientation.rawValue,"imageWidth":image.size.width,"imageHeight":image.size.height,"imageScale":image.scale,
            "cgWidth":image.cgImage?.width ?? 0,"cgHeight":image.cgImage?.height ?? 0,
            "pngOrientation":properties?[kCGImagePropertyOrientation as String] ?? 0,
            "appX":app.frame.origin.x,"appY":app.frame.origin.y,"appWidth":app.frame.width,"appHeight":app.frame.height]
        if let data = try? JSONSerialization.data(withJSONObject: geometry, options: [.sortedKeys]), let text = String(data:data,encoding:.utf8) { print("CAPTURE_GEOMETRY=" + text) }
        let attachment = XCTAttachment(screenshot: screen)
        attachment.name = kind + "-" + name
        attachment.lifetime = .keepAlways
        add(attachment)
        let raw = XCTAttachment(data: screen.pngRepresentation, uniformTypeIdentifier: "public.png")
        raw.name = kind + "-" + name + "-raw"
        raw.lifetime = .keepAlways
        add(raw)
        let digest = SHA256.hash(data: screen.pngRepresentation).map { String(format:"%02x",$0) }.joined()
        print("CAPTURE_RAW_SHA256=" + kind + "-" + name + ";sha256:" + digest)
    }
    private func exif(_ orientation: UIImage.Orientation) -> CGImagePropertyOrientation? {
        switch orientation {
        case .up: return .up
        case .upMirrored: return .upMirrored
        case .down: return .down
        case .downMirrored: return .downMirrored
        case .left: return .left
        case .leftMirrored: return .leftMirrored
        case .right: return .right
        case .rightMirrored: return .rightMirrored
        @unknown default: return nil
        }
    }
    private func screenPoint(_ point: CGPoint, frame: CGRect) -> CGPoint? {
        guard frame.width > 0, frame.height > 0, point.x >= 0, point.x <= 1, point.y >= 0, point.y <= 1 else { return nil }
        return CGPoint(x: frame.minX + point.x * frame.width, y: frame.minY + (1 - point.y) * frame.height)
    }
    func testCoordinateContract() {
        let pairs: [(UIImage.Orientation,UInt32)] = [(.up,1),(.upMirrored,2),(.down,3),(.downMirrored,4),(.leftMirrored,5),(.right,6),(.rightMirrored,7),(.left,8)]
        for (image,expected) in pairs { XCTAssertEqual(exif(image)?.rawValue, expected) }
        let offsetPoint = screenPoint(CGPoint(x:0.25,y:0.8),frame:CGRect(x:20,y:30,width:1000,height:600))
        XCTAssertEqual(offsetPoint?.x ?? -1,270,accuracy:0.0000001)
        XCTAssertEqual(offsetPoint?.y ?? -1,150,accuracy:0.0000001)
        XCTAssertNil(screenPoint(CGPoint(x:-0.1,y:0.8),frame:CGRect(x:20,y:30,width:1000,height:600)))
        XCTAssertNil(screenPoint(CGPoint(x:0.1,y:0.8),frame:.zero))
    }
    private func startPoint(_ app: XCUIApplication) -> CGVector? {
        print("CAPTURE_PRE_QUERY=" + kind + ";query=ocr-app-frame")
        let frame = app.frame
        print("CAPTURE_PRE_QUERY=" + kind + ";query=ocr-app-screenshot")
        let screen = app.screenshot()
        guard let image = screen.image.cgImage else { return nil }
        guard let orientation = exif(screen.image.imageOrientation) else { print("CAPTURE_OCR_UNKNOWN_ORIENTATION"); return nil }
        let quarterTurn = [UIImage.Orientation.left,.leftMirrored,.right,.rightMirrored].contains(screen.image.imageOrientation)
        let width = CGFloat(quarterTurn ? image.height : image.width)
        let height = CGFloat(quarterTurn ? image.width : image.height)
        guard frame.width > 0, frame.height > 0, abs(width / height - frame.width / frame.height) < 0.01 else {
            print("CAPTURE_OCR_AXIS_SCOPE_UNKNOWN;cgW:" + String(image.width) + ";cgH:" + String(image.height) + ";exif:" + String(orientation.rawValue) + ";frameW:" + String(Double(frame.width)) + ";frameH:" + String(Double(frame.height)))
            return nil
        }
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        request.recognitionLanguages = ["zh-Hant", "en-US"]
        request.usesLanguageCorrection = false
        do {
            try VNImageRequestHandler(cgImage: image, orientation: orientation, options: [:]).perform([request])
            for observation in request.results ?? [] {
                guard let text = observation.topCandidates(1).first else { continue }
                let value = text.string.filter { !$0.isWhitespace }
                if value == startLabel && text.confidence >= 0.3 {
                    let bbox = observation.boundingBox
                    guard let point = screenPoint(CGPoint(x:bbox.midX,y:bbox.midY),frame:frame), frame.contains(point), app.frame == frame else { print("CAPTURE_OCR_FRAME_CHANGED_OR_POINT_OUTSIDE"); return nil }
                    let normalized = CGVector(dx:(point.x-frame.minX)/frame.width,dy:(point.y-frame.minY)/frame.height)
                    let coordinate = app.coordinate(withNormalizedOffset: normalized)
                    guard abs(coordinate.screenPoint.x-point.x) < 1, abs(coordinate.screenPoint.y-point.y) < 1 else { print("CAPTURE_OCR_SCREEN_POINT_MISMATCH"); return nil }
                    print("CAPTURE_OCR_CONTRACT=scope:app;exif:" + String(orientation.rawValue) + ";confidence:" + String(text.confidence) + ";bbox:" + String(describing:bbox) + ";frame:" + String(describing:frame) + ";screenPoint:" + String(describing:point))
                    return normalized
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
        capture("menu90", app: app)
        print("CAPTURE_MENU90_FOREGROUND=" + String(app.state == .runningForeground))
        XCTAssertEqual(app.state, .runningForeground, "OWN_GAME_NOT_FOREGROUND")
        let button = app.buttons[startLabel]
        var method = "accessibility-button"
        if button.exists && button.isHittable {
            button.tap()
        } else if let point = startPoint(app) {
            method = "visible-label-vision"
            print("CAPTURE_OCR_POINT=x:" + String(Double(point.dx)) + ";y:" + String(Double(point.dy)))
            app.coordinate(withNormalizedOffset: point).tap()
        } else {
            XCTFail("OWN_GAME_START_LABEL_NOT_VISIBLE_AFTER_90_SECONDS")
            return
        }
        Thread.sleep(forTimeInterval: 20)
        capture("after-start", app: app)
        XCTAssertEqual(app.state, .runningForeground, "OWN_GAME_EXITED_AFTER_START")
        print("CAPTURE_START_INPUT_METHOD=" + method)
        app.terminate()
        app.launch()
        Thread.sleep(forTimeInterval: 90)
        capture("relaunch90", app: app)
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
