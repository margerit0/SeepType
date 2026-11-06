"""Targeted v0.5 component/render evidence, not Computer Use acceptance."""
from pathlib import Path
from datetime import datetime, timezone, timedelta
import hashlib
import json
import os
import subprocess
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
RUNTIME = HERE / 'runtime/native-v05'
RUNTIME.mkdir(parents=True, exist_ok=True)
FRAMES = RUNTIME / 'frames'
FRAMES.mkdir(exist_ok=True)
for artifact in FRAMES.iterdir():
    if artifact.suffix in {'.json', '.bgra'}:
        artifact.unlink()
checks = RUNTIME / 'checks.json'
checks.unlink(missing_ok=True)
exe = HERE / 'build/native_ui_test_x64.exe'
run = subprocess.run([str(exe), str(checks), str(FRAMES), str(RUNTIME / 'settings.ini')], cwd=ROOT,
    capture_output=True, timeout=50, creationflags=subprocess.CREATE_NO_WINDOW)
(RUNTIME / 'test.log').write_bytes(run.stdout + run.stderr)
print((run.stdout + run.stderr).decode('utf-8', errors='replace').replace('\r\n', '\n'))
items = json.loads(checks.read_text(encoding='utf-8'))['checks'] if checks.exists() else []
preview_dir = HERE / 'results/previews-v05'
preview_dir.mkdir(exist_ok=True)
previews = {}
for metadata in sorted(FRAMES.glob('*.json')):
    data = json.loads(metadata.read_text(encoding='utf-8'))
    pixels = metadata.with_suffix('.bgra').read_bytes()
    assert len(pixels) == data['width'] * data['height'] * 4
    rgba = bytearray(Image.frombytes('RGBA', (data['width'], data['height']), pixels, 'raw', 'BGRA').tobytes())
    # Direct2D uses premultiplied alpha; PNG requires straight color channels.
    for i in range(0, len(rgba), 4):
        alpha = rgba[i + 3]
        if alpha:
            for c in range(3):
                rgba[i + c] = min(255, round(rgba[i + c] * 255 / alpha))
    output = preview_dir / (metadata.stem + '.png')
    Image.frombytes('RGBA', (data['width'], data['height']), bytes(rgba)).save(
        output, dpi=(data['dpi'], data['dpi']))
    previews[str(output.relative_to(ROOT))] = data
sources = list((ROOT / 'src/study/windows').glob('*.cpp')) + list((ROOT / 'src/study/windows').glob('*.h'))
sources += [HERE / 'native_ui_test.cpp', HERE / 'verify-native-ui.py', HERE / 'prepare-tsf.py',
            HERE / 'build-service.py', HERE / 'native-host.manifest']
report = {
    'date': datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds'),
    'scope': 'Production v0.5 layout, DirectWrite rendering, action dispatch, menu construction, preference persistence and time-based animation components; own render buffers only.',
    'passed': run.returncode == 0 and len(items) == 50 and all(item['passed'] for item in items),
    'checks': items, 'exit_code': run.returncode, 'previews': previews,
    'binaries': {str(exe.relative_to(ROOT)): hashlib.sha256(exe.read_bytes()).hexdigest()},
    'sources': {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources},
    'limits': ['No Computer Use or physical mouse/keyboard acceptance', 'No Windows display-setting changes or multi-monitor desktop acceptance',
        'No Notepad/browser/VS Code compatibility evidence', 'No installation or input method registration',
        'Component callbacks alone do not establish TSF document edits; separate native-v05-tsf report covers those'],
}
(HERE / 'results/native-v05.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
if not report['passed']:
    raise SystemExit('Native v0.5 checks failed; inspect runtime/native-v05/test.log')
print(f'{len(items)}/{len(items)} native v0.5 component checks passed.')
