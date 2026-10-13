# Crackveil Build 2 native skill glyph fixture

`skill-slash-r10.png` is an unaltered 91×87 crop of original Android KVM run
38344629894's `native-frames/014-skill-ready.png`, rectangle
`[1766, 912, 1857, 999]`. The full frame SHA-256 is
`3ce1721883d301a5458b81ca8963c4f8dc7976f82a6f15f6bc6911882643eb33`;
the crop SHA-256 is
`c4ec576a55a7e69105481d6a4d1f9fae02c1e1050f5a01cd631f96fef3749352`.
R10's original OCR located the lower-right `斬` label in this region before a
normal skill tap; the original runtime artifact ID is 11788632420.

On the original R11 `014-skill-ready.png`, Tesseract missed that visible
button glyph; the fixed-position grayscale normalized correlation is 0.98946.
The same template against R10's post-skill `019-pause-menu.png`, when the
button displays `旋`, scores 0.24808. The probe accepts this fallback only
above 0.94 on the fixed 1920×1080 screen and records the score and both frame
hashes. It never chooses a button coordinate without a verified visual match.
