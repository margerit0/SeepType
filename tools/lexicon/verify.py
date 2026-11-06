"""Record data-pipeline test results independently of native/UI evidence."""
from datetime import datetime, timezone
from pathlib import Path
import platform
import sys
import unittest

import pipeline as p


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


suite = unittest.defaultTestLoader.discover(str(Path(__file__).parent), pattern="test_*.py")
result = unittest.TextTestRunner(verbosity=1, resultclass=Result).run(suite)
paths = list(Path(__file__).parent.glob("*.py")) + [Path(__file__).with_name("review.html")]
paths += [p.DATA / "entries.json", p.DATA / "source.lock.json", p.DATA / "sources/entries.json",
          p.DATA / "licenses/CC-BY-SA-4.0.txt", p.DATA / "NOTICE.txt"]
report = {"date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
          "scope": "Pinned data validation, review invalidation, import atomicity and deterministic export; synthetic approval fixtures only.",
          "python": platform.python_version(), "passed": result.wasSuccessful() and result.testsRun >= 25,
          "checks": result.checks, "test_count": result.testsRun,
          "product_review_counts": p.validate().counts,
          "sources": {str(path.relative_to(p.ROOT)): p.sha256(path.read_bytes()) for path in paths},
          "limits": ["No human approval of product entries", "No browser/desktop interaction acceptance",
                     "No native input method installation or application compatibility evidence"]}
p.atomic_write(p.ROOT / "experiments/phase5/results/lexicon-pipeline.json", p.json_bytes(report))
sys.exit(0 if report["passed"] else 1)
