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
import androidx.test.uiautomator.StaleObjectException
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
        val imePackage = InstrumentationRegistry.getArguments().getString("imePackage") ?: context.packageName
        val device = UiDevice.getInstance(instrumentation)
        instrumentation.uiAutomation.serviceInfo = instrumentation.uiAutomation.serviceInfo.apply {
            flags = flags or AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS or
                AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS or AccessibilityServiceInfo.FLAG_INCLUDE_NOT_IMPORTANT_VIEWS
        }
        // Starting instrumentation force-stops the target package. Rebind the
        // IME after the runner has started, rather than before that force-stop.
        val privateDevice = InstrumentationRegistry.getArguments().getString("privateDevice") == "true"
        val systemPasswordIme = InstrumentationRegistry.getArguments().getString("systemPasswordIme")
        require(systemPasswordIme == null || (privateDevice &&
            systemPasswordIme.matches(Regex("[A-Za-z0-9_.$]+/[A-Za-z0-9_.$]+")) && !systemPasswordIme.startsWith(imePackage)))
        val otherIme = InstrumentationRegistry.getArguments().getString("fallbackIme")
            ?: device.executeShellCommand("ime list -s").lineSequence().first { it.contains("inputmethod.latin") }.trim()
        require(otherIme.matches(Regex("[A-Za-z0-9_.$]+/[A-Za-z0-9_.$]+")))
        val component = device.executeShellCommand("ime list -a -s").lineSequence().map(String::trim).first { it.startsWith("$imePackage/") }
        device.executeShellCommand("ime set $otherIme")
        device.executeShellCommand("ime enable $component")
        device.executeShellCommand("ime set $component")
        val checks = JSONArray()
        val report = JSONObject().put("fingerprint", Build.FINGERPRINT).put("scope", "Real Android EditText/InputConnection with native Compose IME; synthetic text only").put("imePackage", imePackage).put("checks", checks)
            .put("coverageComplete", systemPasswordIme == null)
        if (systemPasswordIme != null) report.put("blockedChecks", JSONArray(listOf(
            "Password keyboard exposes no Chinese candidates", "Password shows protected input state")))
            .put("blockedReason", "Synthetic password field is routed to the system keyboard: $systemPasswordIme")
        fun check(name: String, value: Boolean) { checks.put(JSONObject().put("name", name).put("passed", value)); assertTrue(name, value) }
        fun objectById(name: String): UiObject2 = device.wait(Until.findObject(By.res(context.packageName, name)), 15_000) ?: error("Missing editor $name")
        fun key(name: String) {
            var point: android.graphics.Point? = null
            repeat(4) {
                if (point == null) try {
                    point = (device.wait(Until.findObject(By.res("key_$name").enabled(true)), 15_000) ?: error("Missing keyboard key $name")).visibleCenter
                } catch (_: StaleObjectException) { device.waitForIdle() }
            }
            val hit = point ?: error("Key changed before its hit region could be read: $name")
            device.click(hit.x, hit.y)
        }
        fun launch(kind: String) {
            val token = android.os.SystemClock.elapsedRealtimeNanos()
            context.startActivity(Intent(context, ProbeActivity::class.java).putExtra("field", kind).putExtra("noPersonalization", privateDevice).putExtra("launchToken", token)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK))
            assertTrue(device.wait(Until.hasObject(By.desc("probe_launch_$token")), 8000))
            objectById("probe_text").click()
            assertTrue("IME accessibility root appears", device.wait(Until.hasObject(By.res("study_keyboard")), 30_000))
            device.waitForIdle()
        }
        fun type(text: String) { device.waitForIdle(); text.forEach { key(it.toString()) }; device.waitForIdle() }
        fun waitText(text: String): Boolean = device.wait(Until.hasObject(By.res(context.packageName, "probe_text").text(text)), 8000)
        try {
            launch("text")
            check("Details is disabled without a candidate", device.wait(Until.hasObject(By.res("key_details").enabled(false)), 8000))
            type("gongyuan")
            key("details")
            check("Current word details do not commit the composition", device.wait(Until.hasObject(By.res("definition_panel")), 8000) && waitText("gong yuan"))
            device.findObject(By.desc("关闭释义")).click()
            key("comma")
            check("Chinese comma finishes the current word then inserts punctuation", waitText("公园，"))
            objectById("probe_text").text = ""
            type("gongyuan")
            val park = device.wait(Until.findObject(By.descContains("公园")), 10_000) ?: error("Real park candidate missing")
            val bounds = park.visibleBounds
            // Tap the upper English row: it must still commit Chinese.
            device.click(bounds.centerX(), bounds.top + (bounds.height() * .25).toInt())
            check("Tapping English candidate row commits Chinese", waitText("公园"))
            listOf("space" to "ni", "enter" to "nihao").forEach { (keyName, spelling) ->
                objectById("probe_text").text = ""
                type(spelling)
                assertTrue("Chinese candidates are available before $keyName", device.wait(Until.hasObject(By.res("candidate_0")), 8000))
                key(keyName)
                check("$keyName commits only the typed spelling", waitText(spelling) && device.wait(Until.gone(By.res("candidate_0")), 8000))
            }
            objectById("probe_text").text = ""
            type("gongyuan")
            device.wait(Until.findObject(By.descContains("公园")), 8000)!!.longClick()
            val english = device.wait(Until.findObject(By.res("commit_english")), 8000) ?: error("Definition panel did not open")
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
                device.wait(Until.findObject(By.descContains("你好")), 8000)!!.click()
                key("enter")
                check("$kind dispatches the requested EditorInfo action", device.wait(Until.hasObject(By.res(context.packageName, "probe_action").text("action:$expected")), 8000))
            }
            launch("multiline")
            type("nihao")
            device.wait(Until.findObject(By.descContains("你好")), 8000)!!.click()
            key("enter")
            check("Multiline Enter inserts newline", waitText("你好\n"))

            if (systemPasswordIme == null) {
                launch("password")
                type("abc")
                check("Password keyboard exposes no Chinese candidates", !device.hasObject(By.res("candidate_0")))
                check("Password shows protected input state", device.hasObject(By.text("密码输入 · 不记录选词")))
            }
            launch("email")
            type("abc")
            check("Email defaults to literal English", waitText("abc"))
            key("page")
            key("1")
            key("comma")
            key("page")
            key("a")
            check("123 and ABC preserve the editor and the comma uses ASCII in English mode", waitText("abc1,a"))
            launch("number")
            type("123")
            check("Number editor opens numeric keyboard", waitText("123"))
            launch("phone")
            type("123")
            check("Phone editor accepts digits", waitText("123"))
            report.put("passed", true)
        } finally {
            if (!privateDevice && !report.optBoolean("passed")) {
                device.takeScreenshot(File(context.filesDir, "ime-failure.png"))
                device.dumpWindowHierarchy(File(context.filesDir, "ime-failure.xml"))
                report.put("windows", instrumentation.uiAutomation.windows.toString())
            }
            File(context.filesDir, "ime-interaction-report.json").writeText(report.toString(2))
        }
    }
}
