// SPDX-License-Identifier: GPL-3.0-or-later
package org.studyime.android.engine

import android.content.Context
import android.os.Handler
import android.os.HandlerThread
import android.os.Looper
import android.os.Process
import android.os.SystemClock
import java.util.concurrent.atomic.AtomicLong
import org.json.JSONObject
import org.studyime.android.diagnostics.StartupTimings
import org.studyime.android.diagnostics.StartupTimings.Phase

data class DispatchTiming(
    val enqueued: Long, val worker: Long, val initialized: Long,
    val dispatched: Long, val parsed: Long, val main: Long,
)

/** One serial worker owns the entire native lifetime. UI owns InputConnection. */
class EngineHost(context: Context) : AutoCloseable {
    private val app = context.applicationContext
    private val thread = HandlerThread("StudyRime", Process.THREAD_PRIORITY_DISPLAY).apply { start() }
    private val worker = Handler(thread.looper)
    // A traversal barrier must not hold an already computed input result for
    // another frame. Callbacks remain serial on the main thread and gated by
    // the editor generation, including after disconnect/close.
    private val main = Handler.createAsync(Looper.getMainLooper())
    private val active = AtomicLong(0)
    private var handle = 0L
    @Volatile private var closed = false
    var onSnapshot: (EngineSnapshot, DispatchTiming, String) -> Unit = { _, _, _ -> }
    var onFailure: () -> Unit = {}

    private fun initialize() {
        if (handle != 0L) return
        val deployer = DataDeployer(app)
        handle = StartupTimings.measure(Phase.RESOURCE_OPEN) {
            deployer.open(initialize = { value ->
                NativeCore.ensureLoaded()
                StartupTimings.measure(Phase.RIME_CREATE) {
                    NativeCore.create(value.shared.path, value.user.path, value.build.path).also { check(it != 0L) }
                }
            }, close = NativeCore::destroy)
        }
    }

    fun begin(config: JSONObject, previous: EngineSnapshot? = null): Long {
        val generation = nextGeneration.incrementAndGet()
        active.set(generation) // Invalidates queued results before any worker task can complete.
        submit(generation, if (previous == null) event("start", "config" to config) else
            event("restart", "config" to config, "previousGeneration" to previous.generation, "revision" to previous.revision))
        return generation
    }

    fun invalidate() { active.set(nextGeneration.incrementAndGet()) }

    fun submit(generation: Long, command: JSONObject) {
        if (closed || active.get() != generation) return
        command.put("generation", generation)
        val encoded = command.toString() // Immutable message; caller may reuse its JSON object.
        val type = command.optString("type")
        val started = SystemClock.elapsedRealtimeNanos()
        worker.post {
            if (closed || active.get() != generation) return@post
            try {
                val workerStarted = SystemClock.elapsedRealtimeNanos()
                initialize()
                val initialized = SystemClock.elapsedRealtimeNanos()
                if (closed || active.get() != generation) return@post
                val raw = NativeCore.dispatch(handle, encoded)
                val dispatched = SystemClock.elapsedRealtimeNanos()
                if (type == "start" || type == "restart") StartupTimings.record(Phase.FIRST_DISPATCH, initialized, dispatched)
                val snapshot = EngineSnapshot.parse(raw)
                val parsed = SystemClock.elapsedRealtimeNanos()
                main.post {
                    if (!closed && active.get() == generation && snapshot.generation == generation) {
                        if (type == "start" || type == "restart") StartupTimings.record(Phase.FIRST_MAIN_QUEUE, parsed)
                        onSnapshot(snapshot, DispatchTiming(started, workerStarted, initialized, dispatched, parsed,
                            SystemClock.elapsedRealtimeNanos()), type)
                    }
                }
            } catch (_: Exception) {
                // Error codes are shown as a local recovery state. Never log input or JSON.
                main.post { if (!closed && active.get() == generation) onFailure() }
            }
        }
    }

    override fun close() {
        closed = true
        invalidate()
        worker.post {
            try { if (handle != 0L) NativeCore.destroy(handle) }
            finally { handle = 0; thread.quitSafely() }
        }
    }
    companion object { private val nextGeneration = AtomicLong(0) }
}
