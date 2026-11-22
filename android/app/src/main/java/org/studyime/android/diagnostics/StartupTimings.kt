// SPDX-License-Identifier: GPL-3.0-or-later
package org.studyime.android.diagnostics

import android.os.SystemClock
import android.os.Debug
import android.os.Trace
import org.json.JSONArray
import org.json.JSONObject

/** Fixed phase names and bounded durations only; never input, candidates or paths. */
object StartupTimings {
    enum class Phase {
        SERVICE_CREATE, START_INPUT, START_INPUT_VIEW, INPUT_VIEW_CREATE, COMPOSITION,
        RESOURCE_OPEN, MANIFEST_READ, RESOURCE_VERIFY, RESOURCE_COPY, RESOURCE_ACTIVATE,
        NATIVE_LIBRARIES, RIME_CREATE, FIRST_DISPATCH, FIRST_MAIN_QUEUE, FIRST_DELIVERY,
    }
    private data class Span(val phase: Phase, val begin: Long, val end: Long, val cpuNanos: Long?)
    private val spans = ArrayDeque<Span>()
    private var started = 0L
    private var ready = 0L

    @Synchronized fun start(): Long {
        spans.clear()
        ready = 0L
        started = SystemClock.elapsedRealtimeNanos()
        return started
    }

    @Synchronized fun record(phase: Phase, begin: Long, end: Long = SystemClock.elapsedRealtimeNanos(), cpuNanos: Long? = null) {
        if (started == 0L || ready != 0L || begin < started || end < begin || spans.size >= 128) return
        spans.addLast(Span(phase, begin, end, cpuNanos))
    }

    fun mark(phase: Phase) {
        val now = SystemClock.elapsedRealtimeNanos()
        record(phase, now, now)
    }

    fun <T> measure(phase: Phase, work: () -> T): T {
        val begin = SystemClock.elapsedRealtimeNanos()
        val cpuBegin = Debug.threadCpuTimeNanos()
        val tracing = Trace.isEnabled()
        if (tracing) Trace.beginSection("StudyIME." + phase.name)
        try { return work() }
        finally {
            val end = SystemClock.elapsedRealtimeNanos()
            val cpuEnd = Debug.threadCpuTimeNanos()
            if (tracing) Trace.endSection()
            record(phase, begin, end, if (cpuBegin >= 0 && cpuEnd >= cpuBegin) cpuEnd - cpuBegin else null)
        }
    }

    @Synchronized fun ready(now: Long) {
        if (started != 0L && ready == 0L) ready = now
    }

    @Synchronized fun report(): JSONObject = JSONObject()
        .put("boundary", "Service onCreate entry to first ready Compose draw; nested/overlapping spans are not additive. Excludes earlier process creation and physical presentation.")
        .put("serviceToReadyMs", if (started != 0L && ready != 0L) (ready - started) / 1_000_000.0 else JSONObject.NULL)
        .put("startedElapsedRealtimeNanos", started)
        .put("readyElapsedRealtimeNanos", ready)
        .put("spans", JSONArray().also { output ->
            spans.forEach { span -> output.put(JSONObject().put("phase", span.phase.name)
                .put("startMs", (span.begin - started) / 1_000_000.0)
                .put("durationMs", (span.end - span.begin) / 1_000_000.0)
                .put("threadCpuMs", span.cpuNanos?.let { it / 1_000_000.0 } ?: JSONObject.NULL)) }
        })
}
