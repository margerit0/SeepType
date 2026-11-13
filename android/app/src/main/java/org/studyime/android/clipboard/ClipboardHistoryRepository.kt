// SPDX-License-Identifier: GPL-3.0-or-later
package org.studyime.android.clipboard

import android.content.Context
import java.io.File
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

data class ClipboardHistoryState(
    val history: ClipboardHistory = ClipboardHistory(),
    val loaded: Boolean = false,
    val storageError: Boolean = false,
)

/** One app-wide queue orders loading, recording, deletion and settings changes. No disk I/O on keys. */
class ClipboardHistoryRepository private constructor(context: Context) {
    private val changes = Channel<(ClipboardHistory) -> ClipboardHistory>(Channel.UNLIMITED)
    private val mutable = MutableStateFlow(ClipboardHistoryState())
    val state: StateFlow<ClipboardHistoryState> = mutable

    init {
        val app = context.applicationContext
        CoroutineScope(SupervisorJob() + Dispatchers.IO).launch {
            val storage = ClipboardHistoryFile(File(app.noBackupFilesDir, "clipboard/history-v1.json"))
            var history = try { storage.read() } catch (_: Exception) {
                // Never log clipboard data. Corrupt/unsupported data fails closed.
                mutable.value = ClipboardHistoryState(storageError = true)
                ClipboardHistory()
            }
            mutable.value = mutable.value.copy(history = history, loaded = true)
            for (change in changes) {
                val next = change(history)
                if (next == history && !mutable.value.storageError) continue
                try {
                    storage.write(next)
                    history = next
                    mutable.value = ClipboardHistoryState(history, loaded = true)
                } catch (_: Exception) {
                    // Do not claim that deletion/disable succeeded when it was not persisted.
                    mutable.value = mutable.value.copy(storageError = true)
                }
            }
        }
    }

    fun setEnabled(enabled: Boolean) { changes.trySend { it.setEnabled(enabled) } }
    fun record(text: String, timestamp: Long) { changes.trySend { it.record(text, timestamp) } }
    fun ignore(timestamp: Long) { changes.trySend { it.ignore(timestamp) } }
    fun remove(id: String) { changes.trySend { it.remove(id) } }
    fun togglePin(id: String) { changes.trySend { it.togglePin(id) } }
    fun clear() { changes.trySend { it.clear() } }

    companion object {
        @Volatile private var instance: ClipboardHistoryRepository? = null
        fun get(context: Context): ClipboardHistoryRepository = instance ?: synchronized(this) {
            instance ?: ClipboardHistoryRepository(context).also { instance = it }
        }
    }
}
