// SPDX-License-Identifier: GPL-3.0-or-later
package org.studyime.android.ui

import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Icon
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.draw.drawWithCache
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.scale
import androidx.compose.ui.graphics.drawscope.translate
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.em
import org.studyime.android.settings.KeyboardPreferences

private class SoftPopPalette(private val dark: Boolean) {
    private fun tone(day: Long, night: Long) = Color(if (dark) night else day)
    val mint = tone(0xFF22C6A1, 0xFF238F79)
    val mintLetter = tone(0xFF90E5C9, 0xFFC5F6E6)
    val mintDetail = tone(0xFF0DAF8F, 0xFF087761)
    val mintLine = tone(0xFFEAFFF4, 0xFFBEEDDC)
    val lemon = listOf(tone(0xFFFFD462, 0xFFB49A51), tone(0xFFFFE781, 0xFFCCB46B), tone(0xFFFAFFA6, 0xFFE0D589))
    val lemonInk = tone(0xFF917014, 0xFF3C3116)
    val lemonMark = tone(0xFFCFB20F, 0xFF655515)
    val lemonGlint = tone(0xFFFFF5AF, 0xFFFFECAB)
    val violet = listOf(tone(0xFF7D7CF4, 0xFF9894DD), tone(0xFF605FC9, 0xFF716DAF), tone(0xFF393982, 0xFF4A467F))
    val violetLetter = tone(0xFFE0DEFF, 0xFFF3F0FF)
    val violetMark = tone(0xFF424194, 0xFF373168)
    val violetGlint = tone(0xFF9391EA, 0xFFC1B8ED)
    val disc = tone(0xFFF6F6F8, 0xFF343744)
    val jade = tone(0xFF35B796, 0xFF8AE1C5)
    val bar = tone(0xFFF8DE80, 0xFFEDCF75)
    val modeInk = tone(0xFF545780, 0xFFBCBDE8)
    private val coral = tone(0xFFED686F, 0xFFF4A2AC)
    private val green = tone(0xFF36BE99, 0xFF86DCC4)
    private val lilac = tone(0xFFA28BC2, 0xFFCBB4E8)
    private val gold = tone(0xFFF6E285, 0xFFF0DB8A)
    private val iris = tone(0xFF7976DF, 0xFFB8AAF5)
    private val pencil = tone(0xFFABABAC, 0xFFBFC1CD)
    fun ink(symbol: String) = when (symbol) {
        "1", "8" -> coral; "2", "6" -> green; "3", "7", "0" -> lilac
        "4", "9" -> gold; "5" -> iris; else -> pencil
    }
}

private val LightArt = SoftPopPalette(false)
private val DarkArt = SoftPopPalette(true)

private object Trim {
    val sweep = softPath("M6 154C58 139 125 72 151 -7")
    val rim = softPath("M44 154C88 128 150 67 165 7Q166 -1 154 1")
    val stars = softPath("M88 13L97 24L122 28L97 32L88 44L79 32L53 28L79 24ZM129 107Q131 120 144 122Q131 125 129 138Q126 125 113 122Q126 120 129 107Z")
    val sweepPen = roundStroke(6f)
    val rimPen = roundStroke(3.1f)
    // A two-ink, open-ended family. The send arch is specific to Send; a
    // search, return or commit action must not masquerade as a send button.
    val actions = mapOf(
        "Del" to "M51 10H23Q18 10 15 15L10 23Q7 28 10 33L14 40Q17 45 24 45H51",
        "Send" to "M6 43L20 18Q24 10 32 10Q40 10 44 18L58 43",
        "Done" to "M10 27L25 41Q27 43 29 40L53 13",
        "Search" to "M42 24A15 15 0 1 1 12 24A15 15 0 1 1 42 24ZM38 36L53 49",
        "Next" to "M9 28H50M36 12L52 28L36 44",
        "Prev" to "M55 28H14M28 12L12 28L28 44",
        "Go" to "M9 28H50M36 12L52 28L36 44",
        "Enter" to "M53 10V22Q53 30 44 30H11M23 17L10 30L23 43",
    ).mapValues { softPath(it.value) }
    val actionPen = roundStroke(5.6f)
    val linkTop = softPath("M29 5Q24 1 20 5L7 18Q3 22 6.5 26L14 34")
    val linkBottom = softPath("M19 48Q24 52 28 48L41 35Q45 31 41.5 27L34 19")
    val linkPen = roundStroke(4.7f)
}

// Reference coordinates describe the visible faces, not the touch boxes:
// 106 × 150 letter, 164 × 150 action, 124 × 150 toggle, 306 × 150 space.
private fun DrawScope.unit(faceWidth: Float) = minOf(size.width / faceWidth, size.height / 150f)

