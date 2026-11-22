// SPDX-License-Identifier: GPL-3.0-or-later
package org.studyime.android.ui

import android.provider.Settings
import android.os.SystemClock
import android.view.HapticFeedbackConstants
import android.view.View
import android.view.ViewConfiguration
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityManager
import android.view.inputmethod.EditorInfo
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.gestures.waitForUpOrCancellation
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.Backspace
import androidx.compose.material.icons.automirrored.outlined.KeyboardReturn
import androidx.compose.material.icons.automirrored.outlined.ArrowForward
import androidx.compose.material.icons.automirrored.outlined.Send
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.ExperimentalComposeUiApi
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawWithCache
import androidx.compose.ui.draw.drawWithContent
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.input.pointer.AwaitPointerEventScope
import androidx.compose.ui.input.pointer.PointerId
import androidx.compose.ui.input.pointer.changedToUpIgnoreConsumed
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.*
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LifecycleEventEffect
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.flow.drop
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import org.json.JSONObject
import org.studyime.android.clipboard.ClipboardHistoryState
import org.studyime.android.engine.*
import org.studyime.android.diagnostics.StartupTimings
import org.studyime.android.diagnostics.StartupTimings.Phase
import org.studyime.android.ime.EditorSpec
import org.studyime.android.ime.InputMetrics
import org.studyime.android.settings.KeyboardPreferences
import org.studyime.android.settings.KeyboardSkin

private const val EMOJI_LABEL = "表情符号"

private val LocalGestureGeneration = staticCompositionLocalOf { 0L }

