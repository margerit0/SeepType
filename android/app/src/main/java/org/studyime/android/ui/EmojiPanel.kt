// SPDX-License-Identifier: GPL-3.0-or-later
package org.studyime.android.ui

import android.view.ContextThemeWrapper
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.key
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.emoji2.emojipicker.EmojiPickerView
import org.studyime.android.R

@Composable
internal fun EmojiPanel(
    statusHeight: Dp, pickerHeight: Dp, landscape: Boolean,
    onClose: () -> Unit, onPick: (String) -> Unit,
) {
    val colors = LocalStudyColors.current
    val columns = (LocalConfiguration.current.screenWidthDp / 43).coerceIn(7, 14)
    val theme = if (colors.dark) R.style.Theme_StudyIME_Emoji_Dark else R.style.Theme_StudyIME_Emoji_Light
    Column(Modifier.fillMaxWidth().testTag("emoji_panel")) {
        Row(Modifier.fillMaxWidth().height(statusHeight).padding(horizontal = 12.dp),
            verticalAlignment = Alignment.CenterVertically) {
            Text("表情", Modifier.weight(1f), color = colors.ink, fontSize = 14.sp, fontWeight = FontWeight.Medium)
            TextButton(onClick = onClose, modifier = Modifier.height(48.dp)) { Text("返回键盘") }
        }
        // Inflate only when open. Variant popups include AppCompat widgets.
        key(theme) {
            AndroidView(
                factory = { context ->
                    EmojiPickerView(ContextThemeWrapper(context, theme)).apply {
                        isFocusable = false
                        isFocusableInTouchMode = false
                    }
                },
                modifier = Modifier.fillMaxWidth().padding(horizontal = 4.dp, vertical = if (landscape) 3.dp else 0.dp)
                    .height(pickerHeight),
                onRelease = { it.setOnEmojiPickedListener(null) },
                update = { picker ->
                    if (picker.emojiGridColumns != columns) picker.emojiGridColumns = columns
                    picker.setOnEmojiPickedListener { onPick(it.emoji) }
                },
            )
        }
    }
}
