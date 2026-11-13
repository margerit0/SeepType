// SPDX-License-Identifier: GPL-3.0-or-later
package org.studyime.android.clipboard

import android.content.ClipDescription
import android.content.ClipboardManager
import android.content.Context
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch

/** The default IME can observe clipboard changes while its service is running. */
class ClipboardMonitor(context: Context, private val repository: ClipboardHistoryRepository) : AutoCloseable {
    private val manager = context.getSystemService(ClipboardManager::class.java)
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private var registered = false
    private var editorKnown = false
    private var protectedEditor = false
    private val listener = ClipboardManager.OnPrimaryClipChangedListener { refresh() }

    init {
        scope.launch {
            repository.state.collect { state ->
                val enabled = state.loaded && state.history.enabled
                if (enabled && !registered) {
                    manager.addPrimaryClipChangedListener(listener)
                    registered = true
                    refresh()
                } else if (!enabled && registered) {
                    manager.removePrimaryClipChangedListener(listener)
                    registered = false
                }
            }
        }
    }

    fun setProtectedEditor(value: Boolean) { editorKnown = true; protectedEditor = value; refresh() }

    fun finishEditor() {
        // Remember a protected clipboard version before leaving that editor,
        // then keep observing copies from non-editable screens while the IME runs.
        if (protectedEditor) refresh()
        editorKnown = true
        protectedEditor = false
    }

    fun refresh() {
        if (!editorKnown || !repository.state.value.history.enabled) return
        try {
            val description = manager.primaryClipDescription ?: return
            if (protectedEditor || description.isSensitive()) {
                repository.ignore(description.timestamp)
                return
            }
            val clip = manager.primaryClip ?: return
            // Recheck the actual clip: it may have changed after reading its description.
            if (clip.description.isSensitive()) { repository.ignore(clip.description.timestamp); return }
            if (clip.itemCount != 1) return
            // Never coerce a URI/Intent to text or open a content provider.
            val item = clip.getItemAt(0)
            if (item.uri != null || item.intent != null) return
            val text = item.text ?: return
            if (text.length > ClipboardHistory.MAX_TEXT_BYTES) return
            repository.record(text.toString(), clip.description.timestamp)
        } catch (_: Exception) {
            // Access can be revoked when the default IME/focus changes. Retry on the next show.
        }
    }

    override fun close() {
        if (registered) manager.removePrimaryClipChangedListener(listener)
        registered = false
        scope.cancel()
    }

    private fun ClipDescription.isSensitive() = extras?.getBoolean("android.content.extra.IS_SENSITIVE", false) == true
}
