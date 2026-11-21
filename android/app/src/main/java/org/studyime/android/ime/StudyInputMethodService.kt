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
import java.io.FileDescriptor
import java.io.PrintWriter
import androidx.compose.runtime.getValue
import androidx.compose.runtime.collectAsState
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
import org.studyime.android.clipboard.ClipboardHistoryRepository
import org.studyime.android.clipboard.ClipboardMonitor
import org.studyime.android.diagnostics.StartupTimings
import org.studyime.android.diagnostics.StartupTimings.Phase
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
    private lateinit var clipboard: ClipboardHistoryRepository
    private lateinit var clipboardMonitor: ClipboardMonitor
    private var state by mutableStateOf(EngineSnapshot())
    private var prefs by mutableStateOf(KeyboardPreferences())
    private var editor by mutableStateOf(EditorSpec())
    private var viewOwner: ImeViewOwner? = null
    private var keyboardView: ComposeView? = null
    private var boundConnection: InputConnection? = null
    private data class EditorIdentity(val app: String?, val field: Int, val inputType: Int, val options: Int)
    private var editorIdentity: EditorIdentity? = null
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
        val started = StartupTimings.start()
        super.onCreate()
        preferences = Preferences.get(this)
        prefs = preferences.state.value
        clipboard = ClipboardHistoryRepository.get(this)
        clipboardMonitor = ClipboardMonitor(this, clipboard)
        engine = EngineHost(this)
        engine.onSnapshot = { snapshot, timing, type ->
            if (delivery.accept(snapshot.generation, snapshot.revision)) {
                if (deliver(snapshot)) {
                    ascii = snapshot.asciiMode
                    state = snapshot.copy(commands = emptyList())
                    // Aggregate durations only. No text, package or candidate is retained.
                    if (type == "key") InputMetrics.result(snapshot.generation, snapshot.revision, timing)
                    if (type == "start" || type == "restart") StartupTimings.record(Phase.FIRST_DELIVERY, timing.main)
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
        StartupTimings.record(Phase.SERVICE_CREATE, started)
    }

    override fun onEvaluateFullscreenMode() = false

    override fun onCreateInputView(): View {
        val started = SystemClock.elapsedRealtimeNanos()
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
                val clipboardState by clipboard.state.collectAsState()
                StudyTheme(prefs.theme, prefs.skin) {
                    StudyKeyboard(state, prefs, editor, preferences::update, ::send,
                        onSettings = {
                            startActivity(Intent(this@StudyInputMethodService, MainActivity::class.java)
                                .putExtra("screen", "settings")
                                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                        },
                        onSwitchIme = { (getSystemService(INPUT_METHOD_SERVICE) as InputMethodManager).showInputMethodPicker() },
                        onRetry = { restartEditor() },
                        onPickEmoji = ::pickEmoji,
                        clipboard = clipboardState, onClipboardEnabled = clipboard::setEnabled,
                        onPasteClipboard = ::pasteClipboard, onPinClipboard = clipboard::togglePin,
                        onDeleteClipboard = clipboard::remove, onClearClipboard = clipboard::clear,
                    )
                }
            }
            keyboardView = this
            owner.resume()
        }.also { StartupTimings.record(Phase.INPUT_VIEW_CREATE, started) }
    }

    override fun onStartInput(attribute: EditorInfo, restarting: Boolean) {
        StartupTimings.mark(Phase.START_INPUT)
        super.onStartInput(attribute, restarting)
        val identity = EditorIdentity(attribute.packageName, attribute.fieldId, attribute.inputType, attribute.imeOptions)
        val oldConnection = boundConnection
        val previous = state.takeIf { restarting && identity == editorIdentity && oldConnection != null && it.ready && !it.error }
        delivery.invalidate()
        engine.invalidate()
        boundConnection = currentInputConnection
        editorIdentity = identity
        editor = EditorSpec.from(attribute)
        clipboardMonitor.setProtectedEditor(editor.sensitive || editor.noPersonalization)
        // restartInput can deliver EditorInfo with the selection from before
        // an application's setText. Ask the new connection for current offsets
        // once; never retain the extracted text or query it on the key path.
        val extracted = runCatching { boundConnection?.getExtractedText(ExtractedTextRequest().apply {
            hintMaxChars = 1
            hintMaxLines = 1
        }, 0) }.getOrNull()
        val currentStart = (extracted?.let { it.startOffset + it.selectionStart } ?: attribute.initialSelStart).coerceAtLeast(0)
        val currentEnd = (extracted?.let { it.startOffset + it.selectionEnd } ?: attribute.initialSelEnd).coerceAtLeast(0)
        val restore = previous?.takeIf {
            if (currentStart != selectionStart || currentEnd != selectionEnd) false
            else if (it.input.isEmpty()) true
            else extracted?.text?.let { text ->
                val begin = composingStart - extracted.startOffset
                begin >= 0 && begin + composingLength <= text.length &&
                    text.subSequence(begin, begin + composingLength).toString() == it.preedit.ifEmpty { it.input }
            } == true
        }
        if (restore == null) {
            composingStart = -1
            composingLength = 0
            runCatching { oldConnection?.finishComposingText() }
        } else if (composingStart >= 0 && composingLength > 0) {
            // restartInput removes the old composing span even though the
            // verified text remains. Reattach it before replacing preedit.
            boundConnection?.setComposingRegion(composingStart, composingStart + composingLength)
        }
        ascii = restore?.asciiMode ?: editor.asciiPreferred
        selectionStart = currentStart
        selectionEnd = currentEnd
        expectedSelections.clear()
        expected(selectionStart, selectionEnd)
        beginEditor(restore)
    }

    private fun beginEditor(previous: EngineSnapshot? = null) {
        generation = engine.begin(config(), previous)
        delivery.bind(generation)
        state = previous?.copy(generation = generation, target = null, commands = emptyList()) ?: EngineSnapshot(generation = generation, schema = prefs.schema, asciiMode = ascii,
            showEnglish = prefs.showEnglish && !editor.sensitive, userLearning = prefs.userLearning && !editor.sensitive && !editor.noPersonalization)
    }

    private fun restartEditor() {
        boundConnection = currentInputConnection
        beginEditor()
    }

    private fun config() = prefs.engineConfig(ascii, editor.sensitive, editor.noPersonalization)

    override fun onStartInputView(info: EditorInfo, restarting: Boolean) {
        StartupTimings.mark(Phase.START_INPUT_VIEW)
        InputMetrics.showRequested()
        super.onStartInputView(info, restarting)
        viewOwner?.resume()
        clipboardMonitor.refresh()
        keyboardView?.invalidate()
    }

    override fun onFinishInputView(finishingInput: Boolean) {
        viewOwner?.stop()
        // The platform default finishes composing text on a hide even when
        // this editor remains active. Keep its span until onFinishInput (or an
        // actual external cursor edit) so reopening can continue the word.
        if (finishingInput) super.onFinishInputView(true)
    }

    override fun onFinishInput() {
        delivery.invalidate()
        engine.invalidate()
        // Finish only the captured old connection, never whichever editor may
        // become current by the time an asynchronous result is delivered.
        val previousConnection = boundConnection
        boundConnection = null
        editorIdentity = null
        clipboardMonitor.finishEditor()
        generation = 0
        composingStart = -1
        composingLength = 0
        runCatching { previousConnection?.finishComposingText() }
        state = EngineSnapshot()
        super.onFinishInput()
    }

    override fun onDestroy() {
        delivery.invalidate()
        clipboardMonitor.close()
        scope.cancel()
        keyboardView?.disposeComposition()
        viewOwner?.destroy()
        engine.close()
        super.onDestroy()
    }

    override fun dump(fd: FileDescriptor, writer: PrintWriter, args: Array<out String>?) {
        if (args?.contains("study-metrics-reset") == true) InputMetrics.reset()
        if (args?.any { it.startsWith("study-metrics") } == true) writer.println(InputMetrics.report())
        else super.dump(fd, writer, args)
    }

    private fun send(command: JSONObject) {
        if (generation != 0L) engine.submit(generation, command)
    }

    private fun canInsertLiteral(requestedGeneration: Long) =
        requestedGeneration == generation && generation != 0L && boundConnection != null &&
            isInputViewShown && state.ready && !state.error

    private fun pickEmoji(text: String, requestedGeneration: Long) {
        if (!canInsertLiteral(requestedGeneration) || !editor.allowsEmoji) return
        // Submit the entire Unicode sequence as one literal, just like punctuation.
        send(event("literal", "text" to text))
    }

    private fun pasteClipboard(id: String, requestedGeneration: Long) {
        if (!canInsertLiteral(requestedGeneration) || editor.sensitive || editor.noPersonalization) return
        val history = clipboard.state.value.history
        if (!history.enabled) return
        val entry = history.entries.firstOrNull { it.id == id } ?: return
        // The same generation/commit-id gates as keys protect asynchronous paste delivery.
        send(event("literal", "text" to entry.text))
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
            if (snapshot.notice == "restart-discarded") {
                connection.finishComposingText()
                composingStart = -1
                composingLength = 0
            }
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
        if (selection == (selectionStart to selectionEnd)) {
            if (composingStart < 0 || (candidatesStart == composingStart && candidatesEnd == composingStart + composingLength)) return
            // Closing the old InputConnection removes its composing span just
            // before onStartInput(restarting=true). Quiesce delivery immediately,
            // but allow that verified restart to reclaim the visible word.
            val closingGeneration = generation
            delivery.invalidate()
            engine.invalidate()
            keyboardView?.postDelayed({
                if (generation == closingGeneration && generation != 0L) {
                    composingStart = -1
                    composingLength = 0
                    expectedSelections.clear()
                    beginEditor()
                }
            }, 50)
            return
        }
        selectionStart = newSelStart.coerceAtLeast(0)
        selectionEnd = newSelEnd.coerceAtLeast(0)
        expectedSelections.clear()
        if (generation != 0L && boundConnection != null) {
            // External cursor/selection movement ends the old composing region.
            // Raise the generation immediately so queued keystrokes cannot apply
            // at the new caret. Already visible text remains in the editor.
            composingStart = -1
            composingLength = 0
            boundConnection?.finishComposingText()
            beginEditor()
        }
    }
}
