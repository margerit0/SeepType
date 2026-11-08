// SPDX-License-Identifier: GPL-3.0-or-later
package org.studyime.android

import android.content.Intent
import android.accessibilityservice.AccessibilityServiceInfo
import android.os.Build
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.By
import androidx.test.uiautomator.UiDevice
import androidx.test.uiautomator.UiObject2
import androidx.test.uiautomator.Until
import java.io.File
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class ImeInteractionTest {
    @Test fun realInputConnectionAndEditorActions() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val context = instrumentation.targetContext
        val device = UiDevice.getInstance(instrumentation)
        instrumentation.uiAutomation.serviceInfo = instrumentation.uiAutomation.serviceInfo.apply {
            flags = flags or AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS or
                AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS or AccessibilityServiceInfo.FLAG_INCLUDE_NOT_IMPORTANT_VIEWS
        }
        // Starting instrumentation force-stops the target package. Rebind the
        // IME after the runner has started, rather than before that force-stop.
        val otherIme = device.executeShellCommand("ime list -s").lineSequence().first { it.contains("inputmethod.latin") }.trim()
        device.executeShellCommand("ime set $otherIme")
        device.executeShellCommand("ime enable ${context.packageName}/org.studyime.android.ime.StudyInputMethodService")
        device.executeShellCommand("ime set ${context.packageName}/org.studyime.android.ime.StudyInputMethodService")
        val checks = JSONArray()
        val report = JSONObject().put("fingerprint", Build.FINGERPRINT).put("scope", "Real Android EditText/InputConnection with native Compose IME; synthetic text only").put("checks", checks)
        fun check(name: String, value: Boolean) { checks.put(JSONObject().put("name", name).put("passed", value)); assertTrue(name, value) }
        fun objectById(name: String): UiObject2 = device.wait(Until.findObject(By.res(context.packageName, name)), 15_000) ?: error("Missing editor $name")
        fun key(name: String) {
            val button = device.wait(Until.findObject(By.res("key_$name")), 15_000) ?: error("Missing keyboard key $name")
            assertTrue("Key $name should be enabled", button.isEnabled)
            button.click()
        }
        fun launch(kind: String) {
            context.startActivity(Intent(context, ProbeActivity::class.java).putExtra("field", kind)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK))
            objectById("probe_text").click()
            assertTrue("IME accessibility root appears", device.wait(Until.hasObject(By.res("study_keyboard")), 30_000))
            device.waitForIdle()
        }
        fun type(text: String) { text.forEach { key(it.toString()) }; device.waitForIdle() }
        fun waitText(text: String): Boolean = device.wait(Until.hasObject(By.res(context.packageName, "probe_text").text(text)), 8000)
        try {
            launch("text")
            type("gongyuan")
            val park = device.wait(Until.findObject(By.descContains("公园")), 10_000) ?: error("Real park candidate missing")
            val bounds = park.visibleBounds
            // Tap the upper English row: it must still commit Chinese.
            device.click(bounds.centerX(), bounds.top + (bounds.height() * .25).toInt())
            check("Tapping English candidate row commits Chinese", waitText("公园"))
            objectById("probe_text").text = ""
            type("gongyuan")
            key("space")
            check("Ordinary space commits Chinese", waitText("公园"))
            objectById("probe_text").text = ""
            type("gongyuan")
            device.wait(Until.findObject(By.descContains("公园")), 8000)!!.longClick()
            val english = device.wait(Until.findObject(By.text("输入英文")), 8000) ?: error("Definition panel did not open")
            english.click()
            check("Explicit English action uses full engine value", waitText("park"))
            check("Long press does not also submit Chinese", objectById("probe_text").text == "park")
            objectById("probe_text").text = "A🙂"
            key("delete")
            check("Backspace deletes complete Unicode code point", waitText("A"))

            objectById("probe_text").text = ""
            type("gongyuan")
            objectById("probe_other").click()
            device.waitForIdle()
            check("Focus change does not write old composition into new editor", objectById("probe_other").text == "第二个输入位置" || objectById("probe_other").text.isEmpty())

            listOf("search" to 3, "send" to 4, "next" to 5, "text" to 6).forEach { (kind, expected) ->
                launch(kind)
                type("nihao")
                key("space")
                key("enter")
                check("$kind dispatches the requested EditorInfo action", device.wait(Until.hasObject(By.res(context.packageName, "probe_action").text("action:$expected")), 8000))
            }
            launch("multiline")
            type("nihao")
            key("space")
            key("enter")
            check("Multiline Enter inserts newline", waitText("你好\n"))

            launch("password")
            type("abc")
            check("Password keyboard exposes no Chinese candidates", !device.hasObject(By.res("candidate_0")))
            check("Password shows protected input state", device.hasObject(By.text("密码输入 · 不记录选词")))
            launch("email")
            type("abc")
            check("Email defaults to literal English", waitText("abc"))
            launch("number")
            type("123")
            check("Number editor opens numeric keyboard", waitText("123"))
            launch("phone")
            type("123")
            check("Phone editor accepts digits", waitText("123"))
            report.put("passed", true)
        } finally {
            if (!report.optBoolean("passed")) {
                device.takeScreenshot(File(context.filesDir, "ime-failure.png"))
                device.dumpWindowHierarchy(File(context.filesDir, "ime-failure.xml"))
                report.put("windows", instrumentation.uiAutomation.windows.toString())
            }
            File(context.filesDir, "ime-interaction-report.json").writeText(report.toString(2))
        }
    }
}