@OptIn(ExperimentalComposeUiApi::class, ExperimentalFoundationApi::class)
@Composable
fun StudyKeyboard(
    state: EngineSnapshot, prefs: KeyboardPreferences, editor: EditorSpec,
    update: ((KeyboardPreferences) -> KeyboardPreferences) -> Unit,
    send: (JSONObject) -> Unit, onSettings: () -> Unit,
    onSwitchIme: () -> Unit, onRetry: () -> Unit, onPickEmoji: (String, Long) -> Unit,
    clipboard: ClipboardHistoryState, onClipboardEnabled: (Boolean) -> Unit,
    onPasteClipboard: (String, Long) -> Unit, onPinClipboard: (String) -> Unit,
    onDeleteClipboard: (String) -> Unit, onClearClipboard: () -> Unit,
) {
    val compositionStarted = SystemClock.elapsedRealtimeNanos()
    val colors = LocalStudyColors.current
    val configuration = LocalConfiguration.current
    val density = LocalDensity.current
    val landscape = configuration.screenWidthDp > configuration.screenHeightDp
    val context = LocalContext.current
    val view = LocalView.current
    val accessibility = remember(context) { context.getSystemService(AccessibilityManager::class.java) }
    val systemReduced = remember { Settings.Global.getFloat(context.contentResolver, Settings.Global.ANIMATOR_DURATION_SCALE, 1f) == 0f }
    val reduced = prefs.reduceMotion || systemReduced
    val effectivePrefs = prefs.copy(reduceMotion = reduced)
    var page by remember(state.generation) { mutableStateOf(if (editor.numeric) "numbers" else "letters") }
    var shift by remember(state.generation) { mutableStateOf(ShiftMode.LOWER) }
    var firstShiftTapAt by remember(state.generation) { mutableStateOf<Long?>(null) }
    var expanded by remember(state.generation) { mutableStateOf(false) }
    var quickSettings by remember(state.generation) { mutableStateOf(false) }
    var clipboardOpen by remember(state.generation) { mutableStateOf(false) }
    var emojiOpen by remember(state.generation) { mutableStateOf(false) }
    if (emojiOpen) LifecycleEventEffect(Lifecycle.Event.ON_STOP) { emojiOpen = false }
    val active = state.ready && !state.error
    val emojiShowing = emojiOpen && editor.allowsEmoji && active
    val clipboardAllowed = !editor.sensitive && !editor.noPersonalization
    val clipboardShowing = clipboardOpen && clipboardAllowed
    val currentState by rememberUpdatedState(state)
    // Keep letter keys independent of candidate revisions. The callback reads
    // the current snapshot at activation; a new editor still cancels gestures.
    val onKey = remember(state.generation, send) {
        { id: String, text: String ->
            val latest = currentState
            if (id != "shift") firstShiftTapAt = null
            when (id) {
                "shift" -> {
                    val now = SystemClock.uptimeMillis()
                    val rapidSecondTap = firstShiftTapAt?.let { now - it <= ViewConfiguration.getDoubleTapTimeout() } == true
                    shift = when (shift) {
                        ShiftMode.LOWER -> ShiftMode.ONCE
                        ShiftMode.ONCE -> if (rapidSecondTap) ShiftMode.LOCKED else ShiftMode.LOWER
                        ShiftMode.LOCKED -> ShiftMode.LOWER
                    }
                    firstShiftTapAt = now.takeIf { shift == ShiftMode.ONCE }
                }
                "mode" -> {
                    if (shift == ShiftMode.ONCE) shift = ShiftMode.LOWER
                    send(event("mode", "ascii" to !latest.asciiMode))
                }
                "details" -> send(event("inspect", "index" to latest.highlighted, "revision" to latest.revision))
                "comma" -> send(event("literal", "text" to text))
                "page" -> { page = if (page == "letters") "numbers" else "letters" }
                "symbols" -> { page = when (page) { "numbers" -> "commonSymbols"; "letters" -> "symbols"; else -> "numbers" } }
                "symbolSet" -> { page = if (page == "commonSymbols") "symbols" else "commonSymbols" }
                "delete" -> send(event("key", "code" to 0xff08))
                "enter" -> send(event("key", "code" to 0xff0d))
                "space" -> send(event("key", "code" to 32))
                else -> {
                    if (page == "letters" && id.length == 1 && id[0] in 'a'..'z') {
                        // Read Shift at the tap, since the key face may not have redrawn yet.
                        val letter = id[0]
                        if (shift.upper) {
                            if (shift == ShiftMode.ONCE) shift = ShiftMode.LOWER
                            send(event("literal", "text" to letter.uppercase()))
                        } else send(event("key", "code" to letter.code))
                    } else if ((text.length == 1 && (page == "letters" || text[0].isAsciiLetter())) ||
                        (text == "'" && latest.input.isNotEmpty() && !latest.asciiMode)) {
                        send(event("key", "code" to text[0].code))
                    } else send(event("literal", "text" to text))
                }
            }
        }
    }
    val onLongKey = remember(state.generation, send) { { text: String ->
        firstShiftTapAt = null
        val latest = currentState
        if (text.length == 1 && (text[0].isAsciiLetter() || (text == "'" && latest.input.isNotEmpty() && !latest.asciiMode))) {
            send(event("key", "code" to text[0].code))
        } else send(event("literal", "text" to text))
    } }
    LaunchedEffect(state.generation, state.revision, state.ready, page, expanded, quickSettings, clipboardShowing, emojiShowing,
        shift, prefs.theme, prefs.skin, prefs.showEnglish) {
        announceImeSubtree(view, accessibility)
    }
    val keyHeight = maxOf(if (landscape) 40f else 48f, (if (landscape) 42f else 52f) * prefs.keyHeight,
        24f * density.fontScale * prefs.textScale + 10f).dp
    val keyRowsHeight = keyHeight * 4
    // Keep the same height while idle, composing, switching skins or hiding
    // English. First-candidate delivery must never move a finger's target.
    val statusHeight = maxOf(60f, 39f * density.fontScale * prefs.textScale + 12f).dp
    val openSettings = { quickSettings = true; expanded = false; clipboardOpen = false }
    val openClipboard = { clipboardOpen = !clipboardOpen; quickSettings = false; expanded = false }
    val openEmoji = {
        emojiOpen = true
        clipboardOpen = false
        quickSettings = false
        expanded = false
        if (state.target != null) send(event("dismiss"))
    }

    Column(Modifier.fillMaxWidth().background(colors.board).navigationBarsPadding().drawWithContent {
        drawContent()
        InputMetrics.frame(state.generation, state.revision, state.ready && !state.error)
    }
        .semantics { testTagsAsResourceId = true }.testTag("study_keyboard")) {
        val keys: @Composable (Modifier) -> Unit = { modifier ->
            when {
                clipboardShowing -> ClipboardPanel(clipboard, modifier.height(keyRowsHeight), active, onClipboardEnabled,
                    onPaste = { id -> onPasteClipboard(id, state.generation); clipboardOpen = false },
                    onPinClipboard, onDeleteClipboard, onClearClipboard, close = { clipboardOpen = false })
                quickSettings -> QuickSettings(prefs, update, state.input.isNotEmpty(), editor.sensitive,
                    modifier.height(keyRowsHeight), close = { quickSettings = false }, allSettings = {
                        quickSettings = false
                        onSettings()
                    })
                expanded && state.candidates.isNotEmpty() -> ExpandedCandidates(state, prefs, send,
                    modifier.height(keyRowsHeight), openSettings) { expanded = false }
                // Never reuse the preceding editor's key faces or pressed state
                // when the IME window survives an input connection change.
                else -> key(state.generation) {
                    KeyboardRows(page, shift, state.generation, active, state.asciiMode, state.input.isNotEmpty(),
                        canInspect = !editor.sensitive && state.highlighted in state.candidates.indices,
                        effectivePrefs, editor, keyHeight, modifier, onKey, onLongKey, onSwitchIme)
                }
            }
        }

        if (emojiShowing) {
            EmojiPanel(if (landscape) 60.dp else statusHeight, keyRowsHeight, landscape,
                onClose = { emojiOpen = false }, onPick = { onPickEmoji(it, state.generation) })
        } else if (landscape) {
            IdleToolbar(state, prefs, editor, update, openSettings, openClipboard, openEmoji, onRetry,
                Modifier.fillMaxWidth().height(60.dp))
            val row = Modifier.fillMaxWidth().padding(horizontal = 5.dp, vertical = 3.dp)
            if (clipboardShowing) keys(row)
            else Row(row, verticalAlignment = Alignment.Bottom) {
                Column(Modifier.widthIn(max = 270.dp).weight(.34f).height(keyRowsHeight).padding(end = 7.dp)) {
                    if (active && state.candidates.isNotEmpty()) {
                        LazyColumn(Modifier.weight(1f)) {
                            itemsIndexed(state.candidates) { index, candidate ->
                                CandidateCard(candidate, index, state, prefs, send, Modifier.fillMaxWidth())
                            }
                        }
                        Paging(state, send, Modifier.fillMaxWidth())
                    } else ReadyHint(state, editor, onRetry, Modifier.weight(1f))
                }
                keys(Modifier.weight(.66f))
            }
        } else {
            Box(Modifier.fillMaxWidth().height(statusHeight).testTag("keyboard_status")) {
                if (state.candidates.isNotEmpty() && !quickSettings && !clipboardShowing) {
                    CandidateStrip(state, effectivePrefs, send, expanded, openSettings,
                        openEmoji.takeIf { expanded && active && editor.allowsEmoji }) { expanded = !expanded }
                } else IdleToolbar(state, prefs, editor, update, openSettings, openClipboard, openEmoji, onRetry, Modifier.fillMaxSize())
            }
            keys(Modifier.fillMaxWidth().padding(horizontal = 4.dp))
        }
        Spacer(Modifier.height(if (landscape) 3.dp else 7.dp))
        state.target?.takeUnless { emojiShowing }?.let { target ->
            val screen = configuration.screenHeightDp.dp
            val boardHeight = keyRowsHeight + if (landscape) 66.dp else statusHeight + 7.dp
            val nav = WindowInsets.navigationBars.asPaddingValues().calculateBottomPadding()
            val room = screen - boardHeight - nav - 18.dp
            // Above the candidate strip in portrait; on short windows allow
            // overlap rather than losing the actions or resizing any keys.
            val height = minOf(430.dp, maxOf(1.dp, screen - 24.dp), maxOf(230.dp, room))
            WordDetailPopup(target, state.showEnglish, prefs.textScale, height, send)
        }
    }
    val compositionFinished = SystemClock.elapsedRealtimeNanos()
    SideEffect {
        InputMetrics.composed(state.generation, state.revision, compositionStarted, compositionFinished)
        StartupTimings.record(Phase.COMPOSITION, compositionStarted, compositionFinished)
    }
}