@Composable
internal fun SoftPopKeyFace(key: KeySpec, prefs: KeyboardPreferences, rowHeight: Dp, enabled: Boolean, pressed: Boolean) {
    val colors = LocalStudyColors.current
    val art = if (colors.dark) DarkArt else LightArt
    val special = key.id == "delete" || key.id == "enter" || key.id == "shift"
    val wash = animateColorAsState(if (!pressed) Color.Transparent else if (special) Color.Black.copy(alpha = .12f) else colors.tint,
        tween(if (prefs.reduceMotion) 0 else 75), label = "softKeyPress")
    val side = (rowHeight * .038f).coerceIn(1.5.dp, 2.6.dp)
    val underlay = when {
        key.id == "space" -> Modifier.drawBehind {
            // Two hairline bridges join the white punctuation caps to the spacebar.
            drawLine(colors.key, Offset(-side.toPx() * 2, center.y), Offset(size.width + side.toPx() * 2, center.y),
                strokeWidth = (rowHeight.toPx() / 90f).coerceAtLeast(1f))
        }
        key.id == "delete" && !colors.dark -> Modifier.drawWithCache {
            val reach = size.maxDimension * .67f
            val glow = Brush.radialGradient(.6f to Color(0x42FFE385), 1f to Color(0x00FFE385), center = Offset(size.width / 2, size.height / 2), radius = reach)
            onDrawBehind { drawCircle(glow, reach) }
        }
        else -> Modifier
    }
    Box(Modifier.fillMaxSize().then(underlay).padding(horizontal = side, vertical = rowHeight * .076f)
        .clip(RoundedCornerShape(rowHeight * .18f)).drawWithCache {
            val gradient = when (key.id) {
                "delete" -> Brush.linearGradient(art.lemon, Offset.Zero, Offset(size.width, size.height * .35f))
                "enter" -> Brush.linearGradient(art.violet, Offset.Zero, Offset(size.width, size.height))
                else -> null
            }
            onDrawBehind {
                if (gradient != null) drawRect(gradient) else drawRect(if (key.id == "shift") art.mint else colors.key)
                if (wash.value.alpha > 0f) drawRect(wash.value)
            }
        }.clearAndSetSemantics { }, contentAlignment = Alignment.Center) {
        val textScale = prefs.textScale * LocalDensity.current.fontScale
        when {
            key.letter != null && key.symbol != null -> Canvas(Modifier.fillMaxSize()) {
                drawPair(key.letter, key.symbol, key.symbolLayer, textScale, colors.ink, art.ink(key.symbol))
            }
            key.id == "shift" -> {
                Canvas(Modifier.fillMaxSize()) {
                    scale(size.width / 164f, size.height / 150f, pivot = Offset.Zero) {
                        drawPath(Trim.sweep, art.mintDetail.copy(alpha = .72f), style = Trim.sweepPen)
                        drawPath(Trim.rim, art.mintLine, style = Trim.rimPen)
                        drawPath(Trim.stars, art.mintDetail)
                    }
                }
                FaceLabel(if (key.shifted) "AB" else "ab", ShiftSlot, textScale, Quicksand, FontWeight.Normal,
                    if (key.shifted) Color.White else art.mintLetter)
            }
            key.id == "delete" || key.id == "enter" -> {
                val del = key.id == "delete"
                Canvas(Modifier.fillMaxSize()) {
                    val u = unit(164f)
                    translate(size.width * .34f - 32f * u, size.height * .62f - 28f * u) {
                        scale(u, u, pivot = Offset.Zero) {
                            drawPath(Trim.actions[key.caption] ?: Trim.actions.getValue("Enter"), if (del) art.lemonMark else art.violetMark, style = Trim.actionPen)
                            if (del) drawLine(art.lemonGlint, Offset(51f, 27.5f), Offset(59f, 27.5f), 5.3f, StrokeCap.Round)
                            if (key.caption == "Send") drawLine(art.violetGlint, Offset(32f, 29f), Offset(32f, 41f), 5f, StrokeCap.Round)
                        }
                    }
                }
                FaceLabel(key.caption, CaptionSlot, textScale, Quicksand, FontWeight.SemiBold,
                    if (del) art.lemonInk else art.violetLetter)
            }
            key.id == "details" -> Canvas(Modifier.fillMaxSize()) {
                val u = unit(164f)
                drawCircle(art.disc, 53f * u)
                val ink = art.jade.copy(alpha = if (enabled) 1f else .64f)
                translate(center.x - 24f * u, center.y - 26.5f * u) {
                    scale(u, u, pivot = Offset.Zero) {
                        drawPath(Trim.linkTop, ink, style = Trim.linkPen)
                        drawPath(Trim.linkBottom, ink, style = Trim.linkPen)
                    }
                }
            }
            key.id == "space" -> Canvas(Modifier.fillMaxSize()) {
                val half = size.width * .15f
                drawLine(art.bar, Offset(center.x - half, center.y), Offset(center.x + half, center.y),
                    5.3f * unit(306f), StrokeCap.Round)
            }
            key.id == "comma" || key.id == "." -> Canvas(Modifier.fillMaxSize()) {
                val u = unit(106f) * textScale.coerceAtMost(1.5f)
                when (key.text) {
                    ",", "，" -> drawLine(colors.ink, center + Offset(1.2f, -4.5f) * u,
                        center + Offset(-1.8f, 5.4f) * u, 7f * u, StrokeCap.Round)
                    "。" -> drawCircle(colors.ink, 6.1f * u, style = Stroke(3.8f * u))
                    else -> drawCircle(colors.ink, 4.6f * u)
                }
            }
            key.id == "page" -> FaceLabel(key.text, ToggleSlot, textScale, NumberToggleFont, FontWeight.Medium, colors.ink)
            key.id == "mode" -> {
                val dual = '/' in key.text
                FaceLabel(key.text.substringBefore('/'), if (dual) ActiveModeSlot else ModeSlot,
                    textScale, FontFamily.SansSerif, FontWeight.SemiBold, colors.ink)
                if (dual) {
                    FaceLabel(key.text.substringAfter('/'), OtherModeSlot, textScale, FontFamily.SansSerif, FontWeight.SemiBold, art.modeInk)
                    Canvas(Modifier.fillMaxSize()) {
                        val u = unit(124f)
                        val at = Offset(size.width * .562f, size.height * .397f)
                        drawLine(colors.ink, at + Offset(1.1f, -3.8f) * u, at + Offset(-1.1f, 3.8f) * u,
                            3.9f * u, StrokeCap.Round)
                    }
                }
            }
            key.icon != null -> Icon(key.icon, null, Modifier.size(22.dp), tint = colors.ink)
            else -> FaceLabel(key.text, SymbolSlot, textScale, Quicksand, FontWeight.Medium, colors.ink)
        }
    }
}

