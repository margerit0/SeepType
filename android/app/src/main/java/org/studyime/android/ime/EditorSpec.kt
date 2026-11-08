// SPDX-License-Identifier: GPL-3.0-or-later
package org.studyime.android.ime

import android.text.InputType
import android.view.inputmethod.EditorInfo

data class EditorSpec(
    val sensitive: Boolean = false,
    val noPersonalization: Boolean = false,
    val asciiPreferred: Boolean = false,
    val numeric: Boolean = false,
    val phone: Boolean = false,
    val action: Int = EditorInfo.IME_ACTION_UNSPECIFIED,
    val actionLabel: String = "换行",
) {
    companion object {
        fun from(info: EditorInfo): EditorSpec {
            val category = info.inputType and InputType.TYPE_MASK_CLASS
            val variation = info.inputType and InputType.TYPE_MASK_VARIATION
            val password = (category == InputType.TYPE_CLASS_TEXT && variation in listOf(
                InputType.TYPE_TEXT_VARIATION_PASSWORD, InputType.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD,
                InputType.TYPE_TEXT_VARIATION_WEB_PASSWORD,
            )) || (category == InputType.TYPE_CLASS_NUMBER && variation == InputType.TYPE_NUMBER_VARIATION_PASSWORD)
            val numeric = category in listOf(InputType.TYPE_CLASS_NUMBER, InputType.TYPE_CLASS_PHONE, InputType.TYPE_CLASS_DATETIME)
            val ascii = password || numeric || info.imeOptions and EditorInfo.IME_FLAG_FORCE_ASCII != 0 ||
                (category == InputType.TYPE_CLASS_TEXT && variation in listOf(
                    InputType.TYPE_TEXT_VARIATION_EMAIL_ADDRESS, InputType.TYPE_TEXT_VARIATION_WEB_EMAIL_ADDRESS,
                    InputType.TYPE_TEXT_VARIATION_URI,
                ))
            val custom = info.actionLabel != null && info.actionId != 0
            val action = when {
                info.imeOptions and EditorInfo.IME_FLAG_NO_ENTER_ACTION != 0 -> EditorInfo.IME_ACTION_NONE
                custom -> info.actionId
                else -> info.imeOptions and EditorInfo.IME_MASK_ACTION
            }
            val label = if (custom) info.actionLabel.toString() else when (action) {
                EditorInfo.IME_ACTION_GO -> "前往"
                EditorInfo.IME_ACTION_SEARCH -> "搜索"
                EditorInfo.IME_ACTION_SEND -> "发送"
                EditorInfo.IME_ACTION_NEXT -> "下一项"
                EditorInfo.IME_ACTION_DONE -> "完成"
                EditorInfo.IME_ACTION_PREVIOUS -> "上一项"
                else -> "换行"
            }
            return EditorSpec(password, info.imeOptions and EditorInfo.IME_FLAG_NO_PERSONALIZED_LEARNING != 0,
                ascii, numeric, category == InputType.TYPE_CLASS_PHONE, action, label)
        }
    }
}
