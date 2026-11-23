"""Run isolated offline checks and record which code/data they verified."""
from datetime import datetime, timezone
from pathlib import Path
import platform
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.lexicon import pipeline as legacy
from tools.lexicon_expand.common import CACHE, DATA, ROOT, digest, generated_directory, write_json


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

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.checks.append({"name": test.id(), "skipped": reason})


def main():
    directory = Path(__file__).parent
    suite = unittest.defaultTestLoader.discover(str(directory), pattern="test_*.py")
    result = unittest.TextTestRunner(verbosity=1, resultclass=Result).run(suite)
    paths = list(directory.glob("*.py")) + [directory / "prompt.txt"] + list(directory.glob('prompts/*.txt'))
    paths += [path for path in DATA.rglob("*") if path.is_file() and path.name != "README.md"
              and not path.is_relative_to(DATA / "reviews")]
    paths += [legacy.DATA / "entries.json", legacy.DATA / "source.lock.json"]
    report = {
        "date": datetime.now(timezone.utc).isoformat(timespec="seconds"), "python": platform.python_version(),
        "passed": result.wasSuccessful() and result.testsRun - len(result.skipped) >= 36,
        "test_count": result.testsRun, "skipped_count": len(result.skipped),
        "checks": result.checks, "real_model_requests": 0, "new_product_translations": 0,
        "existing_review_counts": legacy.validate().counts,
        "inputs": {path.relative_to(ROOT).as_posix(): digest(path.read_bytes()) for path in sorted(paths)},
        "scope": "Pinned sources, versioned prompt snapshots and response formats, per-sense English case, pronunciation quarantine, targeted repair planning, held-out comparison plans, mocked transport and bounded resumable generation.",
        "limits": ["API transport is mocked; no real endpoint/model compatibility has been established",
                   "No new word meanings were generated or human-approved",
                   "No native input method, installed files or runtime import was exercised"],
    }
    write_json(generated_directory(CACHE / "verification") / "offline-checks.json", report)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