internal suspend fun announceImeSubtree(view: View, accessibility: AccessibilityManager) {
    // The non-focused IME window needs a subtree invalidation after layout,
    // including scroll-only movement, to expose current virtual-node bounds.
    withFrameNanos { }
    view.post {
        // An accessibility client can disconnect before this callback runs.
        if (view.isAttachedToWindow && accessibility.isEnabled) {
            view.sendAccessibilityEventUnchecked(AccessibilityEvent.obtain(AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED).apply {
                contentChangeTypes = AccessibilityEvent.CONTENT_CHANGE_TYPE_SUBTREE
            })
        }
    }
}

@Composable
internal fun ToolButton(icon: ImageVector, description: String, enabled: Boolean = true, onClick: () -> Unit) {
    val colors = LocalStudyColors.current
    IconButton(onClick = onClick, enabled = enabled, modifier = Modifier.size(48.dp)) {
        val ink = if (enabled) colors.subtle else colors.subtle.copy(alpha = .5f)
        Icon(icon, description, Modifier.size(20.dp), tint = ink)
    }
}

@Composable
private fun IdleToolbar(state: EngineSnapshot, prefs: KeyboardPreferences, editor: EditorSpec,
                        update: ((KeyboardPreferences) -> KeyboardPreferences) -> Unit,
                        settings: () -> Unit, clipboard: () -> Unit, emoji: () -> Unit,
                        retry: () -> Unit, modifier: Modifier) {
    val colors = LocalStudyColors.current
    val toolbar = modifier.testTag("idle_toolbar")
    if (!state.ready || state.error || editor.sensitive) {
        Row(toolbar.padding(horizontal = 7.dp), verticalAlignment = Alignment.CenterVertically) {
            ToolbarButton(ToolbarGlyph.Menu, "键盘设置", onClick = settings)
            ReadyHint(state, editor, retry, Modifier.weight(1f))
            ToolbarButton(ToolbarGlyph.Clipboard, "剪贴板历史", enabled = false, onClick = clipboard)
        }
    } else {
        Row(toolbar, horizontalArrangement = Arrangement.spacedBy(6.dp, Alignment.CenterHorizontally),
            verticalAlignment = Alignment.CenterVertically) {
            ToolbarButton(ToolbarGlyph.Menu, "键盘设置", onClick = settings)
            ToolbarButton(ToolbarGlyph.Emoji, EMOJI_LABEL, enabled = editor.allowsEmoji, onClick = emoji)
            ToolbarButton(ToolbarGlyph.Clipboard, "剪贴板历史", enabled = !editor.noPersonalization, onClick = clipboard)
            ToolbarButton(if (colors.dark) ToolbarGlyph.Sun else ToolbarGlyph.Moon, "切换浅深色") {
                update { it.copy(theme = if (colors.dark) "light" else "dark") }
            }
            GlossBubble(prefs.showEnglish) { checked -> update { it.copy(showEnglish = checked) } }
        }
    }
}

