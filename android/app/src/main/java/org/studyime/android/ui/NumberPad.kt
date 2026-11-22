// SPDX-License-Identifier: GPL-3.0-or-later
package org.studyime.android.ui

import android.view.HapticFeedbackConstants
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Keyboard
import androidx.compose.material.icons.outlined.MoreHoriz
import androidx.compose.material.icons.outlined.SpaceBar
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawWithCache
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.input.pointer.changedToUp
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.*
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import org.studyime.android.settings.KeyboardPreferences
import org.studyime.android.settings.KeyboardSkin

private const val SIDE_WEIGHT = .72f
private val PadRows = listOf("123", "456", "789", ",0.")

internal enum class PadOperator(val label: String, val output: String, val spoken: String) {
    PLUS("+", "+", "加号"), MINUS("−", "-", "减号"), TIMES("×", "×", "乘号"),
    DIVIDE("÷", "÷", "除号"), PERCENT("%", "%", "百分号");

    companion object {
        fun at(x: Float, y: Float, width: Int, height: Int): PadOperator? {
            if (!(x >= 0 && x < width && y >= 0 && y < height)) return null
            return entries[(y / height * entries.size).toInt().coerceAtMost(entries.lastIndex)]
        }
    }
}

@Composable
internal fun NumberPad(height: Dp, prefs: KeyboardPreferences, enabled: Boolean, asciiMode: Boolean, composing: Boolean,
                       enter: KeySpec, delete: KeySpec, compactLabels: Boolean, modifier: Modifier,
                       onKey: (String, String) -> Unit,
                       onLongKey: (String) -> Unit, onSwitchIme: () -> Unit) {
    val compact = compactLabels && prefs.skin != KeyboardSkin.SOFT_POP
    Row(modifier.testTag("number_pad")) {
        Column(Modifier.weight(SIDE_WEIGHT)) {
            OperatorRail(height, prefs, enabled) { op -> onKey(op.output, op.output) }
            Row {
                KeyCell(KeySpec("page", "ABC", function = true,
                    icon = Icons.Outlined.Keyboard.takeIf { compact }, spoken = "字母键盘"),
                    height, prefs, enabled, onKey, onLongKey,
                    specialLong = { onKey("symbols", "") }, specialLongLabel = "更多符号")
            }
        }
        Column(Modifier.weight(3f + SIDE_WEIGHT)) {
            PadRows.forEachIndexed { row, digits ->
                Row(Modifier.fillMaxWidth()) {
                    digits.forEach { char ->
                        val key = when (char) {
                            ',' -> KeySpec("comma", ",", spoken = "逗号")
                            '.' -> KeySpec(".", ".", spoken = "小数点")
                            else -> KeySpec(char.toString(), char.toString())
                        }
                        KeyCell(key, height, prefs, enabled, onKey, onLongKey)
                    }
                    val action = when (row) {
                        0 -> delete.copy(weight = SIDE_WEIGHT)
                        1 -> KeySpec("symbols", "#+=", SIDE_WEIGHT, true,
                            icon = Icons.Outlined.MoreHoriz.takeIf { compact }, spoken = "更多符号")
                        2 -> KeySpec("space", if (asciiMode) "space" else "空格", SIDE_WEIGHT,
                            icon = Icons.Outlined.SpaceBar.takeIf { compact }, spoken = if (composing) "空格，输入原始拼写" else "空格")
                        else -> enter.copy(weight = SIDE_WEIGHT)
                    }
                    KeyCell(action, height, prefs, enabled, onKey, onLongKey,
                        specialLong = if (action.id == "space") onSwitchIme else null)
                }
            }
        }
    }
}

