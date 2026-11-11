// SPDX-License-Identifier: GPL-3.0-or-later
package org.studyime.android.ui

import android.provider.Settings
import android.os.SystemClock
import android.view.HapticFeedbackConstants
import android.view.View
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityManager
import android.view.inputmethod.EditorInfo
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.animateContentSize
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
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.itemsIndexed as gridItemsIndexed
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.rememberScrollState
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
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.draw.drawWithContent
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.Layout
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.*
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Popup
import androidx.compose.ui.window.PopupProperties
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.flow.drop
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import org.json.JSONObject
import org.studyime.android.engine.*
import org.studyime.android.diagnostics.StartupTimings
import org.studyime.android.diagnostics.StartupTimings.Phase
import org.studyime.android.ime.EditorSpec
import org.studyime.android.ime.InputMetrics
import org.studyime.android.settings.KeyboardPreferences

private val LocalGestureGeneration = staticCompositionLocalOf { 0L }

@OptIn(ExperimentalComposeUiApi::class, ExperimentalFoundationApi::class)
@Composable
fun StudyKeyboard(
    state: EngineSnapshot, prefs: KeyboardPreferences, editor: EditorSpec,
    update: ((KeyboardPreferences) -> KeyboardPreferences) -> Unit,
    send: (JSONObject) -> Unit, onSettings: () -> Unit,
    onSwitchIme: () -> Unit, onRetry: () -> Unit,
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
    var upper by remember(state.generation) { mutableStateOf(false) }
    var expanded by remember(state.generation) { mutableStateOf(false) }
    var quickSettings by remember(state.generation) { mutableStateOf(false) }
    val currentState by rememberUpdatedState(state)
    // Keep letter keys independent of candidate revisions. The callback reads
    // the current snapshot at activation; a new editor still cancels gestures.
    val onKey = remember(state.generation, send) {
        { id: String, text: String ->
            val latest = currentState
            when (id) {
                "shift" -> { upper = !upper; if (!latest.asciiMode) send(event("mode", "ascii" to true)) }
                "mode" -> { upper = false; send(event("mode", "ascii" to !latest.asciiMode)) }
                "page" -> { page = if (page == "letters") "numbers" else "letters" }
                "symbols" -> { page = if (page == "symbols") "numbers" else "symbols" }
                "delete" -> send(event("key", "code" to 0xff08))
                "enter" -> send(event("key", "code" to 0xff0d))
                "space" -> send(event("key", "code" to 32))
                else -> {
                    if ((page == "letters" && text.length == 1) || (text == "'" && latest.input.isNotEmpty() && !latest.asciiMode))
                        send(event("key", "code" to text[0].code))
                    else send(event("literal", "text" to text))
                    if (upper) upper = false
                }
            }
        }
    }
    val onLongKey = remember(send) { { text: String -> send(event("literal", "text" to text)) } }
    LaunchedEffect(state.generation, state.revision, state.ready, page, expanded, quickSettings, upper, prefs.theme) {
        announceImeSubtree(view, accessibility)
    }
    val keyHeight = maxOf(if (landscape) 40f else 48f, (if (landscape) 42f else 52f) * prefs.keyHeight,
        23f * density.fontScale * prefs.textScale + 10f).dp
    val keyRowsHeight = keyHeight * 4
    val active = state.ready && !state.error

    Column(Modifier.fillMaxWidth().background(colors.board).navigationBarsPadding().drawWithContent {
        drawContent()
        InputMetrics.frame(state.generation, state.revision, state.ready && !state.error)
    }
        .semantics { testTagsAsResourceId = true }.testTag("study_keyboard")) {
        Row(Modifier.fillMaxWidth().heightIn(min = 48.dp).padding(horizontal = 8.dp), verticalAlignment = Alignment.CenterVertically) {
            TextButton(onClick = { quickSettings = !quickSettings }, contentPadding = PaddingValues(horizontal = 8.dp), modifier = Modifier.heightIn(min = 48.dp).weight(1f).wrapContentWidth(Alignment.Start)) {
                Icon(if (editor.sensitive) Icons.Outlined.Lock else Icons.Outlined.Spa, null, Modifier.size(19.dp), tint = colors.accent)
                Spacer(Modifier.width(6.dp))
                Text(if (editor.sensitive) "安全输入" else "拾词", color = colors.accent, fontWeight = FontWeight.SemiBold,
                    fontSize = 13.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
            ToolButton(if (colors.dark) Icons.Outlined.LightMode else Icons.Outlined.DarkMode, "切换浅深色", onClick = {
                update { it.copy(theme = if (colors.dark) "light" else "dark") }
            })
            ToolButton(Icons.Outlined.MenuBook, "查看完整释义", active && state.showEnglish && state.candidates.isNotEmpty()) {
                send(event("inspect", "index" to state.highlighted, "revision" to state.revision))
            }
            Row(Modifier.heightIn(min = 48.dp).clip(RoundedCornerShape(12.dp))
                .combinedClickable(enabled = !editor.sensitive, onClick = { update { it.copy(showEnglish = !it.showEnglish) } })
                .padding(horizontal = 8.dp).semantics(mergeDescendants = true) {
                    contentDescription = "显示英文释义"
                    stateDescription = if (state.showEnglish) "开启" else "关闭"
                    role = Role.Switch
                }, verticalAlignment = Alignment.CenterVertically) {
                Text("英语", fontSize = 12.sp, color = colors.accent)
                Spacer(Modifier.width(6.dp))
                Box(Modifier.size(30.dp, 18.dp).background(if (state.showEnglish) colors.accent else colors.subtle, RoundedCornerShape(10.dp))) {
                    Box(Modifier.align(if (state.showEnglish) Alignment.CenterEnd else Alignment.CenterStart).padding(3.dp)
                        .size(12.dp).background(if (state.showEnglish) colors.onAccent else colors.paper, RoundedCornerShape(8.dp)))
                }
            }
        }

        val keys: @Composable (Modifier) -> Unit = { modifier ->
            if (expanded && state.candidates.isNotEmpty()) {
                ExpandedCandidates(state, prefs, send, modifier.height(keyRowsHeight)) { expanded = false }
            } else {
                KeyboardRows(page, upper, state.generation, active, state.asciiMode, state.input.isNotEmpty(),
                    effectivePrefs, editor, keyHeight, modifier, onKey, onLongKey, onSwitchIme,
                )
            }
        }

        if (landscape) {
            Row(Modifier.fillMaxWidth().padding(horizontal = 5.dp, vertical = 3.dp), verticalAlignment = Alignment.Bottom) {
                Column(Modifier.widthIn(max = 270.dp).weight(.34f).height(keyRowsHeight).padding(end = 7.dp)) {
                    Preedit(state, prefs)
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
            Preedit(state, prefs)
            CandidateStrip(state, effectivePrefs, editor, send, onRetry, expanded) { expanded = !expanded }
            keys(Modifier.fillMaxWidth().padding(horizontal = 4.dp))
        }
        Spacer(Modifier.height(if (landscape) 3.dp else 7.dp))
    }

    state.target?.let { target ->
        val vertical = with(density) { -(keyRowsHeight + 14.dp).roundToPx() }
        Popup(alignment = Alignment.BottomCenter, offset = IntOffset(0, vertical),
            onDismissRequest = { send(event("dismiss")) },
            properties = PopupProperties(focusable = false, clippingEnabled = true, dismissOnBackPress = true, dismissOnClickOutside = true)) {
            DefinitionPanel(target, state.showEnglish, prefs, send,
                Modifier.widthIn(max = 480.dp).fillMaxWidth(.92f).heightIn(max = if (landscape) (configuration.screenHeightDp - 48).dp else 430.dp))
        }
    }
    if (quickSettings) {
        Popup(alignment = Alignment.BottomCenter, offset = IntOffset(0, with(density) { -(keyRowsHeight + 14.dp).roundToPx() }),
            onDismissRequest = { quickSettings = false }, properties = PopupProperties(focusable = false, clippingEnabled = true)) {
            QuickSettings(prefs, update, state.input.isNotEmpty(), Modifier.widthIn(max = 480.dp).fillMaxWidth(.92f)
                .heightIn(max = if (landscape) 210.dp else 340.dp), close = { quickSettings = false }, allSettings = {
                quickSettings = false
                onSettings()
            })
        }
    }
    val compositionFinished = SystemClock.elapsedRealtimeNanos()
    SideEffect {
        InputMetrics.composed(state.generation, state.revision, compositionStarted, compositionFinished)
        StartupTimings.record(Phase.COMPOSITION, compositionStarted, compositionFinished)
    }
}

private suspend fun announceImeSubtree(view: View, accessibility: AccessibilityManager) {
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
private fun ToolButton(icon: ImageVector, description: String, enabled: Boolean = true, onClick: () -> Unit) {
    val colors = LocalStudyColors.current
    IconButton(onClick = onClick, enabled = enabled, modifier = Modifier.size(48.dp)) {
        Icon(icon, description, Modifier.size(20.dp), tint = if (enabled) colors.subtle else colors.subtle.copy(alpha = .5f))
    }
}

@Composable
private fun Preedit(state: EngineSnapshot, prefs: KeyboardPreferences) {
    val colors = LocalStudyColors.current
    Row(Modifier.fillMaxWidth().heightIn(min = 27.dp).padding(horizontal = 17.dp, vertical = 1.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(state.preedit.ifEmpty { state.input }, Modifier.weight(1f), color = colors.accent,
            fontSize = (13 * prefs.textScale).sp, lineHeight = (18 * prefs.textScale).sp,
            maxLines = 1, overflow = TextOverflow.Ellipsis)
        Spacer(Modifier.width(10.dp))
        Text(if (state.asciiMode) "英文" else schemaName(state.schema).removeSuffix("双拼") +
            (state.pendingSchema?.let { " → " + schemaName(it).removeSuffix("双拼") } ?: ""),
            fontSize = 11.sp, color = colors.subtle, maxLines = 1)
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun QuickSettings(prefs: KeyboardPreferences, update: ((KeyboardPreferences) -> KeyboardPreferences) -> Unit,
                          composing: Boolean, modifier: Modifier, close: () -> Unit, allSettings: () -> Unit) {
    val colors = LocalStudyColors.current
    Surface(modifier.shadow(12.dp, RoundedCornerShape(19.dp)), color = colors.paper, shape = RoundedCornerShape(19.dp),
        border = androidx.compose.foundation.BorderStroke(1.dp, colors.line)) {
        Column(Modifier.verticalScroll(rememberScrollState()).padding(horizontal = 16.dp, vertical = 4.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("输入方式", Modifier.weight(1f), fontWeight = FontWeight.SemiBold, color = colors.ink)
                ToolButton(Icons.Outlined.Close, "关闭快捷设置", onClick = close)
            }
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
            TextButton(onClick = allSettings, modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp)) { Text("全部设置") }
        }
    }
}

@Composable
private fun CandidateStrip(state: EngineSnapshot, prefs: KeyboardPreferences, editor: EditorSpec, send: (JSONObject) -> Unit,
                           onRetry: () -> Unit, expanded: Boolean, onExpand: () -> Unit) {
    val fontScale = LocalDensity.current.fontScale
    // Keep the input window height stable as the first candidate arrives.
    // Relayout of a bottom-anchored IME during a rapid touch can cancel that
    // gesture even when the final key bounds are unchanged.
    val contentHeight = (maxOf(40f, (if (state.showEnglish) 44f else 28f) * fontScale * prefs.textScale) + 16f).dp
    Box(Modifier.fillMaxWidth().padding(start = 7.dp, end = 3.dp, bottom = 5.dp)
        .animateContentSize(tween(if (prefs.reduceMotion) 0 else 190)).heightIn(min = contentHeight)) {
        if (state.candidates.isEmpty()) {
            ReadyHint(state, editor, onRetry, Modifier.fillMaxWidth().heightIn(min = contentHeight))
        } else {
            val scroll = rememberScrollState()
            val view = LocalView.current
            val accessibility = remember(view) { view.context.getSystemService(AccessibilityManager::class.java) }
            LaunchedEffect(scroll) {
                snapshotFlow { scroll.value }.drop(1).collectLatest { announceImeSubtree(view, accessibility) }
            }
            Row(verticalAlignment = Alignment.CenterVertically) {
                // Measure the five slots directly. Reading BoxWithConstraints
                // from the changing candidate composition otherwise requires
                // a subcomposition inside the input window's measure pass.
                Layout(modifier = Modifier.weight(1f).testTag("candidate_scroll").horizontalScroll(scroll), content = {
                    state.candidates.forEachIndexed { index, candidate ->
                        key(state.page, index) {
                            CandidateCard(candidate, index, state, prefs, send)
                        }
                    }
                }) { measurables, constraints ->
                    // Row.weight fixes the viewport width; horizontalScroll
                    // keeps that minimum while relaxing the maximum width.
                    val viewport = constraints.minWidth
                    val visible = (viewport / (88.dp.toPx() * fontScale * prefs.textScale)).toInt().coerceIn(1, 3)
                    val slot = (viewport / visible).coerceAtLeast(1)
                    val gap = 3.dp.roundToPx()
                    val cardWidth = (slot - gap).coerceAtLeast(0)
                    val cards = measurables.map {
                        it.measure(constraints.copy(minWidth = cardWidth, maxWidth = cardWidth, minHeight = 0))
                    }
                    val height = (cards.maxOfOrNull { it.height } ?: 0).coerceIn(constraints.minHeight, constraints.maxHeight)
                    layout((slot * cards.size - gap).coerceAtLeast(viewport), height) {
                        cards.forEachIndexed { index, card -> card.placeRelative(index * slot, (height - card.height) / 2) }
                    }
                }
                ToolButton(if (expanded) Icons.Outlined.ExpandLess else Icons.Outlined.ExpandMore,
                    if (expanded) "收起候选" else "展开候选", onClick = onExpand)
            }
        }
    }
}

@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun CandidateCard(candidate: Candidate, index: Int, state: EngineSnapshot, prefs: KeyboardPreferences,
                          send: (JSONObject) -> Unit, modifier: Modifier = Modifier) {
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
        }.testTag("candidate_$index").padding(horizontal = 5.dp, vertical = 7.dp).heightIn(min = 40.dp),
        horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
        if (state.showEnglish) Text(candidate.english.ifEmpty { " " }, color = colors.accent, fontSize = (12 * prefs.textScale).sp,
            lineHeight = (16 * prefs.textScale).sp, maxLines = 1, overflow = TextOverflow.Ellipsis, textAlign = TextAlign.Center,
            modifier = Modifier.fillMaxWidth().clearAndSetSemantics { })
        Text(candidate.chinese, color = colors.ink, fontSize = (20 * prefs.textScale).sp,
            lineHeight = (28 * prefs.textScale).sp, fontWeight = FontWeight.Medium, maxLines = 1, overflow = TextOverflow.Ellipsis,
            textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth().clearAndSetSemantics { })
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

@Composable
private fun ExpandedCandidates(state: EngineSnapshot, prefs: KeyboardPreferences, send: (JSONObject) -> Unit,
                               modifier: Modifier, close: () -> Unit) {
    Column(modifier.padding(horizontal = 5.dp)) {
        LazyVerticalGrid(columns = GridCells.Adaptive((92 * LocalDensity.current.fontScale).dp), modifier = Modifier.weight(1f),
            horizontalArrangement = Arrangement.spacedBy(5.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
            gridItemsIndexed(state.candidates) { index, candidate -> CandidateCard(candidate, index, state, prefs, send) }
        }
        Row(verticalAlignment = Alignment.CenterVertically) {
            TextButton(onClick = close, modifier = Modifier.heightIn(min = 48.dp)) { Text("返回键盘") }
            Paging(state, send, Modifier.weight(1f))
        }
    }
}

private data class KeySpec(val id: String, val text: String, val weight: Float = 1f, val function: Boolean = false,
                           val icon: ImageVector? = null, val secondary: String? = null, val spoken: String = text)

@Composable
private fun KeyboardRows(page: String, upper: Boolean, generation: Long, enabled: Boolean, asciiMode: Boolean,
                         composing: Boolean, prefs: KeyboardPreferences, editor: EditorSpec,
                         height: Dp, modifier: Modifier, onKey: (String, String) -> Unit, onLongKey: (String) -> Unit, onSwitchIme: () -> Unit) {
    val letters = page == "letters"
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
    val first = when (page) { "numbers" -> "1234567890"; "symbols" -> if (asciiMode) "!?.,:;\"'`~" else "！？。，、；：“”‘"; else -> "qwertyuiop" }
    val second = when (page) { "numbers" -> if (asciiMode) "@#$%&*()-+" else "@#¥%&*()-+"; "symbols" -> if (asciiMode) "()[]{}<>\\|" else "’（）【】《》〈〉"; else -> "asdfghjkl" }
    val third = when (page) { "numbers" -> ".,'\":/?"; "symbols" -> if (asciiMode) "_-+=&*%" else "…—·～「」•"; else -> "zxcvbnm" }
    fun letter(char: Char, index: Int = -1) = KeySpec(char.toString(), if (letters && upper) char.uppercase() else char.toString(),
        secondary = if (letters && index >= 0) "1234567890"[index].toString() else null)
    CompositionLocalProvider(LocalGestureGeneration provides generation) {
    Column(modifier) {
        Row { first.forEachIndexed { index, char -> KeyCell(letter(char, index), height, prefs, enabled, onKey, onLongKey) } }
        Row {
            if (second.length == 9) Spacer(Modifier.weight(.5f))
            second.forEach { char -> KeyCell(letter(char), height, prefs, enabled, onKey, onLongKey) }
            if (second.length == 9) Spacer(Modifier.weight(.5f))
        }
        Row {
            KeyCell(if (letters) KeySpec("shift", "", 1.45f, true, if (upper) Icons.Outlined.KeyboardCapslock else Icons.Outlined.ArrowUpward, spoken = "切换大写")
                else KeySpec("symbols", if (page == "symbols") "123" else "符号", 1.45f, true,
                    if (largeLabels) Icons.Outlined.MoreHoriz else null), height, prefs, enabled, onKey, onLongKey)
            third.forEach { char -> KeyCell(letter(char), height, prefs, enabled, onKey, onLongKey) }
            KeyCell(KeySpec("delete", "", 1.45f, true, Icons.AutoMirrored.Outlined.Backspace, spoken = "删除"), height, prefs, enabled, onKey, onLongKey)
        }
        Row {
            KeyCell(KeySpec("page", if (letters) "?123" else "ABC", 1.4f, true,
                if (largeLabels) { if (letters) Icons.Outlined.Dialpad else Icons.Outlined.Keyboard } else null,
                spoken = if (letters) "数字与符号" else "字母键盘"), height, prefs, enabled, onKey, onLongKey)
            KeyCell(KeySpec("mode", if (largeLabels) { if (asciiMode) "英" else "中" } else if (asciiMode) "英/中" else "中/英", 1.35f, true, spoken = "切换中英文，长按切换输入法"), height, prefs,
                enabled && !editor.sensitive, onKey, onLongKey, onSwitchIme)
            KeyCell(KeySpec("space", if (asciiMode) "space" else "拾词", 4.6f, spoken = "空格，选取中文候选"), height, prefs, enabled, onKey, onLongKey, onSwitchIme)
            KeyCell(KeySpec(".", if (asciiMode) "." else "。", 1.1f, spoken = "句号"), height, prefs, enabled,
                { id, _ -> onKey(id, if (letters) "." else if (asciiMode) "." else "。") }, onLongKey)
            KeyCell(KeySpec("enter", if (composing) "选词" else editor.actionLabel, 1.65f, true,
                if (largeLabels) actionIcon else if (!composing && editor.actionLabel == "换行") Icons.AutoMirrored.Outlined.KeyboardReturn else null,
                spoken = if (composing) "确认中文选词" else editor.actionLabel), height, prefs, enabled, onKey, onLongKey)
        }
    }
    }
}

@Composable
private fun RowScope.KeyCell(key: KeySpec, height: Dp, prefs: KeyboardPreferences, enabled: Boolean,
                            onKey: (String, String) -> Unit, onLongKey: (String) -> Unit, specialLong: (() -> Unit)? = null) {
    val colors = LocalStudyColors.current
    val view = LocalView.current
    val gestureGeneration = LocalGestureGeneration.current
    val tightLetters = LocalDensity.current.fontScale * prefs.textScale > 2.1f && !key.function && key.id != "space"
    var pressed by remember { mutableStateOf(false) }
    val action by rememberUpdatedState(newValue = { onKey(key.id, key.text) })
    val longAction by rememberUpdatedState(newValue = specialLong ?: key.secondary?.let { { onLongKey(it) } })
    fun feedback() { if (prefs.haptics) view.performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP) }
    val base = when { key.id == "enter" -> colors.accent; key.function -> colors.function; else -> colors.key }
    val fill = animateColorAsState(if (pressed) colors.tint else base, tween(if (prefs.reduceMotion) 0 else 75), label = "keyPress")
    Box(Modifier.weight(key.weight).height(height).testTag("key_${key.id}").semantics {
        contentDescription = key.spoken
        role = Role.Button
        if (!enabled) disabled()
        onClick { if (enabled) { feedback(); action(); true } else false }
        if (longAction != null) onLongClick(label = if (specialLong != null) "切换输入法" else "输入${key.secondary}") {
            if (enabled) { longAction?.invoke(); true } else false
        }
    }.pointerInput(key.id, enabled, prefs.haptics, gestureGeneration) {
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
        } else detectTapGestures(
            onPress = { if (enabled) { pressed = true; try { tryAwaitRelease() } finally { pressed = false } } },
            onTap = { if (enabled) { feedback(); action() } },
            onLongPress = if (longAction == null) null else { _ -> if (enabled) { feedback(); longAction?.invoke() } },
        )
    }.padding(horizontal = if (tightLetters) .5.dp else 2.5.dp, vertical = 3.dp), contentAlignment = Alignment.Center) {
        Box(Modifier.fillMaxSize().drawBehind {
            val corner = CornerRadius(9.dp.toPx())
            // A shallow contact shadow does not need a RenderNode/elevation
            // layer for every key, or its first-frame shadow shader program.
            if (!pressed) {
                drawRoundRect(Color.Black.copy(alpha = .06f), topLeft = Offset(0f, 1.dp.toPx()), size = size, cornerRadius = corner)
                drawRoundRect(Color.Black.copy(alpha = .08f), topLeft = Offset(0f, .5.dp.toPx()), size = size, cornerRadius = corner)
            }
            drawRoundRect(fill.value, cornerRadius = corner)
        }, contentAlignment = Alignment.Center) {
            val ink = if (key.id == "enter" && !pressed) colors.onAccent else if (key.id == "space") colors.subtle else colors.ink
            if (key.icon != null) Icon(key.icon, null, Modifier.size(21.dp), tint = ink)
            else Text(key.text, color = ink, fontSize = ((if (key.function || key.id == "space") 12f else 19f) * prefs.textScale).sp,
                lineHeight = (23 * prefs.textScale).sp, fontFamily = if (!key.function && key.id != "space") FontFamily.Monospace else FontFamily.SansSerif,
                textAlign = TextAlign.Center, maxLines = if (key.id == "enter") 2 else 1, overflow = TextOverflow.Clip,
                modifier = Modifier.padding(horizontal = if (tightLetters) 0.dp else 1.dp).clearAndSetSemantics { })
        }
    }
}

@OptIn(ExperimentalComposeUiApi::class)
@Composable
private fun DefinitionPanel(target: CandidateTarget, showEnglish: Boolean, prefs: KeyboardPreferences,
                            send: (JSONObject) -> Unit, modifier: Modifier) {
    val colors = LocalStudyColors.current
    Surface(modifier.shadow(12.dp, RoundedCornerShape(19.dp)).semantics { testTagsAsResourceId = true }.testTag("definition_panel"),
        color = colors.paper, shape = RoundedCornerShape(19.dp), border = androidx.compose.foundation.BorderStroke(1.dp, colors.line)) {
        Column(Modifier.padding(start = 18.dp, end = 18.dp, bottom = 12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(target.chinese, Modifier.weight(1f), color = colors.ink, fontSize = (16 * prefs.textScale).sp, fontWeight = FontWeight.SemiBold)
                ToolButton(Icons.Outlined.Close, "关闭释义") { send(event("dismiss")) }
            }
            if (showEnglish) {
                Column(Modifier.weight(1f, fill = false).verticalScroll(rememberScrollState())) {
                    Text(target.english.ifEmpty { "暂未收录释义" }, color = colors.accent, fontSize = (25 * prefs.textScale).sp,
                        lineHeight = (33 * prefs.textScale).sp, fontWeight = FontWeight.Medium)
                    Spacer(Modifier.height(7.dp))
                    Text(if (target.reason == "partial-composition") "选完整个词后可输入英文" else "本机开发词库 · 释义待审核",
                        fontSize = 11.sp, color = colors.subtle)
                }
                Spacer(Modifier.height(12.dp))
                Button(onClick = { send(event("english", "token" to target.token)) }, enabled = target.canCommitEnglish,
                    shape = RoundedCornerShape(11.dp), modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp).testTag("commit_english")) {
                    Text("输入英文", fontSize = 14.sp)
                }
            }
            TextButton(onClick = { send(event("forget", "token" to target.token)) }, modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp)) {
                Text("忘记这个词的选词习惯", fontSize = 13.sp, textAlign = TextAlign.Center)
            }
        }
    }
}
