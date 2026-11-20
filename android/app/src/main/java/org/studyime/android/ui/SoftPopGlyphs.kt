// SPDX-License-Identifier: GPL-3.0-or-later
package org.studyime.android.ui

import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.scale
import androidx.compose.ui.graphics.drawscope.translate
import androidx.compose.ui.graphics.vector.PathParser

internal fun softPath(data: String): Path = PathParser().parsePathString(data).toPath()
internal fun roundStroke(width: Float) = Stroke(width, cap = StrokeCap.Round, join = StrokeJoin.Round)

// Original keycap lettering. Each 32 × 32 tile has the same optical centre;
// narrow letters (I, J) do not drift to the right edge like end-aligned text.
private val Caps by lazy {
    mapOf(
        "A" to "M7 26L15 6.8Q16 4.5 17 6.8L25 26M10.4 19H21.6",
        "B" to "M10 6V26H17C25 26 25 16 17 16H10M10 6H17C24.5 6 24 16 17 16",
        "C" to "M24 8.4C18 3.1 7.3 6.4 7.3 16C7.3 25.2 17.1 29 24 23.5",
        "D" to "M8.5 6V26H14.2C28 26 28 6 14.2 6Z",
        "E" to "M21.8 6H10.5V26H22M11 15.7H20.5",
        "F" to "M10.5 26V6H22M11 15.8H20.8",
        "G" to "M24 8.5C18.4 3.1 6.2 6 6.2 16.2C6.2 28.8 25.8 30.2 25.8 16.5H17.5",
        "H" to "M8 6V26M24 6V26M8.6 16H23.4",
        "I" to "M16 6V26",
        "J" to "M20.6 6V20C20.6 26.4 15.2 27.6 11.3 24.9",
        "K" to "M9.2 6V26M23 6L10 18.9M15.5 13.6L23.3 26",
        "L" to "M10.2 6V26H22",
        "M" to "M4.8 26L7 6.9Q7.2 5 8.2 7L16 22L23.8 7Q24.8 5 25 6.9L27.2 26",
        "N" to "M8 26V6L24 26V6",
        "O" to "M25.9 16C25.9 2.5 6.1 2.5 6.1 16C6.1 29.5 25.9 29.5 25.9 16Z",
        "P" to "M9.5 26V6H16.7C25.5 6 25.5 17.2 16.7 17.2H10",
        "Q" to "M25.6 15.5C25.6 2.3 6.1 2.3 6.1 15.5C6.1 28.7 25.6 28.7 25.6 15.5ZM17.6 19.1L25.3 27.6",
        "R" to "M9.3 26V6H16.3C24.9 6 24.9 16.5 16.3 16.5H10M16.6 16.7L23.1 26",
        "S" to "M22.7 8.2C17.8 3.5 8.5 5.4 8.6 11.1C8.8 17.8 23.5 14.2 23.3 21.2C23.2 27.3 13.3 28.2 8.8 23.5",
        "T" to "M8 6H24M16 6.5V26",
        "U" to "M7.8 6V18.4C7.8 28.7 24.2 28.7 24.2 18.4V6",
        "V" to "M7.2 6L15.1 25Q16 27.2 16.9 25L24.8 6",
        "W" to "M3.5 6L7.4 25Q7.8 27.5 9 25L16 10.5L23 25Q24.2 27.5 24.6 25L28.5 6",
        "X" to "M8.4 6L23.6 26M23.6 6L8.4 26",
        "Y" to "M7.7 6L16 17L24.3 6M16 17V26",
        "Z" to "M8.2 6H23.6L8.2 26H23.8",
    ).mapValues { softPath(it.value) }
}

