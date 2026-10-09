import re
"""Create an independent unsigned Simulator UI-test runner, never a game target."""
import hashlib
import pathlib
import plistlib
import sys
import xml.etree.ElementTree as ET

PROJECTS = {"crackveil-vanguard": ("tw.mars.crackveilvanguard", "開始出擊")}


def generate(root, project, kind, nonce):
    if not re.fullmatch(r"[0-9a-f]{32}", nonce):
        raise ValueError("Exact current Runner nonce required")
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
import Darwin
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
        let frame = CGRect(origin: .zero, size: XCUIScreen.main.screenshot().image.size)
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
            "appX":frame.origin.x,"appY":frame.origin.y,"appWidth":frame.width,"appHeight":frame.height]
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
    private func nativeScreenPoint(_ point: CGPoint, size: CGSize, orientation: CGImagePropertyOrientation) -> CGPoint? {
        guard size.width > 0, size.height > 0, point.x >= 0, point.y >= 0, point.x <= size.width, point.y <= size.height else { return nil }
        // Inverse EXIF transform: XCTest screenPoint uses natural screen axes.
        // Run 37628497486 observed (y,W-x) on Phone and (H-y,x) on iPad.
        switch orientation {
        case .up: return point
        case .upMirrored: return CGPoint(x:size.width-point.x,y:point.y)
        case .down: return CGPoint(x:size.width-point.x,y:size.height-point.y)
        case .downMirrored: return CGPoint(x:point.x,y:size.height-point.y)
        case .leftMirrored: return CGPoint(x:point.y,y:point.x)
        case .right: return CGPoint(x:point.y,y:size.width-point.x)
        case .rightMirrored: return CGPoint(x:size.height-point.y,y:size.width-point.x)
        case .left: return CGPoint(x:size.height-point.y,y:point.x)
        @unknown default: return nil
        }
    }
    private func fullScreenGeometry(_ frame: CGRect, size: CGSize, pixels: CGSize, scale: CGFloat, orientation: CGImagePropertyOrientation) -> Bool {
        guard frame.minX == 0, frame.minY == 0, frame.width > 0, frame.height > 0, scale > 0,
            abs(size.width-frame.width) < 0.01, abs(size.height-frame.height) < 0.01 else { return false }
        let quarterTurn = [CGImagePropertyOrientation.left,.leftMirrored,.right,.rightMirrored].contains(orientation)
        let width = quarterTurn ? pixels.height : pixels.width
        let height = quarterTurn ? pixels.width : pixels.height
        return abs(width-size.width*scale) < 1 && abs(height-size.height*scale) < 1
    }
    func testCoordinateContract() {
        let pairs: [(UIImage.Orientation,UInt32)] = [(.up,1),(.upMirrored,2),(.down,3),(.downMirrored,4),(.leftMirrored,5),(.right,6),(.rightMirrored,7),(.left,8)]
        for (image,expected) in pairs { XCTAssertEqual(exif(image)?.rawValue, expected) }
        let offsetPoint = screenPoint(CGPoint(x:0.25,y:0.8),frame:CGRect(x:20,y:30,width:1000,height:600))
        XCTAssertEqual(offsetPoint?.x ?? -1,270,accuracy:0.0000001)
        XCTAssertEqual(offsetPoint?.y ?? -1,150,accuracy:0.0000001)
        XCTAssertNil(screenPoint(CGPoint(x:-0.1,y:0.8),frame:CGRect(x:20,y:30,width:1000,height:600)))
        XCTAssertNil(screenPoint(CGPoint(x:0.1,y:0.8),frame:.zero))
        let nativeCases: [(CGImagePropertyOrientation,CGPoint)] = [(.up,CGPoint(x:200,y:100)),(.upMirrored,CGPoint(x:800,y:100)),(.down,CGPoint(x:800,y:500)),(.downMirrored,CGPoint(x:200,y:500)),(.leftMirrored,CGPoint(x:100,y:200)),(.right,CGPoint(x:100,y:800)),(.rightMirrored,CGPoint(x:500,y:800)),(.left,CGPoint(x:500,y:200))]
        for (orientation,expected) in nativeCases { XCTAssertEqual(nativeScreenPoint(CGPoint(x:200,y:100),size:CGSize(width:1000,height:600),orientation:orientation),expected) }
        XCTAssertNil(nativeScreenPoint(CGPoint(x:1001,y:100),size:CGSize(width:1000,height:600),orientation:.right))
        // Actual run 37616329788: screen backing pixels are portrait with
        // EXIF6, while UIImage and app frame are correctly landscape.
        let phoneFrame = CGRect(x:0,y:0,width:956,height:440)
        XCTAssertTrue(fullScreenGeometry(phoneFrame,size:phoneFrame.size,pixels:CGSize(width:1320,height:2868),scale:3,orientation:.right))
        XCTAssertFalse(fullScreenGeometry(phoneFrame,size:phoneFrame.size,pixels:CGSize(width:2868,height:1320),scale:3,orientation:.right))
        XCTAssertFalse(fullScreenGeometry(CGRect(x:20,y:0,width:956,height:440),size:phoneFrame.size,pixels:CGSize(width:1320,height:2868),scale:3,orientation:.right))
    }
    private let mirrorName = "crack-native-qa-mirror.json"
    private let runnerNonce = "LIFECYCLE_NONCE"
    private func bootstrapRunner() throws {
        let docs = try XCTUnwrap(FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first)
        let file = docs.appendingPathComponent(mirrorName).resolvingSymlinksInPath().standardizedFileURL
        let digest = SHA256.hash(data:Data(file.path.utf8)).map{String(format:"%02x",$0)}.joined()
        let data:[String:Any] = ["protocol":"CRACK_RUNNER_V1","kind":kind,"nonce":runnerNonce,"runnerBundleId":try XCTUnwrap(Bundle.main.bundleIdentifier),"mirrorPathSha256":digest]
        print("CRACK_QA_RUNNER_BOOTSTRAP "+String(data:try JSONSerialization.data(withJSONObject:data,options:[.sortedKeys]),encoding:.utf8)!)
        fflush(stdout)
    }
    private func waitForControlMirror(until:Date) throws {
        let docs = try XCTUnwrap(FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first)
        let file = docs.appendingPathComponent(mirrorName)
        while Date()<until && !FileManager.default.fileExists(atPath:file.path) { Thread.sleep(forTimeInterval:0.1) }
        XCTAssertTrue(FileManager.default.fileExists(atPath:file.path),"CURRENT_RUNNER_MIRROR_MISSING")
        _ = try controlEnvelope() // metadata/nonce only; no fabricated sample or last-sample assertion here.
    }
    private func controlEnvelope() throws -> [String:Any] {
        let documents = try XCTUnwrap(FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first)
        let file = documents.appendingPathComponent(mirrorName)
        let bytes = try Data(contentsOf:file)
        XCTAssertLessThan(bytes.count, 512 * 1024, "OWN_RUNNER_MIRROR_BOUND")
        let value = try XCTUnwrap(JSONSerialization.jsonObject(with:bytes) as? [String:Any])
        XCTAssertEqual(value["appId"] as? String,bundle)
        XCTAssertEqual(value["kind"] as? String,kind)
        XCTAssertEqual(value["nonce"] as? String,runnerNonce)
        XCTAssertEqual((value["build"] as? NSNumber)?.intValue,2)
        XCTAssertEqual(value["version"] as? String,"1.0.0")
        let mirrorDigest = SHA256.hash(data:Data(file.resolvingSymlinksInPath().standardizedFileURL.path.utf8)).map{String(format:"%02x",$0)}.joined()
        XCTAssertEqual(value["mirrorPathSha256"] as? String,mirrorDigest,"ACTUAL_OWN_RUNNER_DOCUMENTS_REQUIRED")
        return value
    }
    private func envelope() throws -> [String:Any] {
        let value = try controlEnvelope()
        XCTAssertEqual(value["sourceReady"] as? Bool,true,"REAL_GAME_SAMPLE_REQUIRED")
        let received = try XCTUnwrap(value["receivedAtMs"] as? Double)
        XCTAssertLessThan(Date().timeIntervalSince1970*1000-received,2000,"FRESH_PASSIVE_SOURCE_REQUIRED")
        return value
    }
    private func latest() throws -> ([String:Any],Int) {
        let e = try envelope()
        let rows = try XCTUnwrap(e["samples"] as? [[String:Any]])
        return (try XCTUnwrap(rows.last),try XCTUnwrap(e["epoch"] as? Int))
    }
    private func flag(_ s:[String:Any],_ k:String)->Bool { (s[k] as? Bool)==true }
    private func number(_ s:[String:Any],_ k:String)throws->Double { try XCTUnwrap(s[k] as? Double) }
    private var actionDeadline = Date.distantPast
    private func rawActual() throws -> ([String:Any],Int,[String:Any]) {
        let e=try controlEnvelope(),rows=try XCTUnwrap(e["samples"] as? [[String:Any]])
        return (try XCTUnwrap(rows.last),try XCTUnwrap(e["epoch"] as? Int),e)
    }
    private func freshAfter(_ baseline:([String:Any],Int,[String:Any]),_ context:[String:Any]?,_ action:String,_ phase:String) throws -> ([String:Any],Int,Double) {
        let until=min(Date().addingTimeInterval(2),actionDeadline),baseSeq=try number(baseline.0,"sequence"),baseTick=try number(baseline.0,"ticks_ms")
        var lastSeq=baseSeq,lastAge=Double.infinity
        while Date()<until {
            let current=try rawActual(),seq=try number(current.0,"sequence"),tick=try number(current.0,"ticks_ms")
            lastSeq=seq;lastAge=Date().timeIntervalSince1970*1000-(try number(current.2,"receivedAtMs"))
            guard current.1==baseline.1 else { throw NSError(domain:"FRESH_SAMPLE_EPOCH_CHANGED",code:1) }
            if let reference=context {
                guard try number(current.0,"scene_instance")==number(reference,"scene_instance"),String(describing:current.0["viewport"]!)==String(describing:reference["viewport"]!) else { throw NSError(domain:"POINT_SCENE_VIEWPORT_CHANGED",code:1) }
                if action=="move" { guard String(describing:current.0["joy_rect"]!)==String(describing:reference["joy_rect"]!) else { throw NSError(domain:"POINT_JOYSTICK_RECT_CHANGED",code:1) } }
            }
            if (current.2["sourceReady"] as? Bool)==true && seq>baseSeq && tick>baseTick && lastAge>=0 && lastAge<2000 { return (current.0,current.1,lastAge) }
            Thread.sleep(forTimeInterval:0.05)
        }
        let d:[String:Any]=["action":action,"phase":phase,"baselineSequence":baseSeq,"baselineTicks":baseTick,"lastSequence":lastSeq,"lastAgeMs":lastAge.isFinite ? lastAge : -1]
        print("CRACK_QA_FRESH_HOLD "+String(data:try JSONSerialization.data(withJSONObject:d,options:[.sortedKeys]),encoding:.utf8)!);fflush(stdout)
        throw NSError(domain:"ACTUAL_NEW_SAMPLE_NOT_FRESH",code:1)
    }
    private func marker(_ action:String,_ phase:String,_ context:[String:Any]?=nil,_ baseline:([String:Any],Int,[String:Any])?=nil)throws {
        let b:([String:Any],Int,[String:Any])
        if let provided=baseline { b=provided } else { b=try rawActual() }
        let accepted=try freshAfter(b,context,action,phase)
        let sample=accepted.0,e=accepted.1,age=accepted.2
        let value:[String:Any] = ["kind":kind,"action":action,"phase":phase,"epoch":e,"sequence":try number(sample,"sequence"),"ticks_ms":try number(sample,"ticks_ms"),"baselineSequence":try number(b.0,"sequence"),"baselineTicks":try number(b.0,"ticks_ms"),"freshAgeMs":age]
        print("CRACK_QA_EVENT "+String(data:try JSONSerialization.data(withJSONObject:value,options:[.sortedKeys]),encoding:.utf8)!);fflush(stdout)
    }
    private func visiblePoint(_ app:XCUIApplication,_ label:String)throws->CGVector? {
        XCTAssertEqual(app.state,.runningForeground,"OWN_GAME_NOT_FOREGROUND")
        let screen=XCUIScreen.main.screenshot()
        let frame=CGRect(origin:.zero,size:screen.image.size)
        guard let cg=screen.image.cgImage,let o=exif(screen.image.imageOrientation),
            let properties=CGImageSourceCreateWithData(screen.pngRepresentation as CFData,nil).flatMap({CGImageSourceCopyPropertiesAtIndex($0,0,nil) as? [String:Any]}),
            (properties[kCGImagePropertyOrientation as String] as? NSNumber)?.uint32Value==o.rawValue,
            fullScreenGeometry(frame,size:screen.image.size,pixels:CGSize(width:CGFloat(cg.width),height:CGFloat(cg.height)),scale:screen.image.scale,orientation:o) else { XCTFail("FRESH_NATIVE_GEOMETRY_UNPROVEN");return nil }
        let request=VNRecognizeTextRequest();request.recognitionLevel = .accurate
        request.recognitionLanguages=["zh-Hant","en-US"];request.usesLanguageCorrection=false
        try VNImageRequestHandler(cgImage:cg,orientation:o,options:[:]).perform([request])
        let rows=(request.results ?? []).filter { row in guard let t=row.topCandidates(1).first else{return false};return t.string.filter{!$0.isWhitespace}==label && t.confidence>=0.9 }
        if rows.isEmpty{return nil};XCTAssertEqual(rows.count,1,"UNIQUE_VISIBLE_LABEL_REQUIRED")
        guard rows.count==1,let point=screenPoint(CGPoint(x:rows[0].boundingBox.midX,y:rows[0].boundingBox.midY),frame:frame),let expected=nativeScreenPoint(point,size:frame.size,orientation:o) else{return nil}
        let n=CGVector(dx:point.x/frame.width,dy:point.y/frame.height)
        let actual=app.coordinate(withNormalizedOffset:n).screenPoint
        XCTAssertLessThan(abs(actual.x-expected.x),1,"FRESH_NATIVE_X_MAPPING_REQUIRED")
        XCTAssertLessThan(abs(actual.y-expected.y),1,"FRESH_NATIVE_Y_MAPPING_REQUIRED")
        return n
    }
    private func tapLabel(_ app:XCUIApplication,_ label:String,_ action:String)throws {
        let baseline=try rawActual() // context only, never accepted as a fresh sample
        let point=try XCTUnwrap(visiblePoint(app,label),"VISIBLE_LABEL_REQUIRED_"+label)
        try marker(action,"begin",baseline.0,baseline)
        app.coordinate(withNormalizedOffset:point).tap()
        Thread.sleep(forTimeInterval:0.4)
        try marker(action,"end")
    }
    private func joyPoint(_ app:XCUIApplication,_ sample:[String:Any],_ fx:CGFloat)throws->XCUICoordinate {
        let rect=try XCTUnwrap(sample["joy_rect"] as? [Double]),v=try XCTUnwrap(sample["viewport"] as? [Double])
        XCTAssertEqual(rect.count,4);XCTAssertEqual(v.count,2)
        guard rect.count==4,v.count==2,rect[2]>0,rect[3]>0,v[0]>0,v[1]>0 else {throw NSError(domain:"PASSIVE_JOYSTICK_RECT_MISSING",code:1)}
        let screen=XCUIScreen.main.screenshot(),frame=CGRect(origin:.zero,size:screen.image.size)
        let o=try XCTUnwrap(exif(screen.image.imageOrientation)),cg=try XCTUnwrap(screen.image.cgImage)
        XCTAssertTrue(fullScreenGeometry(frame,size:screen.image.size,pixels:CGSize(width:CGFloat(cg.width),height:CGFloat(cg.height)),scale:screen.image.scale,orientation:o))
        XCTAssertLessThan(abs(v[0]/v[1]-Double(frame.width/frame.height)),0.01,"SOURCE_VIEWPORT_AXES_REQUIRED")
        let x=rect[0]+rect[2]*Double(fx),y=rect[1]+rect[3]*0.5
        guard x>=0,y>=0,x<=v[0],y<=v[1] else {throw NSError(domain:"POINT_OUTSIDE_PASSIVE_VIEWPORT",code:1)}
        let n=CGVector(dx:x/v[0],dy:y/v[1]),p=CGPoint(x:frame.width*n.dx,y:frame.height*n.dy)
        let expected=try XCTUnwrap(nativeScreenPoint(p,size:frame.size,orientation:o))
        let coordinate=app.coordinate(withNormalizedOffset:n),actual=coordinate.screenPoint
        XCTAssertLessThan(abs(actual.x-expected.x),1);XCTAssertLessThan(abs(actual.y-expected.y),1)
        return coordinate
    }
    @MainActor func testNativeInteraction() throws {
        continueAfterFailure=false
        actionDeadline=Date().addingTimeInterval(1500) // same existing XCTest command ceiling; no reset
        print("CAPTURE_TEST_METHOD_ENTERED="+kind)
        fflush(stdout)
        try bootstrapRunner()
        XCUIDevice.shared.orientation=kind=="iphone" ? .landscapeRight : .landscapeLeft
        let app=XCUIApplication(bundleIdentifier:bundle)
        app.launchArguments=["--","--mars-native-qa-observer"];app.launch()
        let coldDeadline=Date().addingTimeInterval(90)
        try waitForControlMirror(until:coldDeadline)
        let remaining=coldDeadline.timeIntervalSinceNow
        XCTAssertGreaterThan(remaining,0,"EXISTING_COLD_BUDGET_EXHAUSTED")
        Thread.sleep(forTimeInterval:max(0,remaining))
        capture("menu90",app:app)
        XCTAssertEqual(app.state,.runningForeground)
        print("CAPTURE_MENU90_FOREGROUND=true")
        try tapLabel(app,startLabel,"start")
        Thread.sleep(forTimeInterval:2)
        if try visiblePoint(app,"直接出擊") != nil { try tapLabel(app,"直接出擊","guide-dismiss") }
        Thread.sleep(forTimeInterval:2)
        let (before,_)=try latest()
        XCTAssertTrue(flag(before,"game_running") && flag(before,"player_valid") && !flag(before,"tree_paused"),"ACTUAL_BATTLE_REQUIRED")
        _=try XCTUnwrap(visiblePoint(app,"暫停"),"ACTUAL_HUD_PAUSE_LABEL_REQUIRED")
        capture("after-start",app:app);print("CRACK_QA_HUD_VERIFIED="+kind)
        let start=try joyPoint(app,before,0.5),end=try joyPoint(app,before,0.82)
        try marker("move","begin",before)
        start.press(forDuration:0.15,thenDragTo:end,withVelocity:.slow,thenHoldForDuration:1.2)
        Thread.sleep(forTimeInterval:0.4)
        try marker("move","end");capture("after-move",app:app)
        try tapLabel(app,"暫停","pause")
        _=try XCTUnwrap(visiblePoint(app,"繼續"),"VISIBLE_PAUSE_OVERLAY_REQUIRED")
        let (paused,_)=try latest();XCTAssertTrue(flag(paused,"tree_paused") && flag(paused,"manual_paused"))
        try marker("paused-wait","begin");Thread.sleep(forTimeInterval:0.8);try marker("paused-wait","end")
        capture("paused",app:app)
        let resumeBaseline=try rawActual()
        let resumePoint=try XCTUnwrap(visiblePoint(app,"繼續"))
        try marker("resume","begin",resumeBaseline.0,resumeBaseline);app.coordinate(withNormalizedOffset:resumePoint).tap();Thread.sleep(forTimeInterval:0.8);try marker("resume","end")
        let (resumed,_)=try latest();XCTAssertTrue(flag(resumed,"game_running") && !flag(resumed,"tree_paused") && !flag(resumed,"manual_paused"))
        XCTAssertNil(try visiblePoint(app,"繼續"));_=try XCTUnwrap(visiblePoint(app,"暫停"))
        capture("resumed",app:app);XCTAssertEqual(app.state,.runningForeground)
        print("CRACK_QA_INTERACTION_COMPLETE="+kind)
        // Host saves this launch's exact JSONL before running separate warm stage.
    }
    @MainActor func testWarmMenu() throws {
        continueAfterFailure=false
        XCUIDevice.shared.orientation=kind=="iphone" ? .landscapeRight : .landscapeLeft
        let app=XCUIApplication(bundleIdentifier:bundle);app.terminate();app.launchArguments=[];app.launch()
        Thread.sleep(forTimeInterval:90);capture("relaunch90",app:app)
        XCTAssertEqual(app.state,.runningForeground);_=try XCTUnwrap(visiblePoint(app,startLabel))
        print("CRACK_QA_WARM_MENU_VERIFIED="+kind)
    }
}
'''
    swift = swift.replace("APP_ID", app_id).replace("START_LABEL", label).replace("DEVICE_KIND", kind).replace("LIFECYCLE_NONCE", nonce)
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
    generate(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4])