@Composable
private fun EnglishToggle(checked: Boolean, enabled: Boolean = true, onClick: () -> Unit) {
    val colors = LocalStudyColors.current
    Row(Modifier.heightIn(min = 48.dp).clip(RoundedCornerShape(22.dp))
        .toggleable(value = checked, enabled = enabled, role = Role.Switch) { onClick() }
        .padding(horizontal = 10.dp).semantics(mergeDescendants = true) {
            contentDescription = "显示英文释义"
            stateDescription = if (checked) "开启" else "关闭"
        }, verticalAlignment = Alignment.CenterVertically) {
        Text("英译", fontSize = 12.sp, color = colors.accent)
        Spacer(Modifier.width(7.dp))
        Box(Modifier.size(26.dp, 16.dp).background(if (checked) colors.accent else colors.line, RoundedCornerShape(10.dp))) {
            Box(Modifier.align(if (checked) Alignment.CenterEnd else Alignment.CenterStart).padding(3.dp)
                .size(10.dp).background(if (checked) colors.onAccent else colors.subtle, RoundedCornerShape(8.dp)))
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun QuickSettings(prefs: KeyboardPreferences, update: ((KeyboardPreferences) -> KeyboardPreferences) -> Unit,
                          composing: Boolean, sensitive: Boolean, modifier: Modifier, close: () -> Unit, allSettings: () -> Unit) {
    val colors = LocalStudyColors.current
    val scroll = rememberScrollState()
    val view = LocalView.current
    val accessibility = remember(view) { view.context.getSystemService(AccessibilityManager::class.java) }
    val large = LocalDensity.current.fontScale >= 1.5f
    LaunchedEffect(scroll) {
        snapshotFlow { scroll.value }.drop(1).collectLatest { announceImeSubtree(view, accessibility) }
    }
    Column(modifier.background(colors.board).padding(horizontal = 12.dp).testTag("quick_settings")) {
        Row(Modifier.fillMaxWidth().height(48.dp), verticalAlignment = Alignment.CenterVertically) {
            Text(if (large) "设置" else "键盘设置", Modifier.weight(1f), fontSize = 14.sp, fontWeight = FontWeight.Medium, color = colors.ink)
            TextButton(onClick = allSettings, modifier = Modifier.height(48.dp)) { Text(if (large) "全部" else "全部设置", fontSize = 12.sp) }
            ToolButton(Icons.Outlined.Close, "关闭快捷设置", onClick = close)
        }
        Column(Modifier.weight(1f).verticalScroll(scroll).testTag("quick_settings_scroll")) {
            Row(Modifier.fillMaxWidth().heightIn(min = 48.dp), verticalAlignment = Alignment.CenterVertically) {
                Text("皮肤", Modifier.weight(1f), fontSize = 13.sp, color = colors.ink)
                KeyboardSkin.entries.forEach { skin ->
                    SettingChoice(skin.title, prefs.skin == skin, "skin_${skin.id}") { update { it.copy(skin = skin) } }
                }
            }
            Row(Modifier.fillMaxWidth().heightIn(min = 48.dp), verticalAlignment = Alignment.CenterVertically) {
                Text("外观", Modifier.weight(1f), fontSize = 13.sp, color = colors.ink)
                listOf("system" to "自动", "light" to "浅色", "dark" to "深色").forEach { (mode, title) ->
                    SettingChoice(title, prefs.theme == mode, "theme_$mode") { update { it.copy(theme = mode) } }
                }
            }
            Row(Modifier.fillMaxWidth().heightIn(min = 48.dp), verticalAlignment = Alignment.CenterVertically) {
                Text("英文释义", Modifier.weight(1f), fontSize = 13.sp, color = colors.ink)
                EnglishToggle(prefs.showEnglish && !sensitive, !sensitive) { update { it.copy(showEnglish = !it.showEnglish) } }
            }
            Text("输入方式", Modifier.padding(top = 12.dp, bottom = 4.dp), fontSize = 13.sp, color = colors.subtle)
            FlowRow(horizontalArrangement = Arrangement.spacedBy(7.dp)) {
                listOf("study", "study_double_pinyin", "study_flypy").forEach { schema ->
                    FilterChip(selected = prefs.schema == schema, onClick = { update { it.copy(schema = schema) } },
                        label = { Text(schemaName(schema).removeSuffix("双拼"), fontSize = 13.sp) }, modifier = Modifier.heightIn(min = 48.dp))
                }
            }
            if (composing) Text("完成当前选词后切换方案", fontSize = 12.sp, color = colors.subtle)
            Row(Modifier.fillMaxWidth().heightIn(min = 64.dp), verticalAlignment = Alignment.CenterVertically) {
                Text("记住中文选词习惯", Modifier.weight(1f), fontSize = 14.sp, color = colors.ink)
                Switch(checked = prefs.userLearning, onCheckedChange = { checked -> update { it.copy(userLearning = checked) } })
            }
        }
    }
}

@Composable
private fun SettingChoice(title: String, selected: Boolean, tag: String, onClick: () -> Unit) {
    val colors = LocalStudyColors.current
    TextButton(onClick = onClick, shape = RoundedCornerShape(12.dp),
        colors = ButtonDefaults.textButtonColors(containerColor = if (selected) colors.tint else Color.Transparent,
            contentColor = if (selected) colors.accent else colors.subtle),
        contentPadding = PaddingValues(horizontal = 12.dp),
        modifier = Modifier.heightIn(min = 48.dp).testTag(tag).semantics { this.selected = selected }) {
        Text(title, fontSize = 12.sp, maxLines = 1)
    }
}

@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun CandidateStrip(state: EngineSnapshot, prefs: KeyboardPreferences, send: (JSONObject) -> Unit,
                           expanded: Boolean, settings: () -> Unit, openEmoji: (() -> Unit)?, onExpand: () -> Unit) {
    val scroll = key(state.generation, state.input, state.page) { rememberScrollState() }
    val view = LocalView.current
    val accessibility = remember(view) { view.context.getSystemService(AccessibilityManager::class.java) }
    LaunchedEffect(scroll) {
        snapshotFlow { scroll.value }.drop(1).collectLatest { announceImeSubtree(view, accessibility) }
    }
    Row(Modifier.fillMaxSize().padding(start = 5.dp, end = 1.dp), verticalAlignment = Alignment.CenterVertically) {
        // Scroll only the candidates. The row measures each card at its content
        // width so long words use more space without shrinking the touch targets.
        Row(Modifier.weight(1f).testTag("candidate_scroll").horizontalScroll(scroll),
            horizontalArrangement = Arrangement.spacedBy(2.dp), verticalAlignment = Alignment.CenterVertically) {
            state.candidates.forEachIndexed { index, candidate ->
                key(state.page, index) {
                    CandidateCard(candidate, index, state, prefs, send, Modifier.widthIn(min = 48.dp), compact = true)
                }
            }
        }
        if (openEmoji != null) ToolbarButton(ToolbarGlyph.Emoji, EMOJI_LABEL, onClick = openEmoji)
        Box(Modifier.size(48.dp).clip(RoundedCornerShape(10.dp))
            .combinedClickable(onClick = onExpand, onLongClick = settings, onLongClickLabel = "键盘设置"),
            contentAlignment = Alignment.Center) {
            Icon(if (expanded) Icons.Outlined.ExpandLess else Icons.Outlined.ExpandMore,
                if (expanded) "收起候选" else "展开候选", Modifier.size(20.dp), tint = LocalStudyColors.current.subtle)
        }
    }
}

@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun CandidateCard(candidate: Candidate, index: Int, state: EngineSnapshot, prefs: KeyboardPreferences,
                          send: (JSONObject) -> Unit, modifier: Modifier = Modifier, compact: Boolean = false) {
    val colors = LocalStudyColors.current
    val view = LocalView.current
    fun select() = send(event("select", "index" to index, "revision" to state.revision))
    fun inspect() = send(event("inspect", "index" to index, "revision" to state.revision))
    Column(modifier.background(if (index == state.highlighted) colors.tint else androidx.compose.ui.graphics.Color.Transparent, RoundedCornerShape(11.dp))
        .pointerInput(state.generation, state.revision, index) {
            detectTapGestures(onTap = { select() }, onLongPress = {
                if (prefs.haptics) view.performHapticFeedback(HapticFeedbackConstants.LONG_PRESS)
                inspect()
            })
        }
        .semantics(mergeDescendants = true) {
            contentDescription = candidate.chinese + if (state.showEnglish && candidate.english.isNotEmpty()) "，英文释义：${candidate.english}" else ""
            role = Role.Button
            selected = index == state.highlighted
            onClick(label = "输入中文") { select(); true }
            onLongClick(label = if (state.showEnglish) "查看释义与选词学习" else "查看选词学习") { inspect(); true }
        }.testTag("candidate_$index").heightIn(min = 48.dp).padding(horizontal = if (compact) 3.dp else 5.dp, vertical = if (compact) 3.dp else 7.dp),
        horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
        val maxLines = if (compact) 1 else Int.MAX_VALUE
        val label = Modifier.clearAndSetSemantics { }
        if (state.showEnglish) Text(candidate.english.ifEmpty { " " }, color = if (index == state.highlighted) colors.accent else colors.subtle,
            fontFamily = LocalLatinFont.current, fontSize = ((if (compact) 11 else 12) * prefs.textScale).sp,
            lineHeight = ((if (compact) 15 else 16) * prefs.textScale).sp, maxLines = maxLines, softWrap = !compact,
            textAlign = TextAlign.Center, modifier = label)
        Text(candidate.chinese, color = colors.ink, fontSize = ((if (compact) 18 else 20) * prefs.textScale).sp,
            lineHeight = ((if (compact) 24 else 28) * prefs.textScale).sp,
            fontWeight = if (prefs.skin == KeyboardSkin.SOFT_POP) FontWeight.Normal else FontWeight.Medium,
            maxLines = maxLines, softWrap = !compact, textAlign = TextAlign.Center, modifier = label)
    }
}

@Composable
private fun ReadyHint(state: EngineSnapshot, editor: EditorSpec, onRetry: () -> Unit, modifier: Modifier) {
    val colors = LocalStudyColors.current
    Box(modifier, contentAlignment = Alignment.Center) {
        if (state.error) TextButton(onClick = onRetry) { Text("重新准备键盘", color = colors.accent) }
        else Text(when {
            !state.ready -> "正在准备离线词库…"
            editor.sensitive -> "密码输入 · 不记录选词"
            state.asciiMode -> "English"
            state.pendingSchema != null -> "完成选词后切换方案"
            else -> "自在输入，顺便拾词"
        }, color = colors.subtle, fontSize = 12.sp, textAlign = TextAlign.Center, modifier = Modifier.padding(horizontal = 8.dp))
    }
}

@Composable
private fun Paging(state: EngineSnapshot, send: (JSONObject) -> Unit, modifier: Modifier = Modifier) {
    Row(modifier.heightIn(min = 48.dp), horizontalArrangement = Arrangement.SpaceEvenly, verticalAlignment = Alignment.CenterVertically) {
        ToolButton(Icons.Outlined.ChevronLeft, "上一页候选", state.page > 0) { send(event("page", "backwards" to true, "revision" to state.revision)) }
        Text("${state.page + 1}", fontSize = 12.sp, color = LocalStudyColors.current.subtle)
        ToolButton(Icons.Outlined.ChevronRight, "下一页候选", !state.lastPage) { send(event("page", "backwards" to false, "revision" to state.revision)) }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun ExpandedCandidates(state: EngineSnapshot, prefs: KeyboardPreferences, send: (JSONObject) -> Unit,
                               modifier: Modifier, settings: () -> Unit, close: () -> Unit) {
    Column(modifier.padding(horizontal = 5.dp)) {
        val scroll = key(state.generation, state.input, state.page) { rememberScrollState() }
        val minCardWidth = (92 * LocalDensity.current.fontScale).dp
        FlowRow(Modifier.weight(1f).fillMaxWidth().verticalScroll(scroll),
            horizontalArrangement = Arrangement.spacedBy(5.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
            state.candidates.forEachIndexed { index, candidate ->
                key(state.page, index) {
                    CandidateCard(candidate, index, state, prefs, send, Modifier.widthIn(min = minCardWidth))
                }
            }
        }
        Row(verticalAlignment = Alignment.CenterVertically) {
            TextButton(onClick = close, modifier = Modifier.heightIn(min = 48.dp)) { Text("返回键盘") }
            Paging(state, send, Modifier.weight(1f))
            ToolButton(Icons.Outlined.Settings, "键盘设置", onClick = settings)
        }
    }
}

private fun Char.isAsciiLetter() = this in 'a'..'z' || this in 'A'..'Z'
private val SecondaryKeys = "qwertyuiopasdfghjklzxcvbnm".zip("1234567890!@#¥%&*()~/-_:;?").toMap()

internal enum class ShiftMode(val description: String, val actionLabel: String) {
    LOWER("小写", "切换大写"),
    ONCE("大写", "切换小写"),
    LOCKED("大写锁定", "解除大写锁定");

    val upper get() = this != LOWER
}

internal data class KeySpec(val id: String, val text: String, val weight: Float = 1f, val function: Boolean = false,
                           val icon: ImageVector? = null, val secondary: String? = null, val spoken: String = text,
                           val letter: String? = null, val symbol: String? = null,
                           val shift: ShiftMode? = null, val caption: String = text) {
    val isPadDigit get() = id.length == 1 && id[0] in '0'..'9'
}

@Composable
private fun KeyboardRows(page: String, shift: ShiftMode, generation: Long, enabled: Boolean, asciiMode: Boolean,
                         composing: Boolean, canInspect: Boolean, prefs: KeyboardPreferences, editor: EditorSpec,
                         height: Dp, modifier: Modifier, onKey: (String, String) -> Unit, onLongKey: (String) -> Unit, onSwitchIme: () -> Unit) {
    val letters = page == "letters"
    val soft = prefs.skin == KeyboardSkin.SOFT_POP
    // Compact labels before the 320 dp mode key clips at 1.3x font scale.
    val largeLabels = LocalDensity.current.fontScale * prefs.textScale >= 1.25f
    val actionIcon = when {
        composing -> Icons.Outlined.Check
        editor.action == EditorInfo.IME_ACTION_SEARCH -> Icons.Outlined.Search
        editor.action == EditorInfo.IME_ACTION_SEND -> Icons.AutoMirrored.Outlined.Send
        editor.action in listOf(EditorInfo.IME_ACTION_NEXT, EditorInfo.IME_ACTION_GO, EditorInfo.IME_ACTION_PREVIOUS) -> Icons.AutoMirrored.Outlined.ArrowForward
        editor.action == EditorInfo.IME_ACTION_DONE -> Icons.Outlined.Check
        else -> Icons.AutoMirrored.Outlined.KeyboardReturn
    }
    val caption = when {
        composing -> "Done"
        editor.action == EditorInfo.IME_ACTION_SEARCH -> "Search"
        editor.action == EditorInfo.IME_ACTION_SEND -> "Send"
        editor.action == EditorInfo.IME_ACTION_NEXT -> "Next"
        editor.action == EditorInfo.IME_ACTION_PREVIOUS -> "Prev"
        editor.action == EditorInfo.IME_ACTION_GO -> "Go"
        editor.action == EditorInfo.IME_ACTION_DONE -> "Done"
        else -> "Enter"
    }
    val enter = KeySpec("enter", if (composing) "原样" else editor.actionLabel, 1.5f, true,
        if (soft) null else if (largeLabels) actionIcon else if (!composing && editor.actionLabel == "换行") Icons.AutoMirrored.Outlined.KeyboardReturn else null,
        spoken = if (composing) "输入原始拼写" else editor.actionLabel, caption = caption)
    val delete = KeySpec("delete", "", 1.45f, true, Icons.AutoMirrored.Outlined.Backspace, spoken = "删除", caption = "Del")
    CompositionLocalProvider(LocalGestureGeneration provides generation) {
        if (page == "numbers") {
            // A physical number pad keeps 1–2–3 and its side controls in the same places in RTL editors.
            CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
                NumberPad(height, prefs, enabled, asciiMode, composing, enter, delete, largeLabels, modifier, onKey, onLongKey, onSwitchIme)
            }
            return@CompositionLocalProvider
        }
        // Keep the old number row's punctuation available behind #+=, alongside the original symbol sheet.
        val common = page == "commonSymbols"
        val first = when { letters -> "qwertyuiop"; common -> "@#\$¥%&*()+"; asciiMode -> "!?.,:;\"'`~"; else -> "！？。，、；：“”‘" }
        val second = when { letters -> "asdfghjkl"; common -> "!?~:;/\\'\"|"; asciiMode -> "()[]{}<>\\|"; else -> "’（）【】《》〈〉" }
        val third = when { letters -> "zxcvbnm"; common -> "-_=<>[]"; asciiMode -> "_-+=&*%"; else -> "…—·～「」•" }
        fun face(char: Char, index: Int = -1): KeySpec {
            val text = if (letters && shift.upper) char.uppercase() else char.toString()
            if (letters && soft) {
                val symbol = SecondaryKeys.getValue(char).toString()
                return KeySpec(char.toString(), text, secondary = symbol, letter = char.uppercase(), symbol = symbol)
            }
            return KeySpec(char.toString(), text, secondary = if (letters && index >= 0) "1234567890"[index].toString() else null)
        }
        Column(modifier) {
            Row { first.forEachIndexed { index, char -> KeyCell(face(char, index), height, prefs, enabled, onKey, onLongKey) } }
            Row {
                if (second.length == 9) Spacer(Modifier.weight(.5f))
                second.forEach { char -> KeyCell(face(char), height, prefs, enabled, onKey, onLongKey) }
                if (second.length == 9) Spacer(Modifier.weight(.5f))
            }
            Row {
                KeyCell(if (letters) KeySpec("shift", "", 1.45f, true,
                    if (shift == ShiftMode.LOCKED) Icons.Outlined.KeyboardCapslock else Icons.Outlined.ArrowUpward,
                    spoken = shift.actionLabel, shift = shift)
                    else KeySpec("symbols", "123", 1.45f, true, if (largeLabels) Icons.Outlined.Dialpad else null, spoken = "数字键盘"), height, prefs, enabled, onKey, onLongKey)
                third.forEach { char -> KeyCell(face(char), height, prefs, enabled, onKey, onLongKey) }
                if (!letters) KeyCell(KeySpec("symbolSet", if (common) "1/2" else "2/2", function = true, spoken = "切换符号页"),
                    height, prefs, enabled, onKey, onLongKey)
                KeyCell(delete, height, prefs, enabled, onKey, onLongKey)
            }
            Row {
                KeyCell(KeySpec("details", "", 1.55f, true, Icons.Outlined.MenuBook, spoken = "查看当前候选词详情"),
                    height, prefs, enabled && canInspect, onKey, onLongKey)
                KeyCell(KeySpec("page", if (letters) "123" else "ABC", 1.15f, true,
                    if (largeLabels && !soft) { if (letters) Icons.Outlined.Dialpad else Icons.Outlined.Keyboard } else null,
                    spoken = if (letters) "数字与符号" else "字母键盘"), height, prefs, enabled, onKey, onLongKey,
                    specialLong = if (soft) { { onKey("symbols", "") } } else null, specialLongLabel = "更多符号")
                KeyCell(KeySpec("comma", if (asciiMode) "," else "，", spoken = "逗号"), height, prefs, enabled, onKey, onLongKey)
                KeyCell(KeySpec("space", if (asciiMode) "space" else "空格", 2.6f,
                    spoken = if (composing) "空格，输入原始拼写" else "空格"), height, prefs, enabled, onKey, onLongKey, onSwitchIme)
                KeyCell(KeySpec(".", if (asciiMode) "." else "。", spoken = "句号"), height, prefs, enabled,
                    { id, _ -> onKey(id, if (letters) "." else if (asciiMode) "." else "。") }, onLongKey)
                KeyCell(KeySpec("mode", if (largeLabels) { if (asciiMode) "英" else "中" } else if (asciiMode) "英/中" else "中/英", 1.2f, true, spoken = "切换中英文，长按切换输入法"), height, prefs,
                    enabled && !editor.sensitive, onKey, onLongKey, onSwitchIme)
                KeyCell(enter, height, prefs, enabled, onKey, onLongKey)
            }
        }
    }
}

// The number pad's continuous operator strip uses the same painted edges as a regular key.
// Insets are visual only: the touch targets still meet at their outer bounds.
internal data class KeyCapFrame(val side: Dp, val vertical: Dp, val radius: Dp) {
    fun inset(modifier: Modifier) = modifier.padding(horizontal = side, vertical = vertical)

    fun defaultFace(modifier: Modifier, pressed: Boolean, fill: () -> Color) = inset(modifier).drawWithCache {
        val corner = CornerRadius(radius.toPx())
        onDrawBehind {
            if (!pressed) {
                drawRoundRect(Color.Black.copy(alpha = .06f), topLeft = Offset(0f, 1.dp.toPx()), size = size, cornerRadius = corner)
                drawRoundRect(Color.Black.copy(alpha = .08f), topLeft = Offset(0f, .5.dp.toPx()), size = size, cornerRadius = corner)
            }
            drawRoundRect(fill(), cornerRadius = corner)
        }
    }
}

internal val DefaultKeyCap = KeyCapFrame(2.5.dp, 3.dp, 9.dp)
private val TightKeyCap = DefaultKeyCap.copy(side = .5.dp)
internal fun softPopKeyCap(height: Dp) = KeyCapFrame((height * .038f).coerceIn(1.5.dp, 2.6.dp), height * .076f, height * .18f)

@Composable
internal fun RowScope.KeyCell(key: KeySpec, height: Dp, prefs: KeyboardPreferences, enabled: Boolean,
                            onKey: (String, String) -> Unit, onLongKey: (String) -> Unit, specialLong: (() -> Unit)? = null,
                            specialLongLabel: String = "切换输入法") {
    val colors = LocalStudyColors.current
    val view = LocalView.current
    val gestureGeneration = LocalGestureGeneration.current
    val soft = prefs.skin == KeyboardSkin.SOFT_POP
    val tightLetters = LocalDensity.current.fontScale * prefs.textScale > 2.1f && !key.function && key.id != "space"
    var pressed by remember { mutableStateOf(false) }
    val action by rememberUpdatedState(newValue = { onKey(key.id, key.text) })
    val longAction by rememberUpdatedState(newValue = specialLong ?: key.secondary?.let { { onLongKey(it) } })
    fun feedback() { if (prefs.haptics) view.performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP) }
    Box(Modifier.weight(key.weight).height(height).testTag("key_${key.id}").semantics {
        contentDescription = key.spoken
        role = Role.Button
        if (!enabled) disabled()
        onClick { if (enabled) { feedback(); action(); true } else false }
        key.shift?.let { stateDescription = it.description }
        if (longAction != null) onLongClick(label = if (specialLong != null) specialLongLabel else "输入${key.secondary}") {
            if (enabled) { longAction?.invoke(); true } else false
        }
    }.pointerInput(key.id, key.secondary, enabled, prefs.haptics, prefs.skin, gestureGeneration) {
        if (key.id == "delete") coroutineScope {
            awaitEachGesture {
                awaitFirstDown()
                if (!enabled) return@awaitEachGesture
                pressed = true
                feedback()
                action()
                val repeating = launch { delay(360); while (isActive) { action(); delay(55) } }
                try { waitForUpOrCancellation() } finally { repeating.cancel(); pressed = false }
            }
        } else awaitEachGesture {
            val down = awaitFirstDown()
            if (!enabled) return@awaitEachGesture
            down.consume()
            pressed = true
            try {
                val released = if (longAction != null) withTimeoutOrNull(480L) {
                    awaitKeyRelease(down.id, down.position, viewConfiguration.touchSlop)
                } else awaitKeyRelease(down.id, down.position, viewConfiguration.touchSlop)
                when (released) {
                    true -> { feedback(); action() }
                    null -> {
                        feedback()
                        longAction?.invoke()
                        waitForUpOrCancellation()
                    }
                    false -> Unit
                }
            } finally { pressed = false }
        }
    }, contentAlignment = Alignment.Center) {
        if (soft) {
            SoftPopKeyFace(key, prefs, height, enabled, pressed)
            return@Box
        }
        val accented = key.id == "enter" || key.shift?.upper == true
        val base = when { accented -> colors.accent; key.function -> colors.function; else -> colors.key }
        val fill = animateColorAsState(if (pressed) colors.tint else base, tween(if (prefs.reduceMotion) 0 else 75), label = "keyPress")
        val cap = if (tightLetters) TightKeyCap else DefaultKeyCap
        Box(cap.defaultFace(Modifier.fillMaxSize(), pressed) { fill.value }, contentAlignment = Alignment.Center) {
            val ink = if (accented && !pressed) colors.onAccent else if (key.id == "space") colors.subtle else colors.ink
            if (key.icon != null) Icon(key.icon, null, Modifier.size(21.dp), tint = if (enabled) ink else ink.copy(alpha = .4f))
            else Text(key.text, color = ink, fontSize = ((when { key.isPadDigit -> 24f; key.function || key.id == "space" -> 12f; else -> 19f }) * prefs.textScale).sp,
                lineHeight = ((if (key.isPadDigit) 27 else 23) * prefs.textScale).sp, fontFamily = if (!key.function && key.id != "space") FontFamily.Monospace else FontFamily.SansSerif,
                textAlign = TextAlign.Center, maxLines = if (key.id == "enter") 2 else 1, overflow = TextOverflow.Clip,
                modifier = Modifier.padding(horizontal = if (tightLetters) 0.dp else 1.dp).clearAndSetSemantics { })
        }
    }
}

private suspend fun AwaitPointerEventScope.awaitKeyRelease(id: PointerId, start: Offset, slop: Float): Boolean {
    while (true) {
        val event = awaitPointerEvent()
        val change = event.changes.firstOrNull { it.id == id } ?: return false
        if (change.isConsumed || (change.position - start).getDistance() > slop ||
            change.position.x !in 0f..size.width.toFloat() || change.position.y !in 0f..size.height.toFloat() ||
            event.changes.any { it.id != id && it.pressed }) return false
        if (change.changedToUpIgnoreConsumed()) {
            change.consume()
            return true
        }
    }
}
