// SPDX-License-Identifier: GPL-3.0-or-later
package org.studyime.android.clipboard

import java.security.MessageDigest
import java.util.UUID

data class ClipboardEntry(val id: String, val text: String, val copiedAt: Long, val pinned: Boolean = false)

/** Bounded, exact-text history. Clipboard identity survives deletion and process restarts. */
data class ClipboardHistory(
    val enabled: Boolean = false,
    val entries: List<ClipboardEntry> = emptyList(),
    val lastTimestamp: Long = -1,
    val lastDigest: String? = null,
) {
    fun setEnabled(value: Boolean) = copy(enabled = value, entries = if (value) entries else emptyList())

    fun record(text: String, timestamp: Long, now: Long = System.currentTimeMillis()): ClipboardHistory {
        if (!enabled || !accepts(text)) return this
        val digest = MessageDigest.getInstance("SHA-256").digest(text.toByteArray(Charsets.UTF_8))
            .joinToString("") { "%02x".format(it) }
        // A null digest marks a clipboard version ignored in a protected editor.
        if (timestamp == lastTimestamp && (lastDigest == null || lastDigest == digest)) return this
        val previous = entries.firstOrNull { it.text == text }
        val entry = previous?.copy(copiedAt = now) ?: ClipboardEntry(UUID.randomUUID().toString(), text, now)
        return copy(entries = ordered(listOf(entry) + entries.filterNot { it.text == text }),
            lastTimestamp = timestamp, lastDigest = digest)
    }

    fun ignore(timestamp: Long) = if (enabled) copy(lastTimestamp = timestamp, lastDigest = null) else this
    fun remove(id: String) = copy(entries = entries.filterNot { it.id == id })
    fun clear() = copy(entries = emptyList())

    fun togglePin(id: String): ClipboardHistory {
        val entry = entries.firstOrNull { it.id == id } ?: return this
        if (!entry.pinned && entries.count { it.pinned } >= MAX_PINNED) return this
        return copy(entries = ordered(entries.map { if (it.id == id) it.copy(pinned = !it.pinned) else it }))
    }

    companion object {
        const val MAX_ENTRIES = 50
        const val MAX_PINNED = 10
        // The engine's literal event accepts at most 4096 UTF-8 bytes. Never truncate a clip.
        const val MAX_TEXT_BYTES = 4096
        fun accepts(text: String) = text.length <= MAX_TEXT_BYTES && text.isNotBlank() && '\u0000' !in text && validUnicode(text) &&
            text.toByteArray(Charsets.UTF_8).size <= MAX_TEXT_BYTES

        private fun validUnicode(text: String): Boolean {
            var index = 0
            while (index < text.length) {
                val char = text[index++]
                if (char.isHighSurrogate()) {
                    if (index == text.length || !text[index++].isLowSurrogate()) return false
                } else if (char.isLowSurrogate()) return false
            }
            return true
        }

        private fun ordered(entries: List<ClipboardEntry>) = entries.sortedWith(
            compareByDescending<ClipboardEntry> { it.pinned }.thenByDescending { it.copiedAt }
        ).take(MAX_ENTRIES)
    }
}
