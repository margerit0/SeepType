"""Open the native settings editor for the isolated interactive host."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
settings = HERE / 'runtime/interactive-settings.ini'
settings.parent.mkdir(parents=True, exist_ok=True)
raise SystemExit(subprocess.call([str(HERE / 'build/study_settings_x64.exe'), str(settings)],
    cwd=ROOT, creationflags=subprocess.CREATE_NO_WINDOW))
