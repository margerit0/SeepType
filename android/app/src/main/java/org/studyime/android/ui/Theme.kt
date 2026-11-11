// SPDX-License-Identifier: GPL-3.0-or-later
package org.studyime.android.ui

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color

data class StudyColors(
    val dark: Boolean, val paper: Color, val ink: Color, val subtle: Color,
    val line: Color, val board: Color, val key: Color, val function: Color,
    val accent: Color, val tint: Color, val onAccent: Color,
)
val LightColors = StudyColors(false, Color(0xFFFBFCFA), Color(0xFF24352E), Color(0xFF53665B),
    Color(0xFFDCE5DE), Color(0xFFE8EEEA), Color.White, Color(0xFFD8E3DC),
    Color(0xFF2D6B53), Color(0xFFD6E7DC), Color.White)
val DarkColors = StudyColors(true, Color(0xFF18221E), Color(0xFFE4EEE8), Color(0xFFB0BEB4),
    Color(0xFF425448), Color(0xFF202D25), Color(0xFF35433A), Color(0xFF2B3D31),
    Color(0xFFACD5BB), Color(0xFF3B5141), Color(0xFF192D20))
val LocalStudyColors = staticCompositionLocalOf { LightColors }

@Composable
fun StudyTheme(mode: String = "system", content: @Composable () -> Unit) {
    val dark = when (mode) { "dark" -> true; "light" -> false; else -> isSystemInDarkTheme() }
    val colors = if (dark) DarkColors else LightColors
    val scheme = if (dark) darkColorScheme(
        primary = colors.accent, onPrimary = colors.onAccent, primaryContainer = colors.tint,
        secondary = colors.accent, onSecondary = colors.onAccent, secondaryContainer = colors.tint,
        onSecondaryContainer = colors.ink, surfaceVariant = colors.function, outlineVariant = colors.line,
        onPrimaryContainer = colors.ink, background = colors.paper, surface = colors.paper,
        onBackground = colors.ink, onSurface = colors.ink, onSurfaceVariant = colors.subtle, outline = colors.line,
    ) else lightColorScheme(
        primary = colors.accent, onPrimary = colors.onAccent, primaryContainer = colors.tint,
        secondary = colors.accent, onSecondary = colors.onAccent, secondaryContainer = colors.tint,
        onSecondaryContainer = colors.ink, surfaceVariant = colors.function, outlineVariant = colors.line,
        onPrimaryContainer = colors.ink, background = colors.paper, surface = colors.paper,
        onBackground = colors.ink, onSurface = colors.ink, onSurfaceVariant = colors.subtle, outline = colors.line,
    )
    CompositionLocalProvider(LocalStudyColors provides colors) { MaterialTheme(colorScheme = scheme, content = content) }
}
