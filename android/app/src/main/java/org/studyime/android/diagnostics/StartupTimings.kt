// SPDX-License-Identifier: GPL-3.0-or-later
package org.studyime.android.diagnostics

import android.os.SystemClock
import org.json.JSONArray
import org.json.JSONObject

/** Fixed phase names and bounded durations only; never input, candidates or paths. */
object StartupTimings {
    enum class Phase {
        SERVICE_CREATE, START_INPUT, START_INPUT_VIEW, INPUT_VIEW_CREATE, COMPOSITION,
        RESOURCE_OPEN, MANIFEST_READ, RESOURCE_VERIFY, RESOURCE_COPY, RESOURCE_ACTIVATE,
        NATIVE_LIBRARIES, RIME_CREATE, FIRST_DISPATCH, FIRST_MAIN_QUEUE, FIRST_DELIVERY,
    }
    private data class Span(val phase: Phase, val begin: Long, val end: Long)
    private val spans = ArrayDeque<Span>()
    private var started = 0L
    private var ready = 0L

    @Synchronized fun start(): Long {
        spans.clear()
        ready = 0L
        started = SystemClock.elapsedRealtimeNanos()
        return started
    }

    @Synchronized fun record(phase: Phase, begin: Long, end: Long = SystemClock.elapsedRealtimeNanos()) {
        if (started == 0L || ready != 0L || begin < started || end < begin || spans.size >= 128) return
        spans.addLast(Span(phase, begin, end))
    }

    fun mark(phase: Phase) {
        val now = SystemClock.elapsedRealtimeNanos()
        record(phase, now, now)
    }

    fun <T> measure(phase: Phase, work: () -> T): T {
        val begin = SystemClock.elapsedRealtimeNanos()
        try { return work() }
        finally { record(phase, begin) }
    }

    @Synchronized fun ready(now: Long) {
        if (started != 0L && ready == 0L) ready = now
    }

    @Synchronized fun report(): JSONObject = JSONObject()
        .put("boundary", "Service onCreate entry to first ready Compose draw; nested/overlapping spans are not additive. Excludes earlier process creation and physical presentation.")
        .put("serviceToReadyMs", if (started != 0L && ready != 0L) (ready - started) / 1_000_000.0 else JSONObject.NULL)
        .put("spans", JSONArray().also { output ->
            spans.forEach { span -> output.put(JSONObject().put("phase", span.phase.name)
                .put("startMs", (span.begin - started) / 1_000_000.0)
                .put("durationMs", (span.end - span.begin) / 1_000_000.0)) }
        })
}
