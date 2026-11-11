// SPDX-License-Identifier: GPL-3.0-or-later
package org.studyime.android.ime

import android.os.SystemClock
import org.json.JSONArray
import org.json.JSONObject
import org.studyime.android.diagnostics.StartupTimings
import org.studyime.android.engine.DispatchTiming

/** Bounded timing-only counters, with no text, keys, package names or file I/O. */
object InputMetrics {
    private data class Pending(val generation: Long, val revision: Long, val timing: DispatchTiming,
        val delivered: Long, var compositionBegin: Long = 0, var compositionEnd: Long = 0, var applied: Long = 0)
    private val pending = ArrayDeque<Pending>()
    private val main = ArrayDeque<Long>()
    private val drawn = ArrayDeque<Long>()
    private val show = ArrayDeque<Long>()
    private val ready = ArrayDeque<Long>()
    private val paired = ArrayDeque<LongArray>()
    private val phaseNames = listOf("workerQueue", "initialize", "nativeDispatch", "snapshotParse", "mainQueue",
        "inputConnection", "awaitComposition", "composition", "applyComposition", "layoutAndDraw")
    private var requested = 0L
    private var waitingReady = 0L
    private var coalesced = 0
    private var discarded = 0
    private var invalidPairs = 0
    private var showRequests = 0
    private fun ArrayDeque<Long>.sample(value: Long) {
        addLast(value)
        if (size > 1024) removeFirst()
    }
    @Synchronized fun result(generation: Long, revision: Long, timing: DispatchTiming) {
        val now = SystemClock.elapsedRealtimeNanos()
        main.sample(now - timing.enqueued)
        pending.addLast(Pending(generation, revision, timing, now))
        while (pending.size > 1024) { pending.removeFirst(); discarded++ }
    }
    @Synchronized fun composed(generation: Long, revision: Long, begin: Long, end: Long) {
        val now = SystemClock.elapsedRealtimeNanos()
        pending.forEach { key ->
            if (key.generation == generation && key.revision <= revision && key.applied == 0L) {
                key.compositionBegin = begin; key.compositionEnd = end; key.applied = now
            }
        }
    }
    @Synchronized fun showRequested() {
        showRequests++
        requested = SystemClock.elapsedRealtimeNanos()
        waitingReady = requested
    }
    @Synchronized fun frame(generation: Long, revision: Long, isReady: Boolean) {
        val now = SystemClock.elapsedRealtimeNanos()
        var batch = 0
        while (pending.isNotEmpty()) {
            val key = pending.first()
            if (key.generation > generation || (key.generation == generation && key.revision > revision)) break
            pending.removeFirst()
            if (key.generation == generation) {
                drawn.sample(now - key.timing.enqueued)
                batch++
                val t = key.timing
                val points = longArrayOf(t.enqueued, t.worker, t.initialized, t.dispatched, t.parsed, t.main,
                    key.delivered, key.compositionBegin, key.compositionEnd, key.applied, now)
                if (points.indices.drop(1).all { points[it] >= points[it - 1] }) {
                    paired.addLast(LongArray(points.size - 1) { points[it + 1] - points[it] })
                    if (paired.size > 1024) paired.removeFirst()
                } else invalidPairs++
            } else discarded++
        }
        if (batch > 1) coalesced += batch - 1
        if (requested != 0L) { show.sample(now - requested); requested = 0 }
        if (isReady && waitingReady != 0L) { ready.sample(now - waitingReady); waitingReady = 0 }
        if (isReady) StartupTimings.ready(now)
    }
    @Synchronized fun reset() {
        pending.clear(); main.clear(); drawn.clear(); show.clear(); ready.clear(); paired.clear()
        requested = 0; waitingReady = 0; coalesced = 0; discarded = 0; invalidPairs = 0; showRequests = 0
    }
    private fun summary(values: Collection<Long>): JSONObject {
        val sorted = values.sorted()
        val result = JSONObject().put("samples", sorted.size)
        if (sorted.isNotEmpty()) {
            fun percentile(p: Double) = sorted[(kotlin.math.ceil(sorted.size * p).toInt() - 1).coerceIn(0, sorted.lastIndex)] / 1_000_000.0
            result.put("p50", percentile(.5)).put("p95", percentile(.95)).put("p99", percentile(.99)).put("max", percentile(1.0))
        }
        return result
    }
    @Synchronized fun report(): String = JSONObject()
        .put("boundary", "Key callback enqueue -> InputConnection delivery / Compose draw recording. Excludes touch recognition, GPU presentation and physical display latency.")
        .put("keyToDeliveryMs", summary(main)).put("keyToComposeDrawMs", summary(drawn))
        .put("showInputViewToDrawMs", summary(show)).put("showInputViewToReadyDrawMs", summary(ready))
        .put("showRequests", showRequests).put("pendingShowDraw", requested != 0L).put("pendingReadyDraw", waitingReady != 0L)
        .put("coalescedKeysBeforeDraw", coalesced).put("discardedBeforeDraw", discarded)
        .put("pendingDraws", pending.size).put("invalidPhasePairs", invalidPairs)
        .put("phaseOrder", JSONArray(phaseNames))
        .put("keyPhasesMs", JSONObject().also { phases -> phaseNames.forEachIndexed { index, name ->
            phases.put(name, summary(paired.map { it[index] }))
        } })
        .put("pairedKeySamplesMs", JSONArray().also { rows -> paired.forEach { values ->
            rows.put(JSONArray(values.map { it / 1_000_000.0 }))
        } })
        .put("startup", StartupTimings.report()).toString()
}
