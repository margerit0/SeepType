// SPDX-License-Identifier: GPL-3.0-or-later
package org.studyime.android.ui

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Close
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.key
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.ExperimentalComposeUiApi
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.testTagsAsResourceId
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.*
import androidx.compose.ui.window.Popup
import androidx.compose.ui.window.PopupPositionProvider
import androidx.compose.ui.window.PopupProperties
import org.json.JSONObject
import org.studyime.android.engine.CandidateTarget
import org.studyime.android.engine.WordSense
import org.studyime.android.engine.event

private class AboveKeyboard(private val gap: Int) : PopupPositionProvider {
    override fun calculatePosition(anchorBounds: IntRect, windowSize: IntSize, layoutDirection: LayoutDirection,
                                   popupContentSize: IntSize): IntOffset = IntOffset(
        anchorBounds.center.x - popupContentSize.width / 2,
        // The anchor is relative to the IME window. A negative offset is
        // how the popup extends above it; Android fits it to the display.
        anchorBounds.top - gap - popupContentSize.height,
    )
}

@OptIn(ExperimentalComposeUiApi::class, ExperimentalLayoutApi::class)
@Composable
internal fun WordDetailPopup(target: CandidateTarget, showEnglish: Boolean, scale: Float, maxHeight: Dp,
                             send: (JSONObject) -> Unit) {
    val colors = LocalStudyColors.current
    val gap = with(LocalDensity.current) { 3.dp.roundToPx() }
    val position = remember(gap) { AboveKeyboard(gap) }
    val close = { send(event("dismiss")) }
    Popup(popupPositionProvider = position, onDismissRequest = close,
        properties = PopupProperties(focusable = false, dismissOnClickOutside = true)) {
        Box(Modifier.widthIn(max = 512.dp).fillMaxWidth().padding(horizontal = 16.dp, vertical = 5.dp)) {
            Surface(Modifier.fillMaxWidth().heightIn(max = maxHeight)
                .semantics { testTagsAsResourceId = true }.testTag("definition_panel"),
                color = colors.paper, shape = RoundedCornerShape(19.dp), border = BorderStroke(1.dp, colors.line),
                shadowElevation = 9.dp) {
                Column(Modifier.padding(horizontal = 18.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        FlowRow(Modifier.weight(1f).padding(vertical = 4.dp),
                            horizontalArrangement = Arrangement.spacedBy(8.dp), itemVerticalAlignment = Alignment.CenterVertically) {
                            Text(target.chinese, color = colors.ink, fontSize = (16 * scale).sp, fontWeight = FontWeight.SemiBold)
                            if (showEnglish && target.pinyin.isNotEmpty()) {
                                Text(target.pinyin, fontFamily = LocalLatinFont.current, color = colors.subtle,
                                    fontSize = (13 * scale).sp, letterSpacing = 0.sp)
                            }
                        }
                        ToolButton(Icons.Outlined.Close, "关闭释义", onClick = close)
                    }
                    if (showEnglish) {
                        val senses = remember(target) {
                            target.senses.ifEmpty { if (target.english.isBlank()) emptyList() else listOf(WordSense(target.english)) }
                        }
                        val scroll = key(target.token) { rememberScrollState() }
                        Column(Modifier.weight(1f, fill = false).verticalScroll(scroll).testTag("definition_senses")) {
                            if (senses.isEmpty()) {
                                Text("暂未收录释义", color = colors.subtle, fontSize = (14 * scale).sp)
                            }
                            senses.forEachIndexed { index, sense ->
                                if (index > 0) HorizontalDivider(Modifier.padding(vertical = 5.dp), color = colors.line)
                                SenseDetails(sense, isDefault = index == 0 && senses.size > 1, scale = scale)
                            }
                            if (target.reason == "partial-composition") {
                                Text("选完整个词后可输入英文", Modifier.padding(top = 5.dp), color = colors.subtle, fontSize = (11 * scale).sp)
                            }
                        }
                        Spacer(Modifier.height(10.dp))
                        Button(onClick = { send(event("english", "token" to target.token)) }, enabled = target.canCommitEnglish,
                            shape = RoundedCornerShape(12.dp), contentPadding = PaddingValues(horizontal = 8.dp, vertical = 8.dp),
                            modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp).testTag("commit_english")) {
                            Text(if (target.english.isBlank()) "输入英文" else "输入 ${target.english}",
                                fontFamily = LocalLatinFont.current, fontSize = (14 * scale).sp,
                                lineHeight = (18 * scale).sp, maxLines = 2, overflow = TextOverflow.Ellipsis,
                                textAlign = TextAlign.Center, letterSpacing = 0.sp)
                        }
                    }
                    TextButton(onClick = { send(event("forget", "token" to target.token)) },
                        modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp).testTag("forget_candidate")) {
                        Text("忘记这个词的选词习惯", fontSize = (13 * scale).sp, textAlign = TextAlign.Center)
                    }
                }
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun SenseDetails(sense: WordSense, isDefault: Boolean, scale: Float) {
    val colors = LocalStudyColors.current
    val latin = LocalLatinFont.current
    val label = listOf(sense.pos, if (isDefault) "默认" else "").filter(String::isNotEmpty).joinToString(" · ")
    FlowRow(horizontalArrangement = Arrangement.spacedBy(10.dp), itemVerticalAlignment = Alignment.CenterVertically) {
        Text(sense.english, color = colors.accent, fontFamily = latin, fontWeight = FontWeight.Medium,
            fontSize = (24 * scale).sp, lineHeight = (29 * scale).sp, letterSpacing = 0.sp)
        if (label.isNotEmpty()) Text(label, color = colors.subtle, fontSize = (11 * scale).sp, lineHeight = (15 * scale).sp)
    }
    if (sense.usage.isNotEmpty() || sense.collocation.isNotEmpty()) {
        Text(buildAnnotatedString {
            withStyle(SpanStyle(fontWeight = FontWeight.Medium)) { append(sense.usage) }
            if (sense.usage.isNotEmpty() && sense.collocation.isNotEmpty()) {
                withStyle(SpanStyle(color = colors.line)) { append(" │ ") }
            }
            withStyle(SpanStyle(color = colors.subtle, fontFamily = latin)) { append(sense.collocation) }
        }, color = colors.ink, fontSize = (12 * scale).sp, lineHeight = (17 * scale).sp, letterSpacing = 0.sp)
    }
    if (sense.exampleEn.isNotEmpty()) {
        val example = remember(sense, colors.accent) {
            val match = Regex("(?<![\\p{L}\\p{N}_])${Regex.escape(sense.english)}(?![\\p{L}\\p{N}_])", RegexOption.IGNORE_CASE)
                .find(sense.exampleEn)
            buildAnnotatedString {
                append(sense.exampleEn)
                if (match != null) addStyle(SpanStyle(color = colors.accent, fontWeight = FontWeight.SemiBold),
                    match.range.first, match.range.last + 1)
            }
        }
        Text(example, color = colors.ink, fontFamily = latin, fontSize = (14 * scale).sp, lineHeight = (18 * scale).sp, letterSpacing = 0.sp)
    }
    if (sense.exampleZh.isNotEmpty()) {
        Text(sense.exampleZh, color = colors.subtle, fontSize = (12 * scale).sp, lineHeight = (17 * scale).sp)
    }
}
