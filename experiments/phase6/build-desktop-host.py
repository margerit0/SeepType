"""Build the acceptance host only; --legacy binds the phase4 IPC instead of dev.2."""
from pathlib import Path
import json
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.packaging.common import CACHE, file_hash, json_bytes

legacy = '--legacy' in sys.argv
work = CACHE / ('desktop-host-legacy' if legacy else 'desktop-host')
work.mkdir(parents=True, exist_ok=True)
cached = ROOT / 'experiments/phase4/build/tsf-x64' if legacy else CACHE / 'build/tsf-x64'
source = ROOT / 'experiments/phase4/tsf_text_host.cpp'
objects = [*sorted((cached / 'ipc').glob('*.obj')),
           *[cached / 'study' / (name + '.obj') for name in
             (['StudyProtocol', 'UiPreferences'] if legacy else ['StudyProtocol', 'UiPreferences', 'ProductRuntime'])]]
boost = cached / 'boost_study.lib' if legacy else CACHE / 'build/boost_study.lib'
includes = [CACHE / 'generated', ROOT / '.cache/study-weasel/include' if legacy else CACHE / 'weasel/include', ROOT / 'src',
            ROOT / '.cache/src/boost_1_84_0']
if legacy:
    includes.append(ROOT / '.cache/src/weasel/include')
flags = ['/nologo', '/std:c++17', '/EHsc', '/O2', '/MT', '/utf-8',
         '/DBOOST_ALL_NO_LIB', '/DBOOST_THREAD_USE_LIB', '/DUNICODE', '/D_UNICODE']
flags += ['/DWEASEL_STUDY_ISOLATED'] if legacy else ['/DWEASEL_STUDY_PRODUCT', '/DSTUDY_PRODUCT_DESKTOP_HOST']
for directory in includes:
    flags += ['/I', str(directory)]
manifest = ROOT / 'experiments/phase4/native-host.manifest'
commands = [
    ['cl', *flags, '/c', source, '/Fo' + str(work / 'host.obj')],
    ['link', '/nologo', '/INCREMENTAL:NO', '/SUBSYSTEM:CONSOLE', '/MANIFEST:EMBED',
     '/MANIFESTINPUT:' + str(manifest), '/OUT:' + str(work / 'StudyIME.DesktopHost.exe'),
     work / 'host.obj', *objects, boost, 'user32.lib', 'gdi32.lib', 'comctl32.lib',
     'ole32.lib', 'oleacc.lib', 'advapi32.lib', 'shell32.lib', 'imm32.lib',
     'uuid.lib', 'oleaut32.lib']]
for index, command in enumerate(commands):
    with (work / f'build-{index}.log').open('wb') as log:
        result = subprocess.run([str(arg) for arg in command], cwd=ROOT,
                                stdout=log, stderr=subprocess.STDOUT)
    if result.returncode:
        print((work / f'build-{index}.log').read_text(encoding='utf-8', errors='replace'))
        raise SystemExit(result.returncode)
inputs = [source, ROOT / 'experiments/phase4/text_store.h', manifest,
          Path(__file__), Path(__file__).with_suffix('.cmd'),
          CACHE / 'generated/ProductIdentity.h', *objects, boost]
(work / 'build.json').write_bytes(json_bytes({
    'inputs': {p.relative_to(ROOT).as_posix(): file_hash(p) for p in inputs},
    'executable_sha256': file_hash(work / 'StudyIME.DesktopHost.exe'),
    'toolset': os.environ.get('VCToolsVersion'), 'sdk': os.environ.get('WindowsSDKVersion'),
    'product_rebuilt': False, 'legacy_experiment': legacy,
}))
print('Built the ' + ('legacy' if legacy else 'product') + ' desktop host only.')
