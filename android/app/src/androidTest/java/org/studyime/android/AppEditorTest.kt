// SPDX-License-Identifier: GPL-3.0-or-later
package org.studyime.android

import android.content.Intent
import android.net.Uri
import android.os.SystemClock
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.uiautomator.By
import androidx.test.uiautomator.Until
import java.io.File
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class AppEditorTest {
    @Test fun browserFormAndIndependentMessagingDraft() {
        val d = ImeDriver()
        val ui = d.device
        val checks = JSONArray()
        val report = JSONObject().put("scope", "Installed AOSP WebView browser and Messaging draft; synthetic local text; no messages sent")
            .put("imePackage", d.imePackage).put("checks", checks)
        fun check(name: String, passed: Boolean) { checks.put(JSONObject().put("name", name).put("passed", passed)); assertTrue(name, passed) }
        try {
            d.launch()
            val runToken = SystemClock.elapsedRealtimeNanos()
            val html = """<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head>
                <body style="font-family:sans-serif;background:#fbfcfa;color:#24352e;padding:16px">
                <h2>拾词 · 浏览器输入验证</h2><p>本页为离线合成测试内容 · $runToken</p>
                <textarea aria-label="study_browser_editor" placeholder="Browser test editor" style="font-size:20px;width:95%;height:150px"></textarea>
                <input aria-label="study_browser_search" type="search" placeholder="Local search field" style="font-size:20px;width:95%">
                </body></html>""".trimIndent()
            d.context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("data:text/html;charset=utf-8," + Uri.encode(html)))
                .setClassName("org.chromium.webview_shell", "org.chromium.webview_shell.WebViewBrowserActivity")
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK))
            // A previous invocation can leave this browser alive with edited
            // form state. Wait for this run's page rather than its shared title.
            assertTrue("Fresh local browser form loaded", ui.wait(Until.hasObject(By.text("本页为离线合成测试内容 · $runToken")), 15_000))
            val web = ui.findObject(By.clazz("android.webkit.WebView")) ?: error("Browser WebView missing")
            val browserField = web.findObjects(By.clazz("android.widget.EditText")).firstOrNull() ?: error("Browser form field missing")
            browserField.click()
            d.key("g")
            d.type("gongyuan")
            d.candidate("公园").click()
            check("Real browser textarea accepts Chinese commit", ui.wait(Until.hasObject(By.text("公园")), 8000))
            d.type("nihao")
            d.candidate("你好").longClick()
            ui.wait(Until.findObject(By.text("输入英文")), 5000)!!.click()
            check("Real browser textarea accepts explicit English after Chinese", ui.wait(Until.hasObject(By.text("公园hello")), 8000))
            d.tapKey("enter")
            d.type("nihao")
            d.tapKey("space")
            check("Browser multiline editing retains the newline", ui.wait(Until.hasObject(By.text("公园hello\n你好")), 8000))
            d.capture("scenarios", "external-browser")

            // NANPA's reserved fictional range opens the compose editor; an
            // empty recipient opens only the contact picker. Never tap Send.
            d.context.startActivity(Intent(Intent.ACTION_SENDTO, Uri.parse("smsto:2025550123"))
                .setPackage("com.android.messaging").putExtra("sms_body", "")
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
            val draft = ui.wait(Until.findObject(By.res("com.android.messaging", "compose_message_text")), 10_000)
                ?: error("Messaging draft editor missing")
            draft.click()
            d.key("g")
            d.type("gongyuan")
            d.candidate("公园").click()
            check("Independent Messaging draft accepts Chinese without sending", ui.wait(Until.hasObject(By.res("com.android.messaging", "compose_message_text").text("公园")), 8000))
            d.capture("scenarios", "external-messaging-draft")
            ui.findObject(By.res("com.android.messaging", "compose_message_text")).text = ""
            for (name in listOf("org.chromium.webview_shell", "com.android.webview", "com.android.messaging")) {
                val info = ui.executeShellCommand("dumpsys package $name")
                report.put(name, JSONArray(info.lineSequence().filter { it.trim().startsWith("versionName=") || it.trim().startsWith("versionCode=") }.map(String::trim).toList()))
            }
            report.put("passed", true)
        } finally {
            if (!report.optBoolean("passed")) d.capture("scenarios", "external-failure")
            File(d.context.filesDir, "app-editor-report.json").writeText(report.toString(2))
        }
    }
}
