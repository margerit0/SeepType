// SPDX-License-Identifier: GPL-3.0-or-later
package org.studyime.android

import android.app.Activity
import android.content.Intent
import android.os.Bundle
import android.text.InputType
import android.view.inputmethod.EditorInfo
import android.view.accessibility.AccessibilityManager
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import java.io.File
import org.json.JSONObject

/** Synthetic real Android editors; excluded entirely from the release APK. */
class ProbeActivity : Activity() {
    private lateinit var primaryEditor: EditText

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        if (intent.hasExtra("snapshotToken")) {
            // Explicit host-test snapshot, so the crash regression can inspect
            // text without connecting an accessibility/UiAutomation service.
            File(filesDir, "unassisted-editor.json").writeText(JSONObject()
                .put("token", intent.getStringExtra("snapshotToken"))
                .put("text", primaryEditor.text.toString())
                .put("accessibilityEnabled", getSystemService(AccessibilityManager::class.java).isEnabled)
                .toString())
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val kind = intent.getStringExtra("field") ?: "text"
        org.studyime.android.settings.Preferences.get(this).update { preferences -> preferences.copy(
            theme = intent.getStringExtra("theme")?.takeIf { it in listOf("light", "dark", "system") } ?: preferences.theme,
            schema = intent.getStringExtra("schema")?.takeIf { it in listOf("study", "study_double_pinyin", "study_flypy") } ?: preferences.schema,
            showEnglish = if (intent.hasExtra("english")) intent.getBooleanExtra("english", true) else preferences.showEnglish,
        ) }
        val density = resources.displayMetrics.density
        val pad = (24 * density).toInt()
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(pad, pad, pad, pad)
            setBackgroundColor(0xfffbfcfa.toInt())
        }
        root.addView(TextView(this).apply { text = "拾词 · 原生输入验证"; textSize = 22f; setTextColor(0xff24352e.toInt()) })
        root.addView(TextView(this).apply {
            text = "Synthetic field: $kind"
            contentDescription = "probe_launch_${intent.getLongExtra("launchToken", 0)}"
            textSize = 12f
            setPadding(0, 16, 0, 24)
        })
        val actionLabel = TextView(this).apply { id = R.id.probe_action; text = "action:none"; textSize = 12f }
        val primary = EditText(this).apply {
            id = R.id.probe_text
            textSize = 18f
            hint = "在这里输入"
            inputType = when (kind) {
                "password" -> InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_WEB_PASSWORD
                "numberPassword" -> InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_VARIATION_PASSWORD
                "email" -> InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_EMAIL_ADDRESS
                "url" -> InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI
                "number" -> InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL or InputType.TYPE_NUMBER_FLAG_SIGNED
                "phone" -> InputType.TYPE_CLASS_PHONE
                "multiline" -> InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_MULTI_LINE
                else -> InputType.TYPE_CLASS_TEXT
            }
            imeOptions = when (kind) {
                "search" -> EditorInfo.IME_ACTION_SEARCH
                "send" -> EditorInfo.IME_ACTION_SEND
                "next" -> EditorInfo.IME_ACTION_NEXT
                "multiline" -> EditorInfo.IME_ACTION_NONE or EditorInfo.IME_FLAG_NO_ENTER_ACTION
                "private" -> EditorInfo.IME_ACTION_DONE or EditorInfo.IME_FLAG_NO_PERSONALIZED_LEARNING
                else -> EditorInfo.IME_ACTION_DONE
            }
            setOnEditorActionListener { _, action, _ -> actionLabel.text = "action:$action"; true }
            if (kind == "multiline") minLines = 3
        }
        val secondary = EditText(this).apply {
            id = R.id.probe_other
            hint = "第二个输入位置"
            textSize = 17f
            inputType = InputType.TYPE_CLASS_TEXT
            imeOptions = EditorInfo.IME_ACTION_DONE
        }
        primaryEditor = primary
        root.addView(primary, LinearLayout.LayoutParams(-1, -2))
        root.addView(secondary, LinearLayout.LayoutParams(-1, -2))
        root.addView(actionLabel)
        setContentView(root)
        primary.requestFocus()
    }
}
