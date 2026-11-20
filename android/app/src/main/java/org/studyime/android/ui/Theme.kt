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
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.font.FontVariation
import androidx.compose.ui.text.ExperimentalTextApi
import org.studyime.android.R
import org.studyime.android.settings.KeyboardSkin

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
val SoftPopLightColors = StudyColors(false, Color(0xFFFAFAFC), Color(0xFF636363), Color(0xFF737580),
    Color(0xFFE7E8EE), Color(0xFFF0EFF4), Color.White, Color.White,
    Color(0xFF237963), Color(0xFFD9EEE7), Color.White)
val SoftPopDarkColors = StudyColors(true, Color(0xFF23252E), Color(0xFFEEF0F4), Color(0xFFBEC0CB),
    Color(0xFF454754), Color(0xFF292B36), Color(0xFF3C3F4E), Color(0xFF454858),
    Color(0xFF8DE0C6), Color(0xFF364F47), Color(0xFF203D33))

@OptIn(ExperimentalTextApi::class)
val Quicksand = FontFamily(
    Font(R.font.quicksand_variable, FontWeight.Normal, variationSettings = FontVariation.Settings(FontVariation.weight(400))),
    Font(R.font.quicksand_variable, FontWeight.Medium, variationSettings = FontVariation.Settings(FontVariation.weight(500))),
    Font(R.font.quicksand_variable, FontWeight.SemiBold, variationSettings = FontVariation.Settings(FontVariation.weight(600))),
)
@OptIn(ExperimentalTextApi::class)
val NumberToggleFont = FontFamily(Font(R.font.fredoka_variable, FontWeight.Medium,
    variationSettings = FontVariation.Settings(FontVariation.weight(500), FontVariation.width(106f))))
val LocalLatinFont = staticCompositionLocalOf<FontFamily> { FontFamily.SansSerif }

@Composable
fun StudyTheme(mode: String = "system", skin: KeyboardSkin = KeyboardSkin.DEFAULT, content: @Composable () -> Unit) {
    val dark = when (mode) { "dark" -> true; "light" -> false; else -> isSystemInDarkTheme() }
    val colors = when (skin) {
        KeyboardSkin.DEFAULT -> if (dark) DarkColors else LightColors
        KeyboardSkin.SOFT_POP -> if (dark) SoftPopDarkColors else SoftPopLightColors
    }
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
    CompositionLocalProvider(LocalStudyColors provides colors,
        LocalLatinFont provides if (skin == KeyboardSkin.SOFT_POP) Quicksand else FontFamily.SansSerif) {
        MaterialTheme(colorScheme = scheme, content = content)
    }
}
