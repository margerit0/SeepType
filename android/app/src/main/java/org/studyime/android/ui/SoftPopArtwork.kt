// SPDX-License-Identifier: GPL-3.0-or-later
package org.studyime.android.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.scale
import androidx.compose.ui.graphics.drawscope.translate
import androidx.compose.ui.graphics.vector.PathParser
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import org.studyime.android.settings.KeyboardPreferences

internal class SoftPopPalette(val dark: Boolean) {
    private fun color(light: Long, night: Long) = Color(if (dark) night else light)
    val mint = color(0xFF20C2A3, 0xFF239A82)
    val mintLetter = color(0xFF85DFC6, 0xFFBCF3E2)
    val mintDetail = color(0xFF0FAE94, 0xFF0B7D6E)
    val mintLine = color(0xD9E5FFF2, 0xB3CEFFF3)
    val lemon = listOf(color(0xFFFFDB74, 0xFFBA9E51), color(0xFFFBFFA8, 0xFFE0D589))
    val lemonInk = color(0xFFA08A29, 0xFF39321C)
    val lemonMark = color(0xFFD0B928, 0xFF5F521E)
    val violet = listOf(color(0xFF9186EE, 0xFF9C94E5), color(0xFF7265D0, 0xFF7B70BC), color(0xFF4E419F, 0xFF51458E))
    val violetLetter = color(0xFFDED8FF, 0xFFEEEAFF)
    val violetMark = color(0xFF473892, 0xFF332A70)
    val coral = color(0xFFE77B83, 0xFFF4A2AC)
    val yellow = color(0xFFE8D274, 0xFFF0DB8A)
    private val mintInk = color(0xFF48B89C, 0xFF86DCC4)
    private val mauve = color(0xFFA78FC0, 0xFFCBB4E8)
    private val violetInk = color(0xFF8D79D2, 0xFFB8A6ED)
    private val symbol = color(0xFF939997, 0xFFC2C6CF)
    fun ink(value: String) = when (value) {
        "1", "8" -> coral
        "2", "6" -> mintInk
        "3", "7", "0" -> mauve
        "4", "9" -> yellow
        "5" -> violetInk
        else -> symbol
    }
}

private val LightArtwork = SoftPopPalette(false)
private val DarkArtwork = SoftPopPalette(true)
internal fun softPopPalette(dark: Boolean) = if (dark) DarkArtwork else LightArtwork

// Paths match the independently drawn, reviewed SVG in the design directory.
// Cache parsed geometry once; candidate revisions never rebuild these paths.
private fun path(data: String): Path = PathParser().parsePathString(data).toPath()
private val Marks by lazy {
    mapOf(
        "0" to "M10 4C4 5 3 11 3 17C3 25 7 28 12 28C18 28 21 23 21 16C21 11 20 8 18 6",
        "1" to "M7 12L13 5M13 13L13 27",
        "2" to "M5 11C4 5 11 2 16 5C21 8 20 13 15 16L8 21Q5 23 5 27M10 27H20",
        "3" to "M5 7C8 3 17 3 19 8C21 12 17 15 12 15M8 16C17 13 22 19 18 25C15 30 6 28 4 24",
        "4" to "M13 4L4 21H12M16 12V28M17 21H21",
        "5" to "M19 4H12M8 5L6 16C12 12 20 16 20 22C20 28 10 30 5 26",
        "6" to "M14 4C11 9 5 17 5 22C5 27 10 29 15 27C21 24 20 18 16 16M12 15L8 17",
        "7" to "M4 5H15M20 5L7 28",
        "8" to "M7 13C2 8 7 3 13 4C19 5 21 9 16 14L7 19C1 24 7 29 14 27M18 24C22 19 15 16 11 15",
        "9" to "M15 5C8 1 3 8 5 14C7 19 13 18 17 14M19 7C21 14 14 23 10 28",
        "!" to "M14 5L10 20M9 27H9.1",
        "@" to "M16 11L14 20Q17 23 20 18C23 9 17 4 10 6C1 8 0 20 6 25Q10 28 15 25M15 11C9 7 5 17 9 20Q12 22 15 17",
        "#" to "M9 7L5 25M18 7L14 25M4 13H21M2 20H19",
        "¥" to "M4 6L12 15L20 6M12 15V28M5 18H19M5 23H19",
        "%" to "M18 5L6 27M9.3 10A3.3 4.3 0 1 1 2.7 10A3.3 4.3 0 1 1 9.3 10M21.3 22A3.3 4.3 0 1 1 14.7 22A3.3 4.3 0 1 1 21.3 22",
        "&" to "M16 8C14 1 6 5 8 11C10 17 17 24 21 27M9 14C-1 19 4 30 12 26L20 18",
        "*" to "M12 11V23M7 14L17 20M17 14L7 20",
        "(" to "M15 4C9 11 9 22 14 28",
        ")" to "M10 4C16 11 16 22 11 28",
        "~" to "M4 17C9 9 14 24 20 16",
        "/" to "M17 4L7 28",
        "-" to "M7 17H17",
        "_" to "M5 26H19",
        ":" to "M12 12H12.1M12 24H12.1",
        ";" to "M13 12H13.1M13 23Q13 27 10 28",
        "?" to "M5 9C6 2 19 2 19 10C19 15 12 16 11 21M11 28H11.1",
        "delete" to "M26 8H13Q10 8 8 11L4 16L8 21Q10 24 13 24H26M22 16H26",
        "enter" to "M26 7V14Q26 18 22 18H6M11 13L6 18L11 23",
        "settings" to "M9 5H17M4 12H20M6 19H14",
        "moon" to "M17 17A8 8 0 0 1 7 7A8 8 0 1 0 17 17Z",
        "sun" to "M16 12A4 4 0 1 1 8 12A4 4 0 1 1 16 12M12 2V4M12 20V22M2 12H4M20 12H22M5 5L6 6M18 18L19 19M5 19L6 18M18 6L19 5",
        "book" to "M12 6C8 3 4 4 3 5V18Q8 16 12 20Q16 16 21 18V5C17 4 15 4 12 6V20",
    ).mapValues { path(it.value) }
}

