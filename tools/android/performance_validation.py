"""Validate the full fixed input sequence, independently of reported pass flags."""
# SPDX-License-Identifier: GPL-3.0-or-later
import math

PHASES = ("workerQueue", "initialize", "nativeDispatch", "snapshotParse", "mainQueue",
          "inputConnection", "awaitComposition", "composition", "applyComposition", "layoutAndDraw")


def percentile(values, fraction):
    return sorted(values)[math.ceil(len(values) * fraction) - 1]


def assess_performance(report):
    """Keep coverage and latency separate; neither trusts the device's booleans."""
    try:
        return _assess_performance(report)
    except (AttributeError, TypeError, ValueError, KeyError, OverflowError) as error:
        return {"coverageComplete": False, "coverageErrors": ["Malformed performance report: " + str(error)],
                "timingTargets": {}, "timingTargetsMet": False}


def _assess_performance(report):
    errors = []
    metrics = report.get("warmTimings", {})

    def require(condition, message):
        if not condition:
            errors.append(message)

    require(report.get("passed") is True, "Instrumentation did not complete successfully")
    first, last = report.get("initialImePid"), report.get("finalImePid")
    require(isinstance(first, str) and first.isdigit() and first == last,
            "The IME process changed or its identity is missing")
    for key, count in (("keyToDeliveryMs", 180), ("keyToComposeDrawMs", 180),
                       ("showInputViewToDrawMs", 20), ("showInputViewToReadyDrawMs", 20)):
        require(metrics.get(key, {}).get("samples") == count, f"{key} must contain exactly {count} samples")
    for key in ("coalescedKeysBeforeDraw", "discardedBeforeDraw", "pendingDraws", "invalidPhasePairs"):
        require(metrics.get(key) == 0, key + " must be zero")
    require(metrics.get("showRequests") == 20, "Exactly 20 keyboard reopenings are required")
    for key in ("pendingShowDraw", "pendingReadyDraw"):
        require(metrics.get(key) is False, key + " must be false")
    words = report.get("syntheticWordObservations", [])
    require(len(words) == 30 and all(
        item.get("iteration") == index + 1 and item.get("syntheticEditorText") == "nihao" * (index + 2)
        for index, item in enumerate(words)), "Every word must be committed once in order")
    require(report.get("syntheticFinalText") == "nihao" * 31, "Final synthetic editor text differs")
    reopenings = report.get("reopeningObservations", [])
    require(len(reopenings) == 20 and all(
        item.get("iteration") == index + 1 and item.get("showRequests") == index + 1
        and item.get("readyDraws") == index + 1 and item.get("pendingReadyDraw") is False
        for index, item in enumerate(reopenings)), "Each reopening must finish before the next hide")
    require(metrics.get("phaseOrder") == list(PHASES), "Timing phase order is missing or different")
    rows = metrics.get("pairedKeySamplesMs", [])
    valid_rows = isinstance(rows, list) and len(rows) == 180 and all(
        isinstance(row, list) and len(row) == len(PHASES) and all(
            isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and value >= 0 for value in row) for row in rows)
    require(valid_rows, "Exactly 180 complete, finite and nonnegative phase pairs are required")
    if valid_rows:
        for key, values in (("keyToDeliveryMs", [sum(row[:6]) for row in rows]),
                            ("keyToComposeDrawMs", [sum(row) for row in rows])):
            summary = metrics.get(key, {})
            for name, fraction in (("p50", .5), ("p95", .95), ("p99", .99), ("max", 1)):
                actual = summary.get(name)
                require(isinstance(actual, (int, float)) and math.isfinite(actual)
                        and math.isclose(actual, percentile(values, fraction), abs_tol=0.000001),
                        f"{key}.{name} disagrees with the paired samples")

    def within(key, name, limit):
        value = metrics.get(key, {}).get(name)
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and 0 <= value <= limit

    targets = {
        "candidateDrawP95Target50Ms": within("keyToComposeDrawMs", "p95", 50),
        "candidateDrawP99Target100Ms": within("keyToComposeDrawMs", "p99", 100),
        "warmReadyP95Target100Ms": within("showInputViewToReadyDrawMs", "p95", 100),
    }
    return {"coverageComplete": not errors, "coverageErrors": errors,
            "timingTargets": targets, "timingTargetsMet": all(targets.values())}
