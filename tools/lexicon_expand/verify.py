"""Run isolated offline checks and record which code/data they verified."""
from datetime import datetime, timezone
from pathlib import Path
import platform
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.lexicon import pipeline as legacy
from tools.lexicon_expand.common import DATA, ROOT, digest, write_json


class Result(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.checks = []

    def addSuccess(self, test):
        super().addSuccess(test)
        self.checks.append({"name": test.id(), "passed": True})

    def addFailure(self, test, error):
        super().addFailure(test, error)
        self.checks.append({"name": test.id(), "passed": False})

    def addError(self, test, error):
        super().addError(test, error)
        self.checks.append({"name": test.id(), "passed": False})


def main():
    directory = Path(__file__).parent
    suite = unittest.defaultTestLoader.discover(str(directory), pattern="test_*.py")
    result = unittest.TextTestRunner(verbosity=1, resultclass=Result).run(suite)
    paths = list(directory.glob("*.py")) + [directory / "prompt.txt"]
    paths += [path for path in DATA.rglob("*") if path.is_file() and path.name != "README.md"]
    paths += [legacy.DATA / "entries.json", legacy.DATA / "source.lock.json"]
    report = {
        "date": datetime.now(timezone.utc).isoformat(timespec="seconds"), "python": platform.python_version(),
        "passed": result.wasSuccessful() and result.testsRun >= 36, "test_count": result.testsRun,
        "checks": result.checks, "real_model_requests": 0, "new_product_translations": 0,
        "existing_review_counts": legacy.validate().counts,
        "inputs": {path.relative_to(ROOT).as_posix(): digest(path.read_bytes()) for path in sorted(paths)},
        "scope": "Pinned target lists, exact dictionary references, deterministic request planning, strict response schema, mocked external transport, credential handling and bounded resumable generation.",
        "limits": ["API transport is mocked; no real endpoint/model compatibility has been established",
                   "No new word meanings were generated or human-approved",
                   "No native input method, installed files or runtime import was exercised"],
    }
    write_json(ROOT / "experiments/lexicon-expansion/results/offline-checks.json", report)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
