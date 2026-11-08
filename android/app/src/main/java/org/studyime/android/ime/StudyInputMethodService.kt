// SPDX-License-Identifier: GPL-3.0-or-later
package org.studyime.android.ime

import android.content.Intent
import android.inputmethodservice.InputMethodService
import android.os.SystemClock
import android.view.View
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.ExtractedTextRequest
import android.view.inputmethod.InputConnection
import android.view.inputmethod.InputMethodManager
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.ComposeView
import androidx.compose.ui.platform.ViewCompositionStrategy
import androidx.core.view.WindowCompat
import androidx.lifecycle.setViewTreeLifecycleOwner
import androidx.lifecycle.setViewTreeViewModelStoreOwner
import androidx.savedstate.setViewTreeSavedStateRegistryOwner
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import org.json.JSONObject
import org.studyime.android.MainActivity
import org.studyime.android.engine.EngineHost
import org.studyime.android.engine.EngineSnapshot
import org.studyime.android.engine.event
import org.studyime.android.settings.KeyboardPreferences
import org.studyime.android.settings.Preferences
import org.studyime.android.ui.StudyKeyboard
import org.studyime.android.ui.StudyTheme

class StudyInputMethodService : InputMethodService() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private lateinit var engine: EngineHost
    private lateinit var preferences: Preferences
    private var state by mutableStateOf(EngineSnapshot())
    private var prefs by mutableStateOf(KeyboardPreferences())
    private var editor by mutableStateOf(EditorSpec())
    private var viewOwner: ImeViewOwner? = null
    private var keyboardView: ComposeView? = null
    private var boundConnection: InputConnection? = null
    private var generation = 0L
    private var ascii = false
    private val delivery = DeliveryGate()
    private var selectionStart = 0
    private var selectionEnd = 0
    private var composingStart = -1
    private var composingLength = 0
    private data class ExpectedSelection(val start: Int, val end: Int, val composingStart: Int, val composingEnd: Int)
    private val expectedSelections = ArrayDeque<ExpectedSelection>()

    override fun onCreate() {
        super.onCreate()
        preferences = Preferences.get(this)
        prefs = preferences.state.value
        engine = EngineHost(this)
        engine.onSnapshot = { snapshot, started ->
            if (delivery.accept(snapshot.generation, snapshot.revision)) {
                if (deliver(snapshot)) {
                    ascii = snapshot.asciiMode
                    state = snapshot.copy(commands = emptyList())
                    // Aggregate durations only. No text, package or candidate is retained.
                    InputMetrics.engineResult(SystemClock.elapsedRealtimeNanos() - started)
                } else connectionFailed()
            }
        }
        engine.onFailure = {
            delivery.invalidate()
            state = EngineSnapshot(generation = generation, error = true, showEnglish = !editor.sensitive && prefs.showEnglish)
        }
        scope.launch {
            preferences.state.collect { next ->
                val engineChanged = next.schema != prefs.schema || next.showEnglish != prefs.showEnglish || next.userLearning != prefs.userLearning
                prefs = next
                if (generation != 0L && engineChanged) send(event("configure", "config" to config()))
            }
        }
    }

    override fun onEvaluateFullscreenMode() = false

    override fun onCreateInputView(): View {
        keyboardView?.disposeComposition()
        viewOwner?.destroy()
        val owner = ImeViewOwner().also { viewOwner = it }
        window?.window?.let {
            WindowCompat.setDecorFitsSystemWindows(it, false)
            // Compose's window recomposer starts at the content root, above
            // ComposeView. The IME window has no Activity to install owners.
            it.decorView.setViewTreeLifecycleOwner(owner)
            it.decorView.setViewTreeViewModelStoreOwner(owner)
            it.decorView.setViewTreeSavedStateRegistryOwner(owner)
        }
        return ComposeView(this).apply {
            setViewTreeLifecycleOwner(owner)
            setViewTreeViewModelStoreOwner(owner)
            setViewTreeSavedStateRegistryOwner(owner)
            setViewCompositionStrategy(ViewCompositionStrategy.DisposeOnViewTreeLifecycleDestroyed)
            setContent {
                StudyTheme(prefs.theme) {
                    StudyKeyboard(state, prefs, editor, preferences::update, ::send,
                        onSettings = {
                            startActivity(Intent(this@StudyInputMethodService, MainActivity::class.java)
                                .putExtra("screen", "settings")
                                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                        },
                        onSwitchIme = { (getSystemService(INPUT_METHOD_SERVICE) as InputMethodManager).showInputMethodPicker() },
                        onRetry = { restartEditor() },
                    )
                }
            }
            keyboardView = this
            owner.resume()
        }
    }

    override fun onStartInput(attribute: EditorInfo, restarting: Boolean) {
        super.onStartInput(attribute, restarting)
        delivery.invalidate()
        engine.invalidate()
        boundConnection = currentInputConnection
        editor = EditorSpec.from(attribute)
        ascii = editor.asciiPreferred
        // restartInput can deliver EditorInfo with the selection from before
        // an application's setText. Ask the new connection for current offsets
        // once; never retain the extracted text or query it on the key path.
        val extracted = runCatching { boundConnection?.getExtractedText(ExtractedTextRequest().apply {
            hintMaxChars = 1
            hintMaxLines = 1
        }, 0) }.getOrNull()
        selectionStart = (extracted?.let { it.startOffset + it.selectionStart } ?: attribute.initialSelStart).coerceAtLeast(0)
        selectionEnd = (extracted?.let { it.startOffset + it.selectionEnd } ?: attribute.initialSelEnd).coerceAtLeast(0)
        composingStart = -1
        composingLength = 0
        expectedSelections.clear()
        expected(selectionStart, selectionEnd)
        beginEditor()
    }

    private fun beginEditor() {
        generation = engine.begin(config())
        delivery.bind(generation)
        state = EngineSnapshot(generation = generation, schema = prefs.schema, asciiMode = ascii,
            showEnglish = prefs.showEnglish && !editor.sensitive, userLearning = prefs.userLearning && !editor.sensitive && !editor.noPersonalization)
    }

    private fun restartEditor() {
        boundConnection = currentInputConnection
        beginEditor()
    }

    private fun config() = prefs.engineConfig(ascii, editor.sensitive, editor.noPersonalization)

    override fun onStartInputView(info: EditorInfo, restarting: Boolean) {
        super.onStartInputView(info, restarting)
        viewOwner?.resume()
    }

    override fun onFinishInputView(finishingInput: Boolean) {
        viewOwner?.stop()
        super.onFinishInputView(finishingInput)
    }

    override fun onFinishInput() {
        delivery.invalidate()
        engine.invalidate()
        // Finish only the captured old connection, never whichever editor may
        // become current by the time an asynchronous result is delivered.
        runCatching { boundConnection?.finishComposingText() }
        boundConnection = null
        generation = 0
        composingStart = -1
        composingLength = 0
        state = EngineSnapshot()
        super.onFinishInput()
    }

    override fun onDestroy() {
        delivery.invalidate()
        scope.cancel()
        keyboardView?.disposeComposition()
        viewOwner?.destroy()
        engine.close()
        super.onDestroy()
    }

    private fun send(command: JSONObject) {
        if (generation != 0L) engine.submit(generation, command)
    }

    private fun expected(start: Int, end: Int = start) {
        selectionStart = start
        selectionEnd = end
        expectedSelections.addLast(ExpectedSelection(start, end, composingStart,
            if (composingStart >= 0) composingStart + composingLength else -1))
        while (expectedSelections.size > 64) expectedSelections.removeFirst()
    }

    private fun deliver(snapshot: EngineSnapshot): Boolean {
        val connection = boundConnection ?: return false
        connection.beginBatchEdit()
        try {
            for (command in snapshot.commands) {
                if (!delivery.consume(command.id) {
                    when (command.kind) {
                        "commit" -> {
                            val start = if (composingStart >= 0) composingStart else minOf(selectionStart, selectionEnd)
                            val success = connection.commitText(command.text, 1)
                            composingStart = -1
                            composingLength = 0
                            expected(start + command.text.length)
                            success
                        }
                        "delete" -> {
                            val selected = selectionStart != selectionEnd
                            var removedWidth = 1
                            val success = if (selected) connection.commitText("", 1) else {
                                // Code-point deletion preserves surrogate pairs (e.g. emoji).
                                val before = connection.getTextBeforeCursor(2, 0)?.toString().orEmpty()
                                val width = if (before.length >= 2 && Character.isSurrogatePair(before[before.lastIndex - 1], before.last())) 2 else 1
                                removedWidth = width
                                val deleted = connection.deleteSurroundingTextInCodePoints(1, 0)
                                if (!deleted) connection.deleteSurroundingText(width, 0) else true
                            }
                            val target = if (selected) minOf(selectionStart, selectionEnd) else (selectionStart - removedWidth).coerceAtLeast(0)
                            expected(target)
                            success
                        }
                        "action" -> if (editor.action in listOf(EditorInfo.IME_ACTION_UNSPECIFIED, EditorInfo.IME_ACTION_NONE)) {
                            val success = connection.commitText("\n", 1)
                            expected(minOf(selectionStart, selectionEnd) + 1)
                            success
                        } else connection.performEditorAction(editor.action)
                        else -> false
                    }
                }) return false
            }
            if (snapshot.input.isNotEmpty()) {
                val text = snapshot.preedit.ifEmpty { snapshot.input }
                if (composingStart < 0) composingStart = minOf(selectionStart, selectionEnd)
                if (!connection.setComposingText(text, 1)) return false
                composingLength = text.length
                expected(composingStart + text.length)
                if (snapshot.caret < snapshot.input.length) {
                    val bytes = text.toByteArray(Charsets.UTF_8)
                    val offset = String(bytes, 0, snapshot.preeditCursor.coerceIn(0, bytes.size), Charsets.UTF_8).length
                    if (!connection.setSelection(composingStart + offset, composingStart + offset)) return false
                    expected(composingStart + offset)
                }
            } else if (composingStart >= 0) {
                if (!connection.setComposingText("", 1)) return false
                connection.finishComposingText()
                val start = composingStart
                composingStart = -1
                composingLength = 0
                expected(start)
            }
            return true
        } catch (_: RuntimeException) {
            return false
        } finally {
            runCatching { connection.endBatchEdit() }
        }
    }

    private fun connectionFailed() {
        delivery.invalidate()
        engine.invalidate()
        // Do not resend commits after an uncertain editor result.
        state = EngineSnapshot(generation = generation, error = true)
    }

    override fun onUpdateSelection(oldSelStart: Int, oldSelEnd: Int, newSelStart: Int, newSelEnd: Int, candidatesStart: Int, candidatesEnd: Int) {
        super.onUpdateSelection(oldSelStart, oldSelEnd, newSelStart, newSelEnd, candidatesStart, candidatesEnd)
        val selection = newSelStart to newSelEnd
        val expectedIndex = expectedSelections.indexOfFirst { it.start == newSelStart && it.end == newSelEnd &&
            it.composingStart == candidatesStart && it.composingEnd == candidatesEnd }
        if (expectedIndex >= 0) {
            repeat(expectedIndex + 1) { expectedSelections.removeFirst() }
            return
        }
        if (selection == (selectionStart to selectionEnd)) return
        selectionStart = newSelStart.coerceAtLeast(0)
        selectionEnd = newSelEnd.coerceAtLeast(0)
        expectedSelections.clear()
        if (generation != 0L && boundConnection != null) {
            // External cursor/selection movement ends the old composing region.
            // Raise the generation immediately so queued keystrokes cannot apply
            // at the new caret. Already visible text remains in the editor.
            boundConnection?.finishComposingText()
            composingStart = -1
            composingLength = 0
            beginEditor()
        }
    }
}

object InputMetrics {
    private val samples = ArrayDeque<Long>()
    @Synchronized fun engineResult(nanos: Long) {
        samples.addLast(nanos)
        if (samples.size > 1024) samples.removeFirst()
    }
    @Synchronized fun samplesMs(): List<Double> = samples.map { it / 1_000_000.0 }
}
