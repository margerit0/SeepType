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
import android.widget.ScrollView
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
        if (intent.getBooleanExtra("nativeVerification", false)) {
            window.addFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
            setContentView(TextView(this).apply { text = "拾词 · 正在验证合成词库"; textSize = 22f })
            return
        }
        val kind = intent.getStringExtra("field") ?: "text"
        val manual = intent.getBooleanExtra("manual", false)
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
        root.addView(TextView(this).apply {
            text = if (manual) "拾词 · 交互体验" else "拾词 · 原生输入验证"
            textSize = 22f
            setTextColor(0xff24352e.toInt())
        })
        root.addView(TextView(this).apply {
            text = if (manual) when (kind) {
                "password", "numberPassword" -> "密码输入 · 请用虚构内容体验"
                "number" -> "数字输入 · 小数、正负号与删除"
                "phone" -> "电话号码 · 请用虚构号码体验"
                "email" -> "邮箱输入 · 字母、@ 与标点"
                "url" -> "网址输入 · 字母、斜杠与标点"
                "multiline" -> "多行文本 · 试打几句，再换行"
                "search" -> "搜索 · 点右下角查看收到的动作"
                "send" -> "发送动作 · 只记录动作，不发送消息"
                "next" -> "切换输入框 · 在两个位置继续输入"
                "private" -> "暂停个性化 · 此处不学习新的选词习惯"
                else -> "自由输入 · 试试 gongyuan，长按候选看看释义"
            } else "Synthetic field: $kind"
            contentDescription = "probe_launch_${intent.getLongExtra("launchToken", 0)}"
            textSize = 12f
            if (manual) setTextColor(0xff53665b.toInt())
            setPadding(0, 16, 0, 24)
        })
        val actionLabel = TextView(this).apply {
            id = R.id.probe_action
            text = if (manual) "测试内容仅用于本次体验。" else "action:none"
            textSize = 12f
            if (manual) setTextColor(0xff53665b.toInt())
        }
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
            setOnEditorActionListener { _, action, _ ->
                actionLabel.text = if (manual) "收到动作：" + when (action) {
                    EditorInfo.IME_ACTION_SEARCH -> "搜索"
                    EditorInfo.IME_ACTION_SEND -> "发送（未发送消息）"
                    EditorInfo.IME_ACTION_NEXT -> "下一个输入位置"
                    else -> "完成"
                } else "action:$action"
                if (manual && action == EditorInfo.IME_ACTION_NEXT) root.findViewById<EditText>(R.id.probe_other)?.requestFocus()
                true
            }
            if (kind == "multiline") minLines = 3
        }
        val secondary = EditText(this).apply {
            id = R.id.probe_other
            hint = "第二个输入位置"
            textSize = 17f
            inputType = InputType.TYPE_CLASS_TEXT
            imeOptions = EditorInfo.IME_ACTION_DONE
        }
        if (intent.getBooleanExtra("noPersonalization", false)) {
            primary.imeOptions = primary.imeOptions or EditorInfo.IME_FLAG_NO_PERSONALIZED_LEARNING
            secondary.imeOptions = secondary.imeOptions or EditorInfo.IME_FLAG_NO_PERSONALIZED_LEARNING
        }
        primaryEditor = primary
        root.addView(primary, LinearLayout.LayoutParams(-1, -2))
        root.addView(secondary, LinearLayout.LayoutParams(-1, -2))
        root.addView(actionLabel)
        // With a large font and the IME open in landscape, the labels alone
        // can fill the viewport. Keep the editor measurable and focusable.
        if (manual || resources.configuration.orientation == android.content.res.Configuration.ORIENTATION_LANDSCAPE)
            setContentView(ScrollView(this).apply { isFillViewport = true; addView(root) })
        else setContentView(root)
        primary.requestFocus()
    }
}
