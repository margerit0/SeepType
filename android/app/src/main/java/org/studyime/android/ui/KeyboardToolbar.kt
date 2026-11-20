// SPDX-License-Identifier: GPL-3.0-or-later
package org.studyime.android.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.IconButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.scale
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.unit.dp

internal enum class ToolbarGlyph { Menu, Moon, Sun, Clipboard, GlossOff, GlossOn }

@Composable
internal fun ToolbarButton(glyph: ToolbarGlyph, description: String, enabled: Boolean = true, onClick: () -> Unit) {
    IconButton(onClick = onClick, enabled = enabled, modifier = Modifier.size(48.dp).semantics {
        contentDescription = description
    }) { ToolbarIcon(glyph, enabled) }
}

@Composable
internal fun GlossBubble(checked: Boolean, onCheckedChange: (Boolean) -> Unit) {
    Box(Modifier.size(48.dp).clip(RoundedCornerShape(10.dp))
        .toggleable(value = checked, role = Role.Switch, onValueChange = onCheckedChange)
        .semantics {
            contentDescription = "显示英文释义"
            stateDescription = if (checked) "开启" else "关闭"
        }, contentAlignment = Alignment.Center) {
        ToolbarIcon(if (checked) ToolbarGlyph.GlossOn else ToolbarGlyph.GlossOff)
    }
}

// The selected 32-unit toolbar study, rendered as vectors at a fixed 27 dp.
private object ToolbarArt {
    val menu = softPath("M11.5 7.5H23.1M5.1 16H26.9M7.7 24.5H19.3")
    val moon = softPath("M14.45 5.75C12 14.3 18.7 22.15 26.55 20.15C24.47 25.25 19.23 27.85 14.02 26.55C8.13 25.08 4.65 20.2 5.6 14.62C6.26 10.1 9.76 6.49 14.45 5.75Z")
    val rays = softPath("M16 4.25V6.62M16 25.38V27.75M4.25 16H6.62M25.38 16H27.75M7.69 7.69L9.37 9.37M22.63 22.63L24.31 24.31M7.69 24.31L9.37 22.63M22.63 9.37L24.31 7.69")
    val clipboard = softPath("M4.85 24.5V11.23C4.85 8.3 6.86 6.7 9.61 6.7H22.39C25.14 6.7 27.15 8.3 27.15 11.23V24.5")
    val coralDash = softPath("M11.75 15.35H20.25")
    val bubble = softPath("M26.27 15.7V10.83C26.27 7.5 24.18 5.65 20.97 5.65H10.57C7.31 5.65 5.1 7.68 5.1 10.98V17.72C5.1 20.88 7.03 22.89 9.72 23.08L9.65 26.06C9.65 26.49 9.93 26.65 10.32 26.39L15.03 23.14H17.2")
    val letter = softPath("M11.03 18.09L14.55 10.45C14.82 9.27 15.34 9.27 15.61 10.45L19.13 18.09")
    val crossbar = softPath("M12.22 15.51H17.94")
    val off = softPath("M21.05 22.81H26.69")
    val on = softPath("M20.42 21.86L23.03 24.3L27.74 18.99")
    val menuPen = roundStroke(2.65f)
    val outline = roundStroke(2.45f)
    val bubblePen = roundStroke(2.3f)
    val rayPen = roundStroke(2.05f)
    val letterPen = roundStroke(1.82f)
    val crossbarPen = roundStroke(1.69f)
    val offPen = roundStroke(2.27f)
    val onPen = roundStroke(2.42f)
}

@Composable
private fun ToolbarIcon(glyph: ToolbarGlyph, enabled: Boolean = true) {
    val colors = LocalStudyColors.current
    val alpha = if (enabled) 1f else .38f
    val ink = colors.ink.copy(alpha = alpha)
    val coral = (if (colors.dark) Color(0xFFFF909A) else Color(0xFFED6E76)).copy(alpha = alpha)
    Canvas(Modifier.size(27.dp)) {
        val unit = size.minDimension / 32f
        scale(unit, unit, pivot = Offset.Zero) {
            with(ToolbarArt) {
                when (glyph) {
                    ToolbarGlyph.Menu -> drawPath(menu, ink, style = menuPen)
                    ToolbarGlyph.Moon -> drawPath(moon, ink, style = outline)
                    ToolbarGlyph.Sun -> {
                        drawCircle(ink, radius = 5.1f, center = Offset(16f, 16f), style = bubblePen)
                        drawPath(rays, ink, style = rayPen)
                    }
                    ToolbarGlyph.Clipboard -> {
                        drawPath(clipboard, ink, style = outline)
                        drawPath(coralDash, coral, style = outline)
                    }
                    ToolbarGlyph.GlossOff, ToolbarGlyph.GlossOn -> {
                        drawPath(bubble, ink, style = bubblePen)
                        drawPath(letter, ink, style = letterPen)
                        drawPath(crossbar, ink, style = crossbarPen)
                        if (glyph == ToolbarGlyph.GlossOn) drawPath(on, colors.accent, style = onPen)
                        else drawPath(off, colors.subtle, style = offPen)
                    }
                }
            }
        }
    }
}