// Anchor to the centre of the ink above the baseline, not the font's line box.
// Long actions (Search), narrow screens and large accessibility text are fitted
// against the actual face. Layout is cached; key presses only repaint the fill.
private data class LabelSlot(val faceWidth: Float, val emSize: Float, val x: Float, val y: Float,
                             val align: Float, val room: Float, val maxEmHeight: Float, val opticalMiddle: Float, val tracking: Float = 0f)
private val ShiftSlot = LabelSlot(164f, 45f, .15f, .63f, 0f, .67f, .46f, .32f)
private val CaptionSlot = LabelSlot(164f, 31f, .87f, .235f, 1f, .78f, .35f, .34f)
private val ToggleSlot = LabelSlot(124f, 47.5f, .5f, .5f, .5f, .88f, .56f, .35f, tracking = .085f)
private val ModeSlot = LabelSlot(124f, 44f, .5f, .5f, .5f, .88f, .55f, .36f)
private val ActiveModeSlot = ModeSlot.copy(x = .32f, room = .43f)
private val OtherModeSlot = ModeSlot.copy(emSize = 32f, x = .74f, y = .55f, room = .32f)
private val SymbolSlot = LabelSlot(106f, 46f, .5f, .5f, .5f, .87f, .58f, .34f)

@Composable
private fun FaceLabel(text: String, slot: LabelSlot, textScale: Float, family: FontFamily, weight: FontWeight, ink: Color) {
    val measurer = rememberTextMeasurer(cacheSize = 2)
    Spacer(Modifier.fillMaxSize().drawWithCache {
        val u = minOf(size.width / slot.faceWidth, size.height / 150f)
        val emPx = minOf(slot.emSize * u * textScale, size.height * slot.maxEmHeight)
        val layout = measurer.measure(text, TextStyle(color = ink, fontFamily = family, fontWeight = weight, fontSize = emPx.toSp(),
            letterSpacing = slot.tracking.em),
            softWrap = false, maxLines = 1)
        val fit = minOf(1f, size.width * slot.room / layout.size.width.coerceAtLeast(1))
        val origin = Offset(-layout.size.width * slot.align, emPx * slot.opticalMiddle - layout.firstBaseline)
        onDrawBehind {
            translate(size.width * slot.x, size.height * slot.y) {
                scale(fit, fit, pivot = Offset.Zero) { drawText(layout, topLeft = origin) }
            }
        }
    })
}