@Composable
internal fun SoftPopMark(name: String, color: Color, modifier: Modifier = Modifier) {
    val geometry = Marks.getValue(name)
    val width = when (name) { "delete", "enter" -> 32f; else -> 24f }
    val height = if (name in listOf("settings", "moon", "sun", "book")) 24f else 32f
    Canvas(modifier.clearAndSetSemantics { }) {
        val factor = minOf(size.width / width, size.height / height)
        translate((size.width - width * factor) / 2, (size.height - height * factor) / 2) {
            scale(factor, factor, pivot = Offset.Zero) {
                drawPath(geometry, color, style = Stroke(2.35f, cap = StrokeCap.Round, join = StrokeJoin.Round))
            }
        }
    }
}

private val ShiftCurve by lazy { path("M7 104C48 89 79 48 89 -5") }
private val ShiftLine by lazy { path("M27 105C56 82 91 40 101 3") }
private val ShiftStars by lazy { path("M53 9Q56 14 58 17L73 20L58 23Q56 26 53 30Q50 25 48 23L33 20L48 17Q51 13 53 9ZM77 72C78 79 79 80 86 82C79 84 78 85 77 92C76 85 75 84 68 82C75 80 76 79 77 72Z") }

@Composable
internal fun SoftPopKeyContent(key: KeySpec, prefs: KeyboardPreferences, faceHeight: Float) {
    val colors = LocalStudyColors.current
    val art = softPopPalette(colors.dark)
    val density = LocalDensity.current
    val configuration = LocalConfiguration.current
    val narrow = configuration.screenWidthDp < 360
    val landscape = configuration.screenWidthDp > configuration.screenHeightDp
    val faceWidth = ((configuration.screenWidthDp - 8) * (if (landscape) .66f else 1f) / 10f - 6f).coerceAtLeast(16f)
    val scale = prefs.textScale
    Box(Modifier.fillMaxSize().clearAndSetSemantics { }, contentAlignment = Alignment.Center) {
        when {
            key.letter != null && key.symbol != null -> {
                val desired = if (key.symbolLayer) (if (narrow) 20f else 22f) else 14f
                // Reserve vertical space for the other label, including on the
                // shorter landscape keys. Candidates keep the full font scale.
                val letterRoom = faceHeight - if (key.symbolLayer) 20f else 29f
                val letterSize = minOf(desired * scale, faceWidth / density.fontScale,
                    letterRoom.coerceAtLeast(14f) / (1.15f * density.fontScale))
                Text(key.letter, color = colors.ink, fontFamily = Quicksand, fontWeight = FontWeight.Medium,
                    fontSize = letterSize.sp, lineHeight = (letterSize * 1.15f).sp, maxLines = 1,
                    modifier = if (key.symbolLayer) Modifier.align(Alignment.BottomStart).padding(start = if (narrow) 2.dp else 5.dp, bottom = 2.dp)
                    else Modifier.align(Alignment.TopEnd).padding(end = if (narrow) 3.dp else 5.dp, top = 3.dp))
                SoftPopMark(key.symbol, art.ink(key.symbol), if (key.symbolLayer)
                    Modifier.align(Alignment.TopEnd).padding(top = 1.dp, end = 3.dp).size(13.dp, 16.dp)
                    else Modifier.align(Alignment.BottomStart).padding(start = if (narrow) 4.dp else 7.dp, bottom = 3.dp).size(17.dp, 22.dp))
            }
            key.id == "shift" -> {
                Canvas(Modifier.fillMaxSize()) {
                    scale(size.width / 100f, size.height / 100f, pivot = Offset.Zero) {
                        drawPath(ShiftCurve, art.mintDetail, style = Stroke(2.6f))
                        drawPath(ShiftLine, art.mintLine, style = Stroke(1.7f))
                        drawPath(ShiftStars, art.mintDetail)
                    }
                }
                val shiftSize = minOf(16 * scale, (faceWidth * key.weight - 9) / (1.35f * density.fontScale))
                Text(if (key.shifted) "AB" else "ab", fontFamily = Quicksand, fontWeight = FontWeight.Normal,
                    fontSize = shiftSize.sp, lineHeight = (shiftSize * 1.25f).sp,
                    color = if (key.shifted) Color(0xFFF2FFFB) else art.mintLetter,
                    modifier = Modifier.align(Alignment.BottomStart).padding(start = 7.dp, bottom = 7.dp))
            }
            key.id == "delete" || key.id == "enter" -> {
                val captionSize = minOf(12 * scale, (faceWidth * key.weight - 5) / (key.caption.length * .64f * density.fontScale))
                Text(key.caption, fontFamily = Quicksand, fontWeight = FontWeight.Medium, fontSize = captionSize.sp,
                    lineHeight = (captionSize * 1.25f).sp, maxLines = 1, color = if (key.id == "delete") art.lemonInk else art.violetLetter,
                    modifier = Modifier.align(Alignment.TopEnd).padding(top = 4.dp, end = 6.dp))
                if (key.id == "enter" && key.icon != null) {
                    Icon(key.icon, null, Modifier.align(Alignment.BottomStart).padding(start = 6.dp, bottom = 4.dp).size(22.dp), tint = art.violetMark)
                } else SoftPopMark(key.id, if (key.id == "delete") art.lemonMark else art.violetMark,
                    Modifier.align(Alignment.BottomStart).padding(start = 5.dp, bottom = 1.dp).size(27.dp))
            }
            key.id == "space" -> {
                Text(key.text, color = colors.subtle, fontFamily = LocalLatinFont.current, fontSize = (12 * scale).sp,
                    modifier = Modifier.padding(bottom = 7.dp), maxLines = 1)
                Box(Modifier.align(Alignment.BottomCenter).padding(bottom = 10.dp).size(34.dp, 2.dp).background(art.yellow, RoundedCornerShape(2.dp)))
            }
            key.id == "page" -> {
                val toggleSize = minOf((if (narrow) 17f else 19f) * scale,
                    faceWidth * key.weight / (2.05f * density.fontScale))
                Text(key.text, fontFamily = NumberToggleFont, fontWeight = FontWeight.Medium,
                    fontSize = toggleSize.sp, lineHeight = (toggleSize * 1.25f).sp,
                    letterSpacing = .5.sp, color = colors.ink, maxLines = 1)
            }
            key.id == "mode" -> {
                if ('/' in key.text) {
                    val modeScale = minOf(scale, faceWidth * key.weight / (34f * density.fontScale))
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(key.text.substringBefore('/'), fontSize = (18 * modeScale).sp, color = colors.ink)
                        Text("’", fontFamily = Quicksand, fontSize = (14 * modeScale).sp, color = colors.subtle)
                        Text(key.text.substringAfter('/'), fontSize = (12 * modeScale).sp, color = art.ink("5"))
                    }
                } else Text(key.text, fontSize = minOf(18 * scale, faceWidth * key.weight / density.fontScale).sp, color = colors.ink)
            }
            key.icon != null -> Icon(key.icon, null, Modifier.size(22.dp), tint = colors.ink)
            else -> Text(key.text, fontFamily = Quicksand, fontWeight = FontWeight.Medium,
                fontSize = ((if (key.function) 12f else 19f) * scale).sp, color = colors.ink,
                textAlign = TextAlign.Center, maxLines = 1)
        }
    }
}