@Composable
private fun OperatorRail(rowHeight: Dp, prefs: KeyboardPreferences, enabled: Boolean, onPick: (PadOperator) -> Unit) {
    val colors = LocalStudyColors.current
    val soft = prefs.skin == KeyboardSkin.SOFT_POP
    val cap = if (soft) softPopKeyCap(rowHeight) else DefaultKeyCap
    // KeyCell rounds each row to physical pixels. Round before multiplying so
    // the ABC key stays level with the bottom row at fractional densities.
    val railHeight = with(LocalDensity.current) { (rowHeight.roundToPx() * 3).toDp() }
    val cellHeight = railHeight / PadOperator.entries.size
    val fontSize = with(LocalDensity.current) { minOf((19f * prefs.textScale).sp.toPx(), (cellHeight * .72f).toPx()).toSp() }
    val view = LocalView.current
    val commit by rememberUpdatedState { op: PadOperator ->
        if (prefs.haptics) view.performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP)
        onPick(op)
    }
    var highlighted by remember { mutableStateOf<PadOperator?>(null) }
    Box(Modifier.fillMaxWidth().height(railHeight).testTag("operator_rail")
        .pointerInput(enabled, prefs.skin) {
            if (!enabled) return@pointerInput
            // One pointer owns the whole strip. Crossing a divider only previews;
            // leaving the strip, a second pointer inside it, or disposal cancels the gesture.
            awaitEachGesture {
                val down = awaitFirstDown()
                if (currentEvent.changes.size != 1) return@awaitEachGesture
                val bounds = size
                val first = PadOperator.at(down.position.x, down.position.y, bounds.width, bounds.height) ?: return@awaitEachGesture
                down.consume()
                highlighted = first
                try {
                    while (true) {
                        val event = awaitPointerEvent()
                        if (bounds != size || event.changes.size != 1) break
                        val change = event.changes.single()
                        if (change.id != down.id || change.isConsumed) break
                        val op = PadOperator.at(change.position.x, change.position.y, bounds.width, bounds.height) ?: break
                        val released = change.changedToUp()
                        change.consume()
                        highlighted = op
                        if (released) {
                            commit(op)
                            break
                        }
                    }
                } finally {
                    highlighted = null
                }
            }
        }) {
        // Inset only the painted face, like a regular key. Both skins keep the
        // same touch targets and accessibility bounds, including the five rows.
        val surface = Modifier.matchParentSize()
        Box(if (soft) cap.inset(surface).background(colors.key, RoundedCornerShape(cap.radius))
            else cap.defaultFace(surface, pressed = highlighted != null) { colors.function })
        Column(Modifier.matchParentSize()) {
            PadOperator.entries.forEachIndexed { i, op ->
                Box(Modifier.fillMaxWidth().weight(1f).testTag("key_${op.output}").semantics {
                    contentDescription = op.spoken
                    role = Role.Button
                    if (!enabled) disabled()
                    onClick { if (enabled) { commit(op); true } else false }
                }.drawWithCache {
                    val side = (cap.side + 2.dp).toPx()
                    val top = if (i == 0) (cap.vertical + 1.dp).toPx() else 1.dp.toPx()
                    val bottom = if (i == PadOperator.entries.lastIndex) (cap.vertical + 1.dp).toPx() else 1.dp.toPx()
                    val origin = Offset(side, top)
                    val face = Size((size.width - 2 * side).coerceAtLeast(0f), (size.height - top - bottom).coerceAtLeast(0f))
                    val corner = CornerRadius(cap.radius.toPx())
                    // A slide only repaints existing cells; it never moves labels or adds/removes layout nodes.
                    onDrawBehind {
                        if (i > 0) drawLine(colors.line, Offset(size.width * .27f, 0f), Offset(size.width * .73f, 0f), .8.dp.toPx())
                        if (highlighted == op) drawRoundRect(colors.tint, origin, face, corner)
                    }
                }, contentAlignment = Alignment.Center) {
                    Text(op.label, color = if (!enabled) colors.subtle.copy(alpha = .45f) else colors.ink,
                        fontSize = fontSize, lineHeight = fontSize, fontFamily = if (soft) Quicksand else FontFamily.Monospace,
                        fontWeight = if (soft) FontWeight.Medium else FontWeight.Normal, maxLines = 1,
                        modifier = Modifier.clearAndSetSemantics { })
                }
            }
        }
    }
}
