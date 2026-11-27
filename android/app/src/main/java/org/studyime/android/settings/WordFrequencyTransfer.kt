// SPDX-License-Identifier: GPL-3.0-or-later
package org.studyime.android.settings

import android.content.Context
import android.net.Uri
import android.provider.DocumentsContract
import android.widget.Toast
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import java.io.File
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.studyime.android.engine.EngineHost

internal class WordFrequencyTransfer : ViewModel() {
    enum class Operation(val label: String, val failure: String) {
        EXPORT("导出", "无法导出词频记忆，请重试。"),
        IMPORT("导入", "无法导入词频记忆，请检查 TSV 文件后重试。"),
    }

    var operation by mutableStateOf<Operation?>(null)
        private set

    fun save(context: Context, destination: Uri) = transfer(context, Operation.EXPORT) { app ->
        val resolver = app.contentResolver
        try {
            withSnapshot(app) { snapshot ->
                val entries = EngineHost.exportWordFrequency(app, snapshot.path)
                checkNotNull(resolver.openOutputStream(destination, "wt")).use { output ->
                    snapshot.inputStream().use { it.copyTo(output) }
                }
                entries
            }
        } catch (error: Exception) {
            runCatching { DocumentsContract.deleteDocument(resolver, destination) }
            throw error
        }
    }

    fun load(context: Context, source: Uri) = transfer(context, Operation.IMPORT) { app ->
        withSnapshot(app) { snapshot ->
            checkNotNull(app.contentResolver.openInputStream(source)).use { input ->
                snapshot.outputStream().use { output ->
                    val buffer = ByteArray(DEFAULT_BUFFER_SIZE)
                    var remaining = 32 * 1024 * 1024
                    while (true) {
                        val count = input.read(buffer)
                        if (count < 0) break
                        remaining -= count
                        require(remaining >= 0)
                        output.write(buffer, 0, count)
                    }
                }
            }
            EngineHost.importWordFrequency(app, snapshot.path)
        }
    }

    private suspend fun withSnapshot(app: Context, use: suspend (File) -> Int): Int {
        val snapshot = File.createTempFile("word-frequency-", ".tsv", app.cacheDir)
        try { return use(snapshot) }
        finally { snapshot.delete() }
    }

    private fun transfer(context: Context, current: Operation, work: suspend (Context) -> Int) {
        if (operation != null) return
        val app = context.applicationContext
        operation = current
        viewModelScope.launch {
            try {
                val count = withContext(Dispatchers.IO) { work(app) }
                Toast.makeText(app, "已${current.label}词频记忆（${count} 条）", Toast.LENGTH_SHORT).show()
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (_: Exception) {
                Toast.makeText(app, current.failure, Toast.LENGTH_LONG).show()
            } finally {
                operation = null
            }
        }
    }
}
