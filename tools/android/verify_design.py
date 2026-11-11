"""Measure actual Compose colors and captured Android accessibility touch bounds."""
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.android.common import CACHE, ROOT, digest, json_write


def luminance(hex_rgb):
    values = [int(hex_rgb[index:index + 2], 16) / 255 for index in (0, 2, 4)]
    rgb = [value / 12.92 if value <= .04045 else ((value + .055) / 1.055) ** 2.4 for value in values]
    return sum(value * weight for value, weight in zip(rgb, (.2126, .7152, .0722)))


def verify():
    source = ROOT / "android/app/src/main/java/org/studyime/android/ui/Theme.kt"
    body = source.read_text(encoding="utf-8")
    names = ["paper", "ink", "subtle", "line", "board", "key", "function", "accent", "tint", "onAccent"]
    combinations = [(foreground, background) for foreground, backgrounds in {
        "ink": ["paper", "board", "key", "function", "tint"],
        "subtle": ["paper", "board", "key"],
        "accent": ["paper", "board", "tint"], "onAccent": ["accent"],
    }.items() for background in backgrounds]
    contrasts = []
    for theme in ("Light", "Dark"):
        declaration = body.split("val " + theme + "Colors = StudyColors", 1)[1].split("\nval ", 1)[0]
        values = re.findall(r"Color\(0xFF([0-9A-Fa-f]{6})\)|Color\.(White)", declaration)
        colors = dict(zip(names, [value or "FFFFFF" for value, _ in values], strict=True))
        for foreground, background in combinations:
            bright, dark = sorted([luminance(colors[foreground]), luminance(colors[background])], reverse=True)
            ratio = (bright + .05) / (dark + .05)
            contrasts.append({"theme": theme, "foreground": foreground, "background": background,
                              "colors": [colors[foreground], colors[background]], "ratio": round(ratio, 2), "passed": ratio >= 4.5})
    path = CACHE / "evidence/visual/320dp-font1.0-light.xml"
    tree = ET.parse(path).getroot()
    parents = {child: parent for parent in tree.iter() for child in parent}
    touch = []
    for node in tree.iter("node"):
        if node.get("content-desc") not in ("切换浅深色", "查看完整释义", "展开候选", "显示英文释义"):
            continue
        target = node
        while target.get("clickable") != "true" and target in parents:
            target = parents[target]
        left, top, right, bottom = map(int, re.findall(r"\d+", target.get("bounds", "")))
        touch.append({"button": node.get("content-desc"), "widthDp": (right - left) / 2, "heightDp": (bottom - top) / 2,
                      "passed": (right - left) >= 96 and (bottom - top) >= 96})
    result = {"scope": "WCAG relative luminance from shipped Compose constants; touch bounds from real 320 dp / density 320 screenshot hierarchy",
              "sourceSha256": digest(source), "hierarchySha256": digest(path), "contrasts": contrasts, "toolTouchBounds": touch,
              "passed": all(item["passed"] for item in contrasts + touch) and len(touch) == 4}
    json_write(CACHE / "evidence/design-measurements.json", result)
    print(json.dumps({"passed": result["passed"], "lowestTextContrast": min(item["ratio"] for item in contrasts), "toolButtons": len(touch)}))
    if not result["passed"]:
        raise SystemExit("Design measurement failed; see preserved report")


if __name__ == "__main__":
    verify()
