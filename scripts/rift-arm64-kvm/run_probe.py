"""One owned KVM observation of the exact Rift Forge ARM64 development APK.

The Unity Editor does not support Android emulators as a release proof. This
probe records what actually runs under the API 36 ARM64 native bridge and
never labels a partial game loop as accepted.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import socket
import struct
import subprocess
import time


REPO = "mars-tw/taiwan-train-math"
REF = "refs/heads/codex/rift-arm64-kvm-r5-20261013-fastcombat"
PACKAGE = "tw.mars.riftforge3d"
APK_SHA = "aa8cb0bbd1c0e236c415768ba0baafe646ad7db1e439f5ad4c8c09a38f80af28"
CERT_SHA = "11e100f23b70476c3a1b02054e85c9c9681609e5604fada346dd8f3fe3df4c40"
SYSTEM_IMAGE = "system-images;android-36;google_apis;x86_64"
PORT = 5582
SERIAL = f"emulator-{PORT}"
MAX_SECONDS = 650
MAX_CAPTURE_COUNT = 150


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalized(raw: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9]+", " ", raw.upper())).strip()


def classify(text: str) -> str:
    content = normalized(text)
    if "VIEWING FULL SCREEN" in content and "SWIPE DOWN" in content:
        return "immersive_hint"
    if "RIFT SEALED" in content:
        return "victory"
    if "CORE BROKEN" in content:
        return "defeat"
    if "THE FORGE" in content and "OPEN NEXT RIFT" in content:
        return "forge"
    if "ENTER THE RIFT" in content:
        return "title"
    if "STRIKE" in content and "CORE" in content and "RIFT" in content:
        return "combat"
    if "RIFT PAUSED" in content:
        return "pause"
    return "unknown"


def critical_unity_errors(log: bytes, pid: str) -> list[str]:
    app_error = re.compile(r"\s" + re.escape(pid) + r"\s+\d+\s+E Unity\s+:")
    critical = ("Can't add component because class", "ArgumentNullException",
                "NullReferenceException", "MissingReferenceException",
                "MissingMethodException", "Fatal signal", "FATAL EXCEPTION")
    return [line[:500] for line in log.decode("utf-8", "replace").splitlines()
            if app_error.search(line) and any(marker in line for marker in critical)][:30]


def self_test() -> None:
    assert classify("RIFT FORGE ENTER THE RIFT") == "title"
    assert classify("CORE 100 / 100 RIFT 1 / 4 STRIKE DODGE") == "combat"
    assert classify("THE FORGE RIFT 1 CLEARED OPEN NEXT RIFT") == "forge"
    assert classify("RIFT SEALED THE WARDEN HAS FALLEN") == "victory"
    assert classify("CORE BROKEN THE FORGE AWAITS YOUR RETURN") == "defeat"
    assert classify("RIFT PAUSED RESUME") == "pause"
    assert classify("Viewing full screen To exit swipe down from the top of your screen") == "immersive_hint"
    assert len(critical_unity_errors(
        b"1791870996.653  2753  2885 E Unity   : Can't add component because class 'CapsuleCollider' doesn't exist!\n",
        "2753")) == 1
    print("RIFT_KVM_PROBE_SELF_TEST_PASS")


class Probe:
    def __init__(self) -> None:
        if (os.environ.get("GITHUB_ACTIONS") != "true"
                or os.environ.get("GITHUB_REPOSITORY") != REPO
                or os.environ.get("GITHUB_REF") != REF
                or os.environ.get("GITHUB_RUN_ATTEMPT") != "1"):
            raise RuntimeError("Fixed one-shot QA branch only")
        self.run_id = os.environ["GITHUB_RUN_ID"]
        if not re.fullmatch(r"[0-9]+", self.run_id):
            raise RuntimeError("Invalid run ID")
        self.sdk = Path(os.environ["RIFT_SDK"]).resolve()
        self.apk = Path(os.environ["RIFT_APK"]).resolve()
        self.out = Path(os.environ["RIFT_OUTPUT"]).resolve()
        self.temp = Path(os.environ["RUNNER_TEMP"]).resolve()
        self.avd_home = Path(os.environ["ANDROID_AVD_HOME"]).resolve()
        self.avd_name = "rift-arm64-kvm-r5-" + self.run_id
        self.avd_path = self.avd_home / (self.avd_name + ".avd")
        self.adb = str(self.sdk / "platform-tools/adb")
        self.emulator = str(self.sdk / "emulator/emulator")
        self.avdmanager = str(self.sdk / "cmdline-tools/latest/bin/avdmanager")
        self.apksigner = str(self.sdk / "build-tools/36.1.0/apksigner")
        self.aapt = str(self.sdk / "build-tools/36.1.0/aapt")
        self.process: subprocess.Popen | None = None
        self.bootlog = None
        self.recorder: subprocess.Popen | None = None
        self.recording_started = 0.0
        self.segment = 0
        self.booted = False
        self.app_pid: str | None = None
        self.width = 0
        self.height = 0
        self.capture_count = 0
        self.started = time.monotonic()
        self.deadline = self.started + MAX_SECONDS
        self.report: dict = {
            "schemaVersion": 1, "runId": self.run_id,
            "headSha": os.environ["GITHUB_SHA"],
            "package": PACKAGE, "apkSha256": APK_SHA,
            "certificateSha256": CERT_SHA,
            "environment": "Android API36 Google x86_64 ARM64 native bridge; Unity emulator unsupported",
            "physicalDevice": False, "storeWrites": 0,
            "status": "STARTED", "atUtc": now(),
            "screenshots": [], "actions": [], "videos": [],
            "forges": [], "combatObservations": [],
        }
        owner = json.loads((self.out / "owned-run.json").read_text(encoding="utf-8"))
        if owner != {"runId": self.run_id, "headSha": os.environ["GITHUB_SHA"],
                     "owner": "rift-arm64-kvm-r5"}:
            raise RuntimeError("Evidence directory owner mismatch")
        self.save()

    def save(self) -> None:
        (self.out / "native-observation.json").write_text(
            json.dumps(self.report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def command(self, argv: list[str], timeout: int = 30,
                input_bytes: bytes | None = None, allow_failure: bool = False):
        result = subprocess.run(argv, input=input_bytes, capture_output=True,
                                timeout=timeout)
        if result.returncode != 0 and not allow_failure:
            raise RuntimeError(f"Command failed ({Path(argv[0]).name}, exit {result.returncode}): "
                               + result.stderr.decode("utf-8", "replace")[-500:])
        return result

    def device(self, *args: str, timeout: int = 30, allow_failure: bool = False):
        return self.command([self.adb, "-s", SERIAL, *args], timeout=timeout,
                            allow_failure=allow_failure)

    def inspect_input(self) -> None:
        manifest = json.loads((self.temp / "rift-arm64-kvm-r5-input/manifest.json").read_text())
        if (manifest.get("repository") != REPO or manifest.get("branch") != REF.removeprefix("refs/heads/")
                or manifest.get("appId") != PACKAGE or manifest.get("versionCode") != 1
                or manifest.get("apk", {}).get("sha256") != APK_SHA
                or manifest.get("apk", {}).get("certificateSha256") != CERT_SHA
                or not self.apk.is_file() or self.apk.stat().st_size != 57_152_389
                or digest(self.apk.read_bytes()) != APK_SHA):
            raise RuntimeError("Exact APK/manifest identity mismatch")
        cert = self.command([self.apksigner, "verify", "--verbose", "--print-certs", str(self.apk)],
                            timeout=35).stdout.decode("utf-8", "replace")
        (self.out / "apk-signature-verification.txt").write_text(cert)
        if ("Verifies" not in cert or CERT_SHA not in cert.lower()):
            raise RuntimeError("APK v2/debug certificate verification failed")
        badging = self.command([self.aapt, "dump", "badging", str(self.apk)],
                               timeout=35).stdout.decode("utf-8", "replace")
        (self.out / "apk-badging.txt").write_text(badging)
        if (f"name='{PACKAGE}'" not in badging or "versionCode='1'" not in badging
                or "sdkVersion:'26'" not in badging or "targetSdkVersion:'36'" not in badging):
            raise RuntimeError("APK package/version/SDK mismatch")
        acceleration = self.command([self.emulator, "-accel-check"], timeout=20)
        accel = (acceleration.stdout + acceleration.stderr).decode("utf-8", "replace")
        (self.out / "emulator-accel-check.txt").write_text(accel)
        if "KVM" not in accel or "usable" not in accel.lower():
            raise RuntimeError("KVM unavailable; no software-emulation fallback")
        gpu = self.command([self.emulator, "-help-gpu"], timeout=20)
        help_text = (gpu.stdout + gpu.stderr).decode("utf-8", "replace")
        if not re.search(r"(?<!\w)swangle(?!\w)", help_text):
            raise RuntimeError("Pinned emulator does not offer swangle GLES")
        self.report["apkInputVerified"] = True
        self.report["kvmUsable"] = True
        self.save()

    def boot(self) -> None:
        attached = self.command([self.adb, "devices"], timeout=20).stdout.decode()
        if any(row.strip() for row in attached.strip().splitlines()[1:]):
            raise RuntimeError("Unexpected preexisting adb device")
        for port in (PORT, PORT + 1):
            with socket.socket() as reservation:
                reservation.bind(("127.0.0.1", port))
        self.avd_home.mkdir(parents=True, exist_ok=True)
        if self.avd_path.exists() or (self.avd_home / (self.avd_name + ".ini")).exists():
            raise RuntimeError("Owned AVD path exists; no overwrite")
        created = self.command([self.avdmanager, "create", "avd", "-n", self.avd_name,
                                "-k", SYSTEM_IMAGE, "--device", "pixel_2",
                                "--path", str(self.avd_path)],
                               timeout=90, input_bytes=b"no\n", allow_failure=True)
        (self.out / "avd-create.stdout.txt").write_bytes(created.stdout)
        (self.out / "avd-create.stderr.txt").write_bytes(created.stderr)
        if created.returncode != 0:
            raise RuntimeError("Owned AVD creation failed; no retry")
        self.bootlog = (self.out / "owned-emulator.log").open("wb")
        self.process = subprocess.Popen(
            [self.emulator, "-avd", self.avd_name, "-no-window", "-no-boot-anim",
             "-no-snapshot", "-no-audio", "-accel", "on", "-gpu", "swangle",
             "-memory", "2048", "-cores", "2", "-camera-back", "none",
             "-camera-front", "none", "-port", str(PORT)],
            stdout=self.bootlog, stderr=subprocess.STDOUT, start_new_session=True)
        until = min(self.deadline, time.monotonic() + 240)
        while time.monotonic() < until:
            if self.process.poll() is not None:
                raise RuntimeError("Owned emulator exited before boot")
            result = self.device("shell", "getprop", "sys.boot_completed",
                                 timeout=15, allow_failure=True)
            if result.returncode == 0 and result.stdout.strip() == b"1":
                break
            time.sleep(3)
        else:
            raise RuntimeError("Owned emulator boot timeout")
        self.booted = True
        abi = self.device("shell", "getprop", "ro.product.cpu.abilist64").stdout.decode().strip()
        bridge = self.device("shell", "getprop", "ro.dalvik.vm.native.bridge").stdout.decode().strip()
        boot_text = (self.out / "owned-emulator.log").read_text(errors="replace")
        if ("arm64-v8a" not in abi.split(",") or bridge != "libndk_translation.so"
                or not re.search(r"gles_mode_selected:swangle\b", boot_text)):
            raise RuntimeError("Guest ARM64 bridge or swangle renderer not proven")
        self.report.update(bootVerified=True, actualAbi64=abi,
                           actualNativeBridge=bridge, actualSwangle=True)
        self.device("shell", "wm", "size", "720x1280")
        self.device("shell", "wm", "density", "320")
        self.device("shell", "settings", "put", "system", "accelerometer_rotation", "0")
        self.device("shell", "settings", "put", "system", "user_rotation", "1")
        self.report["ownedDisplay"] = {
            "size": self.device("shell", "wm", "size").stdout.decode().strip(),
            "density": self.device("shell", "wm", "density").stdout.decode().strip(),
            "userRotation": self.device("shell", "settings", "get", "system",
                                         "user_rotation").stdout.decode().strip()}
        self.save()

    def install(self) -> str:
        installed = self.device("install", str(self.apk), timeout=130, allow_failure=True)
        (self.out / "owned-adb-install.stdout.txt").write_bytes(installed.stdout)
        (self.out / "owned-adb-install.stderr.txt").write_bytes(installed.stderr)
        if installed.returncode != 0 or b"Success" not in installed.stdout:
            raise RuntimeError("Exact ARM64 APK install failed: "
                               + (installed.stdout + installed.stderr).decode("utf-8", "replace")[-500:])
        package = self.device("shell", "dumpsys", "package", PACKAGE,
                              timeout=30).stdout.decode("utf-8", "replace")
        (self.out / "owned-dumpsys-package.txt").write_text(package)
        if not re.search(r"\bversionCode=1\b", package) or "versionName=1.0.0" not in package:
            raise RuntimeError("Installed package identity differs")
        resolved = self.device("shell", "cmd", "package", "resolve-activity", "--brief",
                               PACKAGE).stdout.decode("utf-8", "replace").strip().splitlines()
        if not resolved or not resolved[-1].strip().startswith(PACKAGE + "/"):
            raise RuntimeError("No exported MAIN launcher activity")
        alias = resolved[-1].strip()
        self.report["installedIdentityVerified"] = True
        self.report["resolvedActivity"] = alias
        self.save()
        return alias

    def pixel_rgb(self, file: Path, x_fraction: float, y_fraction: float) -> tuple[int, int, int]:
        x, y = int(self.width * x_fraction), int(self.height * y_fraction)
        raw = self.command(["ffmpeg", "-hide_banner", "-loglevel", "error",
                            "-i", str(file), "-vf", f"crop=1:1:{x}:{y}",
                            "-frames:v", "1", "-f", "rawvideo",
                            "-pix_fmt", "rgb24", "pipe:1"], timeout=20).stdout
        if len(raw) != 3:
            raise RuntimeError("Original PNG control pixel could not be sampled")
        return tuple(raw)

    def capture(self, label: str) -> tuple[str, str]:
        if self.capture_count >= MAX_CAPTURE_COUNT:
            raise RuntimeError("Screenshot budget exhausted")
        self.capture_count += 1
        file = self.out / f"{self.capture_count:03d}-{label}.png"
        png = self.device("exec-out", "screencap", "-p", timeout=30).stdout
        if not png.startswith(b"\x89PNG\r\n\x1a\n") or png[12:16] != b"IHDR":
            raise RuntimeError("Original guest screenshot is not PNG")
        file.write_bytes(png)
        width, height = struct.unpack(">II", png[16:24])
        if width <= height:
            raise RuntimeError(f"Guest game screenshot not landscape: {width}x{height}")
        self.width, self.height = width, height
        ocr = self.command(["tesseract", str(file), "stdout", "--psm", "11"],
                           timeout=25, allow_failure=True)
        text = ocr.stdout.decode("utf-8", "replace")
        (self.out / f"{self.capture_count:03d}-{label}.ocr.txt").write_text(text)
        # Preserve the original screenshot. Derived crops help OCR read dark
        # lettering on brightly colored Unity buttons, which whole-frame OCR
        # omitted in the first native render even though the button was visible.
        content = normalized(text)
        crops = []
        if "RIFT FORGE" in content and "ENTER THE RIFT" not in content:
            crops.append(("title-button", .32, .57, .36, .18))
        if "THE FORGE" in content and "OPEN NEXT RIFT" not in content:
            crops.append(("forge-next", .32, .77, .36, .17))
        if "THE FORGE" in content:
            if "EMBER EDGE" not in content:
                crops.append(("forge-blade", .15, .445, .20, .06))
            if "LIVING PLATE" not in content:
                crops.append(("forge-vitality", .40, .445, .20, .06))
        if "CORE" in content and "RIFT" in content:
            if "STRIKE" not in content:
                crops.append(("strike", .76, .66, .20, .24))
            if "DODGE" not in content:
                crops.append(("dodge", .63, .75, .19, .23))
            if "MOVE" not in content:
                crops.append(("move", .03, .65, .20, .30))
        for crop_name, fx, fy, fw, fh in crops:
            crop_file = self.out / f"{self.capture_count:03d}-{label}-{crop_name}-ocr-crop.png"
            x, y = int(width * fx), int(height * fy)
            cw, ch = int(width * fw), int(height * fh)
            made = self.command(["ffmpeg", "-hide_banner", "-loglevel", "error",
                                 "-y", "-i", str(file), "-vf",
                                 f"crop={cw}:{ch}:{x}:{y},format=gray",
                                 "-frames:v", "1", str(crop_file)],
                                timeout=25, allow_failure=True)
            if made.returncode != 0 or not crop_file.is_file():
                raise RuntimeError("Derived button OCR crop failed: " + crop_name)
            cropped = self.command(["tesseract", str(crop_file), "stdout",
                                    "--psm", "7"], timeout=25, allow_failure=True)
            crop_text = cropped.stdout.decode("utf-8", "replace")
            (self.out / f"{self.capture_count:03d}-{label}-{crop_name}.ocr.txt").write_text(crop_text)
            text += "\n" + crop_text
        state = classify(text)
        color_proof = None
        forge_proof = None
        if all(token in normalized(text) for token in ("CORE", "RIFT", "MOVE")):
            strike = self.pixel_rgb(file, .86, .695)
            dodge = self.pixel_rgb(file, .72, .8125)
            strike_ok = strike[0] < 120 and strike[1] > 170 and strike[2] > 170
            dodge_ok = dodge[0] > 190 and 110 < dodge[1] < 220 and dodge[2] < 130
            color_proof = {"method": "source-anchored original PNG pixel",
                           "strikeRgb": strike, "dodgeRgb": dodge,
                           "strikePass": strike_ok, "dodgePass": dodge_ok}
            if strike_ok and dodge_ok:
                state = "combat"
        if "THE FORGE" in normalized(text):
            next_rgb = self.pixel_rgb(file, .50, .81)
            blade_rgb = self.pixel_rgb(file, .25, .42)
            vitality_rgb = self.pixel_rgb(file, .50, .42)
            next_ok = next_rgb[0] > 190 and 110 < next_rgb[1] < 220 and next_rgb[2] < 130
            blade_ok = blade_rgb[0] < 120 and blade_rgb[1] > 170 and blade_rgb[2] > 170
            vitality_ok = vitality_rgb[0] > 190 and 110 < vitality_rgb[1] < 220 and vitality_rgb[2] < 130
            forge_proof = {"method": "source-anchored original PNG pixel",
                           "nextRgb": next_rgb, "bladeRgb": blade_rgb,
                           "vitalityRgb": vitality_rgb, "nextPass": next_ok,
                           "bladePass": blade_ok, "vitalityPass": vitality_ok}
            if next_ok:
                state = "forge"
        self.report["screenshots"].append({"file": file.name, "bytes": len(png),
            "sha256": digest(png), "width": width, "height": height,
            "state": state, "ocr": normalized(text)[:500],
            "controlColorProof": color_proof, "forgeColorProof": forge_proof,
            "atUtc": now()})
        self.save()
        return state, normalized(text)

    def fast_observe(self, label: str) -> str:
        """Save the original PNG and check fixed UI colors without slow OCR."""
        if self.capture_count >= MAX_CAPTURE_COUNT:
            raise RuntimeError("Screenshot budget exhausted")
        self.capture_count += 1
        file = self.out / f"{self.capture_count:03d}-{label}.png"
        png = self.device("exec-out", "screencap", "-p", timeout=30).stdout
        if not png.startswith(b"\x89PNG\r\n\x1a\n") or png[12:16] != b"IHDR":
            raise RuntimeError("Original fast guest screenshot is not PNG")
        file.write_bytes(png)
        self.width, self.height = struct.unpack(">II", png[16:24])
        if self.width <= self.height:
            raise RuntimeError("Fast guest screenshot not landscape")
        strike = self.pixel_rgb(file, .86, .695)
        dodge = self.pixel_rgb(file, .72, .8125)
        strike_ok = strike[0] < 120 and strike[1] > 170 and strike[2] > 170
        dodge_ok = dodge[0] > 190 and 110 < dodge[1] < 220 and dodge[2] < 130
        next_rgb = None
        blade_rgb = None
        vitality_rgb = None
        next_ok = blade_ok = vitality_ok = False
        if not (strike_ok and dodge_ok):
            next_rgb = self.pixel_rgb(file, .50, .81)
            blade_rgb = self.pixel_rgb(file, .25, .42)
            vitality_rgb = self.pixel_rgb(file, .50, .42)
            next_ok = next_rgb[0] > 190 and 110 < next_rgb[1] < 220 and next_rgb[2] < 130
            blade_ok = blade_rgb[0] < 120 and blade_rgb[1] > 170 and blade_rgb[2] > 170
            vitality_ok = vitality_rgb[0] > 190 and 110 < vitality_rgb[1] < 220 and vitality_rgb[2] < 130
        state = "combat" if strike_ok and dodge_ok else (
            "forge" if next_ok and blade_ok and vitality_ok else "unknown")
        self.report["screenshots"].append({
            "file": file.name, "bytes": len(png), "sha256": digest(png),
            "width": self.width, "height": self.height, "state": state,
            "captureMode": "original PNG with immediate source-anchored pixel checks",
            "controlColorProof": {"strikeRgb": strike, "dodgeRgb": dodge,
                "strikePass": strike_ok, "dodgePass": dodge_ok},
            "forgeColorProof": {"nextRgb": next_rgb, "bladeRgb": blade_rgb,
                "vitalityRgb": vitality_rgb, "nextPass": next_ok,
                "bladePass": blade_ok, "vitalityPass": vitality_ok},
            "atUtc": now()})
        self.save()
        return state

    def tap(self, name: str, x_fraction: float, y_fraction: float, evidence: str) -> None:
        x, y = int(self.width * x_fraction), int(self.height * y_fraction)
        self.device("shell", "input", "tap", str(x), str(y), timeout=15)
        self.report["actions"].append({"type": "tap", "name": name, "x": x, "y": y,
            "evidence": evidence, "atUtc": now()})
        self.save()

    def swipe_move(self) -> None:
        x, y = int(self.width * .13), int(self.height * .80)
        self.device("shell", "input", "swipe", str(x), str(y),
                    str(int(self.width * .20)), str(int(self.height * .72)),
                    "450", timeout=20)
        self.report["actions"].append({"type": "swipe", "name": "MOVE",
            "from": [x, y], "to": [int(self.width * .20), int(self.height * .72)],
            "durationMs": 450, "atUtc": now()})
        self.save()

    def start_video(self) -> None:
        self.segment += 1
        remote = f"/sdcard/Movies/rift-arm64-kvm-r5-{self.segment}.mp4"
        self.recording_started = time.monotonic()
        self.recorder = subprocess.Popen(
            [self.adb, "-s", SERIAL, "shell", "screenrecord",
             "--bit-rate", "4000000", "--time-limit", "180", remote],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(.5)
        if self.recorder.poll() is not None:
            raise RuntimeError("Original screenrecord exited on start")
        self.report["activeRemoteVideo"] = remote
        self.save()

    def finish_video(self) -> None:
        if self.recorder is None:
            return
        remote = self.report.get("activeRemoteVideo")
        if self.recorder.poll() is None:
            pid = self.device("shell", "pidof", "screenrecord",
                              timeout=10, allow_failure=True).stdout.decode().strip()
            if re.fullmatch(r"[1-9][0-9]*", pid):
                self.device("shell", "kill", "-2", pid,
                            timeout=10, allow_failure=True)
        try:
            self.recorder.wait(timeout=20)
        except subprocess.TimeoutExpired:
            self.recorder.terminate()
            self.recorder.wait(timeout=10)
        self.recorder = None
        local = self.out / f"rift-arm64-r5-native-segment-{self.segment}.mp4"
        pulled = self.device("pull", remote, str(local), timeout=90, allow_failure=True)
        (self.out / f"video-pull-{self.segment}.txt").write_bytes(
            pulled.stdout + b"\n" + pulled.stderr)
        if pulled.returncode != 0 or not local.is_file() or local.stat().st_size < 1024:
            self.report.setdefault("videoErrors", []).append("Original screenrecord pull failed")
            self.save()
            return
        with local.open("rb") as stream:
            if stream.read(12)[4:8] != b"ftyp":
                self.report.setdefault("videoErrors", []).append("Pulled video not MP4")
                self.save()
                return
        probe = self.command(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                              "-of", "default=noprint_wrappers=1:nokey=1", str(local)],
                             timeout=30, allow_failure=True)
        try:
            duration = float(probe.stdout.decode().strip())
        except ValueError:
            duration = 0.0
        data = local.read_bytes()
        self.report["videos"].append({"file": local.name, "bytes": len(data),
            "sha256": digest(data), "durationSeconds": duration,
            "originalScreenrecord": True, "physicalDevice": False})
        self.report.pop("activeRemoteVideo", None)
        self.save()

    def ensure_video_window(self) -> None:
        if self.recorder is None or self.recorder.poll() is not None or time.monotonic() - self.recording_started > 150:
            self.finish_video()
            if self.segment < 4:
                self.start_video()

    def launch_and_play(self, alias: str) -> None:
        self.device("logcat", "-c", timeout=20)
        self.start_video()
        started = self.device("shell", "am", "start", "-W", "-n", alias,
                              timeout=60, allow_failure=True)
        (self.out / "owned-am-start.txt").write_bytes(started.stdout + b"\n" + started.stderr)
        if started.returncode != 0:
            raise RuntimeError("Native MAIN activity launch failed")
        for _ in range(20):
            pid = self.device("shell", "pidof", PACKAGE, allow_failure=True).stdout.decode().strip()
            if re.fullmatch(r"[1-9][0-9]*", pid):
                self.app_pid = pid
                break
            time.sleep(2)
        if self.app_pid is None:
            raise RuntimeError("Unity app did not acquire a native process PID")
        self.report["nativeAppPid"] = self.app_pid
        self.save()
        state = "unknown"
        dismissed_hint = False
        title_frames = 0
        for attempt in range(16):
            time.sleep(3 if attempt else 1)
            state, text = self.capture(f"cold-title-{attempt}")
            if state == "immersive_hint":
                if dismissed_hint:
                    raise RuntimeError("Android immersive hint remained after one owned Got it tap")
                self.tap("ANDROID FULLSCREEN GOT IT", .80, .53,
                         "OCR-visible Android immersive hint on owned emulator")
                dismissed_hint = True
                time.sleep(1)
                title_frames = 0
                continue
            if state == "title":
                title_frames += 1
                if title_frames >= 2:
                    break
            else:
                title_frames = 0
        if state != "title":
            raise RuntimeError("Native launch did not render OCR-visible ENTER THE RIFT")
        self.report["coldTitleVisible"] = True
        pregame_log = self.device("logcat", "-d", "-v", "epoch",
                                  "--pid=" + self.app_pid, timeout=30).stdout
        (self.out / "owned-app-logcat-before-gameplay.txt").write_bytes(pregame_log)
        pregame_errors = critical_unity_errors(pregame_log, self.app_pid)
        self.report["criticalUnityErrorsBeforeGameplay"] = pregame_errors
        if pregame_errors:
            self.save()
            raise RuntimeError("Critical Unity errors before gameplay; no title tap")
        self.tap("ENTER THE RIFT", .50, .66, "OCR-visible cold title")
        time.sleep(2)
        state, text = self.capture("post-enter")
        if state != "combat":
            raise RuntimeError("Title tap did not reach OCR-visible combat HUD")
        self.report["combatStarted"] = True
        if ("MOVE" in text
                and (self.report["screenshots"][-1].get("controlColorProof") or {}).get("strikePass")
                and self.report["screenshots"][-1]["controlColorProof"].get("dodgePass")):
            self.swipe_move()
            time.sleep(.4)
            self.capture("post-move-swipe")
            self.report["moveTouchIssuedAgainstVisibleHud"] = True
        else:
            raise RuntimeError("Combat HUD lacks visible STRIKE/DODGE/MOVE controls")
        self.save()

        forge_count = 0
        combat_batches = 0
        while time.monotonic() < self.deadline and combat_batches < 70:
            self.ensure_video_window()
            state, text = self.capture(f"phase-{combat_batches}-{forge_count}")
            if state == "victory":
                self.report["victoryVisible"] = True
                self.report["status"] = "FOUR_RIFTS_VICTORY_OBSERVED"
                self.save()
                return
            if state == "defeat":
                self.report["status"] = "NATIVE_DEFEAT_OBSERVED_BEFORE_FOUR_RIFTS"
                self.save()
                raise RuntimeError("Native run ended in defeat before victory")
            if state == "forge":
                forge_count += 1
                self.report["forges"].append({"ordinal": forge_count,
                    "screenshot": self.report["screenshots"][-1]["file"],
                    "ocr": text[:500]})
                self.save()
                if forge_count > 3:
                    raise RuntimeError("Unexpected fourth forge before Warden victory")
                # UI anchors are source-defined; tapping requires the original
                # screenshot to show THE FORGE and OPEN NEXT RIFT together.
                choice = "EMBER EDGE" if forge_count != 2 else "LIVING PLATE"
                x = .25 if forge_count != 2 else .50
                forge_color = self.report["screenshots"][-1].get("forgeColorProof") or {}
                card_color_ok = forge_color.get("bladePass" if forge_count != 2 else "vitalityPass")
                if choice not in text and not card_color_ok:
                    raise RuntimeError("Expected forge upgrade text is not visible")
                self.tap(choice, x, .53, "Source-anchored colored upgrade card on original forge PNG")
                time.sleep(.8)
                upgraded_state, upgraded_text = self.capture(f"forge-{forge_count}-after-upgrade")
                if upgraded_state != "forge":
                    raise RuntimeError("Forge purchase did not leave forge view visible")
                self.report["forges"][-1]["afterUpgradeScreenshot"] = self.report["screenshots"][-1]["file"]
                self.report["forges"][-1]["afterUpgradeOcr"] = upgraded_text[:500]
                self.tap("OPEN NEXT RIFT", .50, .85, "Source-anchored orange NEXT button on original forge PNG")
                time.sleep(2)
                advanced_state, advanced_text = self.capture(f"rift-{forge_count+1}-after-next")
                if advanced_state != "combat":
                    raise RuntimeError("Forge NEXT did not advance to combat")
                self.report["forges"][-1]["nextCombatScreenshot"] = self.report["screenshots"][-1]["file"]
                self.save()
                continue
            if state != "combat":
                time.sleep(1)
                continue
            combat_batches += 1
            self.report["combatObservations"].append({"batch": combat_batches,
                "screenshot": self.report["screenshots"][-1]["file"], "ocr": text[:500]})
            # The button itself must be visible in the original phase PNG.
            control_proof = self.report["screenshots"][-1].get("controlColorProof") or {}
            if "STRIKE" not in text and not control_proof.get("strikePass"):
                raise RuntimeError("No visible STRIKE before combat taps")
            for _ in range(4):
                self.tap("STRIKE", .86, .77, "Source-anchored cyan STRIKE on original combat PNG")
                time.sleep(.54)
            if ("DODGE" in text or control_proof.get("dodgePass")) and combat_batches % 2 == 0:
                self.tap("DODGE", .72, .86, "Source-anchored orange DODGE on original combat PNG")
                time.sleep(.4)
        self.report["status"] = "PARTIAL_NATIVE_GAMEPLAY_ONLY"
        self.save()
        raise RuntimeError("Bounded native battle loop ended without victory")

    def fast_launch_and_play(self, alias: str) -> None:
        """React to combat in seconds; inspect static forge/outcome screens slowly."""
        self.device("logcat", "-c", timeout=20)
        self.start_video()
        started = self.device("shell", "am", "start", "-W", "-n", alias,
                              timeout=60, allow_failure=True)
        (self.out / "owned-am-start.txt").write_bytes(started.stdout + b"\n" + started.stderr)
        if started.returncode != 0:
            raise RuntimeError("Native MAIN activity launch failed")
        for _ in range(20):
            pid = self.device("shell", "pidof", PACKAGE, allow_failure=True).stdout.decode().strip()
            if re.fullmatch(r"[1-9][0-9]*", pid):
                self.app_pid = pid
                break
            time.sleep(2)
        if self.app_pid is None:
            raise RuntimeError("Unity app did not acquire a native process PID")
        self.report["nativeAppPid"] = self.app_pid
        self.save()

        state = "unknown"
        dismissed_hint = False
        title_frames = 0
        for attempt in range(16):
            time.sleep(3 if attempt else 1)
            state, _ = self.capture(f"cold-title-{attempt}")
            if state == "immersive_hint":
                if dismissed_hint:
                    raise RuntimeError("Android immersive hint remained after one owned Got it tap")
                self.tap("ANDROID FULLSCREEN GOT IT", .80, .53,
                         "OCR-visible Android immersive hint on owned emulator")
                dismissed_hint = True
                title_frames = 0
                time.sleep(1)
                continue
            if state == "title":
                title_frames += 1
                if title_frames >= 2:
                    break
            else:
                title_frames = 0
        if state != "title":
            raise RuntimeError("Native launch did not render OCR-visible ENTER THE RIFT")
        self.report["coldTitleVisible"] = True
        pregame_log = self.device("logcat", "-d", "-v", "epoch",
                                  "--pid=" + self.app_pid, timeout=30).stdout
        (self.out / "owned-app-logcat-before-gameplay.txt").write_bytes(pregame_log)
        pregame_errors = critical_unity_errors(pregame_log, self.app_pid)
        self.report["criticalUnityErrorsBeforeGameplay"] = pregame_errors
        if pregame_errors:
            self.save()
            raise RuntimeError("Critical Unity errors before gameplay; no title tap")

        self.tap("ENTER THE RIFT", .50, .66, "OCR-visible cold title")
        self.report["fastCombatMode"] = True
        self.report["moveTouchDeferredForCombatSurvival"] = True
        time.sleep(.4)
        for attempt in range(6):
            state = self.fast_observe(f"post-enter-fast-{attempt}")
            if state == "combat":
                break
            time.sleep(.4)
        if state != "combat":
            slow_state, _ = self.capture("post-enter-slow-diagnostic")
            raise RuntimeError("Fast original PNG did not prove combat controls: " + slow_state)
        self.report["combatStarted"] = True
        self.save()

        forges = 0
        bursts = 0
        unexpected = 0
        while time.monotonic() < self.deadline and bursts < 50:
            self.ensure_video_window()
            if state == "combat":
                bursts += 1
                source_file = self.report["screenshots"][-1]["file"]
                self.report["combatObservations"].append({
                    "burst": bursts, "beforeScreenshot": source_file,
                    "controlColorProof": self.report["screenshots"][-1]["controlColorProof"],
                    "atUtc": now()})
                # A fresh exact-APK PNG confirmed both source-defined buttons.
                # Six sub-second taps avoid the 36-second OCR delay of R4.
                for _ in range(6):
                    self.tap("STRIKE", .86, .77,
                             "Fresh original PNG cyan STRIKE control at source anchor")
                    time.sleep(.52)
                state = self.fast_observe(f"after-strike-burst-{bursts}")
                self.report["combatObservations"][-1]["afterScreenshot"] = (
                    self.report["screenshots"][-1]["file"])
                self.save()
                if state == "combat" and bursts % 2 == 0:
                    self.tap("DODGE", .72, .86,
                             "Fresh original PNG orange DODGE control at source anchor")
                    time.sleep(.35)
                continue

            if state == "forge":
                forges += 1
                if forges > 3:
                    raise RuntimeError("Unexpected fourth forge before victory")
                slow_state, text = self.capture(f"forge-{forges}-arrival")
                if slow_state != "forge":
                    raise RuntimeError("Fast forge colors did not match slow original PNG")
                self.report["forges"].append({
                    "ordinal": forges,
                    "beforeScreenshot": self.report["screenshots"][-1]["file"],
                    "beforeOcr": text[:500], "atUtc": now()})
                self.save()
                # Every cleared wave pays for one Vitality and one Blade level.
                self.tap("LIVING PLATE", .50, .53,
                         "Original forge PNG with orange Vitality card")
                time.sleep(.35)
                self.tap("EMBER EDGE", .25, .53,
                         "Original forge PNG with cyan Blade card")
                time.sleep(.35)
                after_state, after_text = self.capture(f"forge-{forges}-after-two-upgrades")
                if after_state != "forge":
                    raise RuntimeError("Forge upgrades left the forge view")
                self.report["forges"][-1]["afterScreenshot"] = (
                    self.report["screenshots"][-1]["file"])
                self.report["forges"][-1]["afterOcr"] = after_text[:500]
                self.tap("OPEN NEXT RIFT", .50, .85,
                         "Original forge PNG with orange NEXT button")
                time.sleep(.4)
                for attempt in range(6):
                    state = self.fast_observe(f"after-forge-{forges}-next-{attempt}")
                    if state == "combat":
                        break
                    time.sleep(.4)
                if state != "combat":
                    slow_state, _ = self.capture(f"forge-{forges}-next-diagnostic")
                    raise RuntimeError("Forge NEXT did not reach fast combat: " + slow_state)
                self.report["forges"][-1]["nextCombatScreenshot"] = (
                    self.report["screenshots"][-1]["file"])
                self.save()
                continue

            # Outcome overlays have neither combat nor forge control colors.
            slow_state, _ = self.capture(f"outcome-after-burst-{bursts}")
            if slow_state == "victory":
                self.report["victoryVisible"] = True
                self.report["status"] = ("FOUR_RIFTS_VICTORY_OBSERVED"
                                         if forges == 3 else "VICTORY_WITH_MISSING_FORGE_PROOF")
                self.save()
                if forges != 3:
                    raise RuntimeError("Victory without three observed forge transitions")
                return
            if slow_state == "defeat":
                self.report["status"] = "NATIVE_DEFEAT_OBSERVED_BEFORE_FOUR_RIFTS"
                self.save()
                raise RuntimeError("Native run ended in defeat before victory")
            if slow_state in ("combat", "forge"):
                state = slow_state
                continue
            unexpected += 1
            if unexpected >= 3:
                raise RuntimeError("Three unclassified original native frames")
            time.sleep(.5)
            state = self.fast_observe(f"retry-state-{unexpected}")
        self.report["status"] = "PARTIAL_NATIVE_GAMEPLAY_ONLY"
        self.save()
        raise RuntimeError("Bounded native fast battle loop ended without victory")

    def cleanup(self) -> None:
        # Native evidence finalization also runs after a partial gameplay result.
        try:
            self.finish_video()
        except Exception as error:
            self.report.setdefault("cleanupErrors", []).append("video: " + str(error)[:300])
        if self.booted:
            try:
                guest = self.device("logcat", "-d", "-v", "epoch",
                                    timeout=35, allow_failure=True).stdout
                if len(guest) > 12 * 1024 * 1024:
                    guest = guest[-12 * 1024 * 1024:]
                    guest = guest[guest.find(b"\n") + 1:]
                    self.report["guestLogcatTailOnly"] = True
                (self.out / "owned-guest-logcat.txt").write_bytes(guest)
                self.report["guestLogcatSha256"] = digest(guest)
                if self.app_pid:
                    self.report["criticalUnityErrors"] = critical_unity_errors(guest, self.app_pid)
            except Exception as error:
                self.report.setdefault("cleanupErrors", []).append("logcat: " + str(error)[:300])
        if self.process is not None:
            try:
                if self.process.poll() is None:
                    owner = self.device("emu", "avd", "name", timeout=12,
                                        allow_failure=True).stdout.decode("utf-8", "replace")
                    if owner.splitlines() and owner.splitlines()[0].strip() == self.avd_name:
                        self.device("emu", "kill", timeout=12, allow_failure=True)
                        self.report["ownedEmulatorNameVerifiedBeforeKill"] = True
                    self.process.wait(timeout=20)
            except Exception:
                if self.process.poll() is None:
                    os.killpg(self.process.pid, signal.SIGTERM)
                    try:
                        self.process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        os.killpg(self.process.pid, signal.SIGKILL)
                        self.process.wait(timeout=5)
            self.report["ownedEmulatorStopped"] = self.process.poll() is not None
        if self.bootlog is not None:
            self.bootlog.close()
        self.report["finishedAtUtc"] = now()
        self.save()

    def run(self) -> None:
        error: Exception | None = None
        try:
            self.inspect_input()
            self.boot()
            alias = self.install()
            self.fast_launch_and_play(alias)
        except Exception as problem:
            error = problem
            self.report["status"] = self.report.get("status") if self.report.get("status") not in ("STARTED", "") else "FAILED_NATIVE_OBSERVATION"
            self.report["errorType"] = type(problem).__name__
            self.report["error"] = str(problem)[:1000]
            self.save()
        finally:
            self.cleanup()
        if error is not None:
            raise error
        if self.report.get("criticalUnityErrors"):
            self.report["status"] = "NATIVE_APP_ERRORS_OBSERVED"
            self.save()
            raise RuntimeError("Critical Unity errors present in original guest logcat")
        if not self.report.get("victoryVisible") or not self.report.get("videos"):
            raise RuntimeError("Victory or original native video missing")
        print(self.report["status"])


if __name__ == "__main__":
    import sys
    if sys.argv[1:] == ["--self-test"]:
        self_test()
    elif len(sys.argv) == 1:
        Probe().run()
    else:
        raise SystemExit("Usage: python run_probe.py [--self-test]")
