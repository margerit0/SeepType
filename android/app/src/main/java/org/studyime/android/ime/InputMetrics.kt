// SPDX-License-Identifier: GPL-3.0-or-later
package org.studyime.android.ime

import android.os.SystemClock
import org.json.JSONObject

/** Bounded timing-only counters, with no text, keys, package names or file I/O. */
object InputMetrics {
    private data class Pending(val generation: Long, val revision: Long, val started: Long)
    private val pending = ArrayDeque<Pending>()
    private val main = ArrayDeque<Long>()
    private val drawn = ArrayDeque<Long>()
    private val show = ArrayDeque<Long>()
    private val ready = ArrayDeque<Long>()
    private var requested = 0L
    private var waitingReady = 0L
    private var coalesced = 0
    private fun ArrayDeque<Long>.sample(value: Long) {
        addLast(value)
        if (size > 1024) removeFirst()
    }
    @Synchronized fun result(generation: Long, revision: Long, started: Long) {
        main.sample(SystemClock.elapsedRealtimeNanos() - started)
        pending.addLast(Pending(generation, revision, started))
        while (pending.size > 1024) pending.removeFirst()
    }
    @Synchronized fun showRequested() {
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
            if (key.generation == generation) { drawn.sample(now - key.started); batch++ }
        }
        if (batch > 1) coalesced += batch - 1
        if (requested != 0L) { show.sample(now - requested); requested = 0 }
        if (isReady && waitingReady != 0L) { ready.sample(now - waitingReady); waitingReady = 0 }
    }
    @Synchronized fun reset() {
        pending.clear(); main.clear(); drawn.clear(); show.clear(); ready.clear()
        requested = 0; waitingReady = 0; coalesced = 0
    }
    private fun summary(values: ArrayDeque<Long>): JSONObject {
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
        .put("coalescedKeysBeforeDraw", coalesced).toString()
}