// Stencil breaks, round terminals and optical widths are part of the design:
// zero is an open circle; the other numerals are deliberately much narrower.
private val Marks by lazy {
    mapOf(
        "0" to "M6 23C.4 13.1 8 2.4 18.1 3.6Q21.9 4 24.5 6M28.2 10C34.4 22.4 20.9 33.8 9.7 26.9",
        "1" to "M12.4 13.3L18.7 3.8M18.9 13.9V28.1",
        "2" to "M7.2 12C6.8 6.6 11.8 2.3 18.4 3.9M22.4 7C26.3 14.6 19.1 17.1 14.3 19.1Q7.5 21.8 7.5 27.7M13.4 28H24",
        "3" to "M8 10.8Q8.4 1.8 18.6 4M22.3 7.1Q24.5 16.4 13.8 15.4M22.7 19C27.6 30.2 8.1 32.2 7.2 21.3",
        "4" to "M19.4 3.5L7.2 21.9H13M19.3 13.1V28M22.9 21.9H23.6",
        "5" to "M11.9 4L9.3 13.3Q14.5 12.7 18.2 14.2M18.5 4H20M22.5 18C27.4 27 15.8 32.1 8.4 25.2",
        "6" to "M18.8 3.7L10.2 17.5Q7.1 22.4 9.1 25.2M19.5 13.4C30.1 17.4 24.5 32.8 13.2 27.2",
        "7" to "M8 4H17.3M24 4L9 28",
        "8" to "M8.3 12.1C6.7 6.1 11.8 2.1 18.7 4M23 7.3C24.8 13.4 20.3 16.5 15.3 16C9.4 15.5 6.4 20.4 8.1 24.5M12.2 27.6C18.7 30.2 25.1 25.8 23.3 20.1",
        "9" to "M13.5 18.3C4.2 15.5 7 1.1 18.8 4M23 7.3Q25.5 12.7 21.8 18.1L15.1 28",
        "!" to "M19.1 4.3L14.7 19.8M13.6 26.7L13.3 27.4",
        "@" to "M17.8 28C4.8 28 1 13.1 9.2 6.3Q15 1.3 22.4 5.4M26.2 9.2Q30.9 19.1 23.5 22M18.6 10.9L17.8 20H14.5M14.2 12.2Q10.4 12 10.6 17",
        "#" to "M15.1 6.7L10 25.1M22 6.7L16.8 25.1M8 13.4H10M22.9 13.4H25M6.8 18.7H9M21.3 18.7H23.7",
        "¥" to "M6.4 5L16 14.5L25.6 5M16 19V27M7.8 16.9H10.4M21.6 16.9H24.2M7.8 22.5H10.4M21.6 22.5H24.2",
        "%" to "M20.6 4.4L11.6 27.6M4.5 10.1Q4.3 4 10.1 4.7M13.5 8.1Q13.6 14.2 8.3 13.5M18.8 24.1Q18.9 18 24.5 18.7M27.7 22.2Q27.6 28 22.1 27.4",
        "&" to "M9.7 11.2Q8 3.7 15.2 4.4M18.7 7.8C20.4 15.3 5.8 14.1 6.5 24M10.3 27.4Q15.9 29.1 19.7 23.8L24.6 18.5M17.2 18.8L26.2 27.4",
        "*" to "M16 12V17M11.6 14.7L16 16L20.4 14.7M13.4 19.7L16 16L18.6 19.7",
        "(" to "M18.4 3.7Q11.6 16 18.4 28.3", ")" to "M13.6 3.7Q20.4 16 13.6 28.3",
        "~" to "M8.6 16.9Q11.9 12 16 16Q20 20 23.4 15.8", "/" to "M20.5 4.6L11.5 27.4",
        "-" to "M11.3 16H20.7", "_" to "M8.8 24H23.2",
        ":" to "M16 9.2V9.5M16 23V23.3", ";" to "M16.5 9V9.3M16.7 22.7Q16.8 25 15 26.3",
        "?" to "M9.4 9Q11.8 1.9 19.8 5M23.4 8.9C25.2 15.1 16.2 15.7 16 21.6M15.4 27.3H15.7",
    ).mapValues { softPath(it.value) }
}

private val CapStroke = roundStroke(3.85f)
private val MarkStroke = roundStroke(3.45f)
private val FineStroke = roundStroke(2.7f)
private val DotStroke = roundStroke(4.35f)

// Position by the measured face, not the screen: split landscape keyboards and
// narrow windows use the same two anchors. Grow both layers for large type,
// stopping before the widest glyphs cross the cap edge or the other legend.
internal fun DrawScope.drawPair(letter: String, symbol: String, swapped: Boolean, textScale: Float,
                                ink: Color, mark: Color) {
    val unit = minOf(size.width / 106f, size.height / 150f) * textScale.coerceAtMost(1.62f)
    fun tile(name: String, cap: Boolean, upper: Boolean) {
        val factor = unit * when {
            cap -> if (upper) 1f else 1.48f
            upper -> .94f
            symbol[0].isDigit() -> 1.50f
            else -> 1.37f
        }
        val x = size.width * (if (upper) .66f else .345f)
        val y = size.height * (if (upper) .295f else .697f)
        translate(x - 16f * factor, y - 16f * factor) {
            scale(factor, factor, pivot = Offset.Zero) {
                val stroke = when {
                    cap -> CapStroke
                    name == "(" || name == ")" -> FineStroke
                    name == ":" || name == ";" -> DotStroke
                    else -> MarkStroke
                }
                drawPath(if (cap) Caps.getValue(name) else Marks.getValue(name), if (cap) ink else mark, style = stroke)
            }
        }
    }
    tile(letter, cap = true, upper = !swapped)
    tile(symbol, cap = false, upper = swapped)
}
