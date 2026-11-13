// SPDX-License-Identifier: GPL-3.0-or-later
package org.studyime.android.clipboard

import android.util.AtomicFile
import java.io.File
import org.json.JSONArray
import org.json.JSONObject

/** Called only by the repository's serial I/O worker, under noBackupFilesDir. */
internal class ClipboardHistoryFile(private val file: File) {
    private val atomic = AtomicFile(file)

    fun read(): ClipboardHistory {
        if (!file.exists() && !File(file.path + ".bak").exists()) return ClipboardHistory()
        val bytes = atomic.openRead().use { input ->
            val buffer = ByteArray(MAX_FILE_BYTES + 1)
            var size = 0
            while (size < buffer.size) {
                val count = input.read(buffer, size, buffer.size - size)
                if (count < 0) break
                size += count
            }
            require(size <= MAX_FILE_BYTES)
            buffer.copyOf(size)
        }
        val data = JSONObject(bytes.toString(Charsets.UTF_8))
        require(data.getInt("version") == 1)
        val enabled = data.getBoolean("enabled")
        val records = data.getJSONArray("entries")
        require(records.length() <= ClipboardHistory.MAX_ENTRIES)
        val entries = (0 until records.length()).map { index ->
            val value = records.getJSONObject(index)
            ClipboardEntry(value.getString("id"), value.getString("text"), value.getLong("copiedAt"), value.getBoolean("pinned"))
                .also { require(it.id.length in 1..64 && ClipboardHistory.accepts(it.text) && it.copiedAt >= 0) }
        }
        require(entries.distinctBy { it.id }.size == entries.size && entries.distinctBy { it.text }.size == entries.size)
        require(entries.count { it.pinned } <= ClipboardHistory.MAX_PINNED)
        require(enabled || entries.isEmpty())
        val digest = data.optString("lastDigest").takeIf { it.isNotEmpty() }
        require(digest == null || digest.matches(Regex("[0-9a-f]{64}")))
        return ClipboardHistory(enabled, entries, data.optLong("lastTimestamp", -1), digest)
    }

    fun write(history: ClipboardHistory) {
        file.parentFile?.mkdirs()
        val records = JSONArray()
        history.entries.forEach { entry -> records.put(JSONObject().put("id", entry.id).put("text", entry.text)
            .put("copiedAt", entry.copiedAt).put("pinned", entry.pinned)) }
        val bytes = JSONObject().put("version", 1).put("enabled", history.enabled).put("entries", records)
            .put("lastTimestamp", history.lastTimestamp).put("lastDigest", history.lastDigest ?: "")
            .toString().toByteArray(Charsets.UTF_8)
        val output = atomic.startWrite()
        try { output.write(bytes); atomic.finishWrite(output) }
        catch (failure: Exception) { atomic.failWrite(output); throw failure }
    }

    companion object { private const val MAX_FILE_BYTES = 2 * 1024 * 1024 }
}
