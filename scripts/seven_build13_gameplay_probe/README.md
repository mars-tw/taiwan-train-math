# SevenDistrict XCUITest Simulator gameplay probe

This is a **separate, disposable Xcode project**. Its empty host app makes a
standard UI-test target possible. The UI test activates the already installed
`tw.mars.sevendistrictreckoning` by bundle identifier; the Godot project,
`.pck`, exported Xcode project and installed binary are not modified. The first
macOS trial compiled and launched the UI-test runner but did not preserve a
title or gameplay frame. This revision adds observation before OCR so its next
bounded trial can distinguish app loading, orientation and OCR failure.

Use an Intel `macos-15` runner with Xcode 26.3 and a freshly created, booted
iOS 26 Simulator. Install the independently verified x86_64 Godot Simulator
`.app` first, then call:

```bash
bash path/to/xctest-probe/run_probe.sh "$SIMULATOR_UDID" "$RUNNER_TEMP/seven-probe-iphone"
```

Repeat with a fresh iPad Simulator and a separate output directory. Disable
parallel tests as in the script. `xcodebuild test` builds and installs only
`SevenProbeHost.app` and its UI-test runner. The test uses `XCUIDevice` to
rotate iPhone to `landscapeLeft` or iPad to `landscapeRight`, matching the
unchanged Godot Info.plist. It first captures the foreground app, then uses
full-pixel Vision OCR to locate the visible `開始新遊戲` control, validates the
screen-to-app tap coordinate, and requires two real frames with `MAIN-001`
and without Start before the gameplay capture.

The capture handshake is deliberately explicit:

1. After foreground and landscape checks, the test writes
   `seven-activated-ready.txt`. The host captures a native Simulator frame
   and writes `seven-activated-captured.flag`. While the test waits for title,
   the host additionally captures actual raw frames near 120, 240 and 360
   seconds. These are diagnostic only, including any portrait or loading view.
2. After OCR sees Start, the test writes `seven-title-ready.txt` in its
   Simulator Documents container and waits. The host captures
   `title-simctl-raw.png` with `simctl io`, validates landscape geometry and
   SHA-256, then writes `seven-title-captured.flag` next to the marker.
3. The test taps the verified Start coordinate. After its MAIN-001 check, it
   writes `seven-main001-ready.txt` and waits. The host captures
   `main001-simctl-raw.png` in the same manner and writes
   `seven-main001-captured.flag`.
4. The test exits successfully only after all three acknowledgements. On any host
   failure or timeout, the shell trap terminates and waits for its background
   `xcodebuild`. The enclosing CI script retains valid raw PNGs and bounded
   hash/handshake/error evidence. `.xcresult` and raw logs remain private in runner
   scratch and are removed during cleanup; neither image is store-ready yet.

Feasibility still depends on a real macOS trial. Possible failures are Xcode
project parsing/build settings, an unavailable iOS 26 Simulator runtime,
Vision not recognizing the rendered Traditional Chinese Start label, a Godot
black/loading frame before the 420-second limit, XCTest using a cloned device,
or a `MAIN-001` HUD that OCR cannot read. Any such failure must keep the old
`listingUploadReady=false` state and produce no claimed gameplay screenshot.

Primary Apple API references to check during the Mac trial:

- [XCUIDevice.orientation](https://developer.apple.com/documentation/xcuiautomation/xcuidevice/orientation)
- [XCUIApplication.activate()](https://developer.apple.com/documentation/xcuiautomation/xcuiapplication/activate())
- [XCUIElement.coordinate(withNormalizedOffset:)](https://developer.apple.com/documentation/xcuiautomation/xcuielement/coordinate(withnormalizedoffset:))
- [XCUIElementCoordinate.tap()](https://developer.apple.com/documentation/xcuiautomation/xcuielementcoordinate/tap())
- [VNRecognizeTextRequest](https://developer.apple.com/documentation/vision/vnrecognizetextrequest)
- [Xcode UI testing](https://developer.apple.com/documentation/xctest/user-interface-tests)
- Run `xcrun simctl help io` on the pinned Xcode runner for the exact installed
  `simctl` screenshot syntax; the official Xcode command-line tools supply it.
