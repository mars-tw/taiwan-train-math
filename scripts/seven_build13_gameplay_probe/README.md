# SevenDistrict XCUITest dual-native gameplay probe

This is a **separate, disposable Xcode project**. Its empty host app makes a
standard UI-test target possible. The UI test activates the already installed
`tw.mars.sevendistrictreckoning` by bundle identifier; the Godot project,
`.pck`, exported Xcode project and installed binary are not modified. The
second macOS trial preserved a portrait `simctl` activation frame while XCTest
reported a logical landscape app/screen. This revision preserves both original
capture paths to learn whether XCTest can provide a native landscape PNG. No
pixels are rotated, cropped or composited.

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

1. After foreground and landscape checks, the test atomically writes the
   unaltered `XCUIScreenshot.pngRepresentation` before announcing
   `seven-activated-ready.txt`. The host copies that original PNG and
   independently captures `simctl io`. It records both IHDR dimensions and
   hashes, then acknowledges only if either is the required native landscape
   size (2622×1206 iPhone or 2752×2064 iPad). Both originals are retained if
   unsuitable. During title wait, the host also takes raw `simctl` frames near
   120, 240 and 360 seconds as rejected diagnostics.
2. After OCR sees Start, the test saves an unaltered XCTest title PNG before
   `seven-title-ready.txt`. The host keeps the paired originals, selects only
   a native landscape source, and writes `seven-title-captured.flag`.
3. The test taps the verified Start coordinate. After its MAIN-001 check, it
   saves a third original XCTest PNG and writes `seven-main001-ready.txt`.
   The host keeps both originals and their source-selection receipt, then
   writes `seven-main001-captured.flag`.
4. The test exits successfully only after all three acknowledgements. On any host
   failure or timeout, the shell trap terminates and waits for its background
   `xcodebuild`. The enclosing CI script retains both original capture paths
   and bounded hash/handshake/error evidence. A selected original native
   landscape gameplay frame may become an opaque RGB candidate at identical
   dimensions; no rotation, crop or added content is performed. The original
   PNG bytes remain in evidence for comparison.
   `.xcresult` and raw logs remain private in runner scratch and are removed
   during cleanup. No image is store-ready until human review.

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
- [XCUIScreenshot.pngRepresentation](https://developer.apple.com/documentation/xcuiautomation/xcuiscreenshot/pngrepresentation)
- [Xcode UI testing](https://developer.apple.com/documentation/xctest/user-interface-tests)
- Run `xcrun simctl help io` on the pinned Xcode runner for the exact installed
  `simctl` screenshot syntax; the official Xcode command-line tools supply it.
