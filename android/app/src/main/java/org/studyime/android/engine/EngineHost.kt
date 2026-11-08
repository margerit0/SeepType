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

/** One serial worker owns the entire native lifetime. UI owns InputConnection. */
class EngineHost(context: Context) : AutoCloseable {
    private val app = context.applicationContext
    private val thread = HandlerThread("StudyRime", Process.THREAD_PRIORITY_DISPLAY).apply { start() }
    private val worker = Handler(thread.looper)
    private val main = Handler(Looper.getMainLooper())
    private val active = AtomicLong(0)
    private var handle = 0L
    @Volatile private var closed = false
    var onSnapshot: (EngineSnapshot, Long) -> Unit = { _, _ -> }
    var onFailure: () -> Unit = {}

    private fun initialize() {
        if (handle != 0L) return
        val deployer = DataDeployer(app)
        val resources = deployer.prepare()
        fun create(value: DataDeployer.Resources) = NativeCore.create(value.shared.path, value.user.path, value.build.path)
        handle = try {
            create(resources).also { check(it != 0L); deployer.markReady(resources) }
        } catch (error: Exception) {
            val previous = deployer.previous()?.takeIf { it.version != resources.version } ?: throw error
            create(previous).also { check(it != 0L) }
        }
    }

    fun begin(config: JSONObject): Long {
        val generation = nextGeneration.incrementAndGet()
        active.set(generation) // Invalidates queued results before any worker task can complete.
        submit(generation, event("start", "config" to config))
        return generation
    }

    fun invalidate() { active.set(nextGeneration.incrementAndGet()) }

    fun submit(generation: Long, command: JSONObject) {
        if (closed || active.get() != generation) return
        command.put("generation", generation)
        val encoded = command.toString() // Immutable message; caller may reuse its JSON object.
        val started = SystemClock.elapsedRealtimeNanos()
        worker.post {
            if (closed || active.get() != generation) return@post
            try {
                initialize()
                if (closed || active.get() != generation) return@post
                val snapshot = EngineSnapshot.parse(NativeCore.dispatch(handle, encoded))
                main.post {
                    if (!closed && active.get() == generation && snapshot.generation == generation) {
                        onSnapshot(snapshot, started)
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
