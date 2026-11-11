// SPDX-License-Identifier: GPL-3.0-or-later
package org.studyime.android

import android.accessibilityservice.AccessibilityServiceInfo
import android.content.Intent
import android.os.SystemClock
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.By
import androidx.test.uiautomator.Configurator
import androidx.test.uiautomator.UiDevice
import androidx.test.uiautomator.UiObject2
import androidx.test.uiautomator.StaleObjectException
import androidx.test.uiautomator.Until
import java.io.File
import org.junit.Assert.assertTrue

/** Only touches synthetic test editors and the explicitly chosen IME. */
class ImeDriver {
    val instrumentation = InstrumentationRegistry.getInstrumentation()
    val context = instrumentation.targetContext
    val device = UiDevice.getInstance(instrumentation)
    val imePackage = InstrumentationRegistry.getArguments().getString("imePackage") ?: context.packageName
    val component = device.executeShellCommand("ime list -a -s").lineSequence()
        .map(String::trim).first { it.startsWith("$imePackage/") }
    init {
        Configurator.getInstance().waitForIdleTimeout = 100
        instrumentation.uiAutomation.serviceInfo = instrumentation.uiAutomation.serviceInfo.apply {
            flags = flags or AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS or
                AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS
        }
        rebind()
    }
    fun rebind() {
        val latin = device.executeShellCommand("ime list -s").lineSequence().first { it.contains("inputmethod.latin") }.trim()
        device.executeShellCommand("ime set $latin")
        device.executeShellCommand("ime enable $component")
        device.executeShellCommand("ime set $component")
    }
    fun editor(name: String = "probe_text"): UiObject2 = device.wait(Until.findObject(By.res(context.packageName, name)), 8000)
        ?: error("Missing synthetic editor: $name")
    fun key(name: String): UiObject2 = device.wait(Until.findObject(By.res("key_$name").enabled(true)), 15_000)
        ?: error("Missing enabled key: $name")
    fun tapKey(name: String) {
        var point: android.graphics.Point? = null
        repeat(4) {
            if (point == null) try { point = key(name).visibleCenter }
            catch (_: StaleObjectException) { device.waitForIdle(); SystemClock.sleep(30) }
        }
        val hit = point ?: error("Key changed before its hit region could be read: $name")
        // Only node acquisition is retried; the actual input event is sent once.
        device.click(hit.x, hit.y)
    }
    fun launch(kind: String = "text", theme: String = "light") {
        val token = SystemClock.elapsedRealtimeNanos()
        context.startActivity(Intent(context, ProbeActivity::class.java).putExtra("field", kind).putExtra("theme", theme)
            .putExtra("schema", "study").putExtra("english", true).putExtra("launchToken", token)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK))
        assertTrue("Fresh synthetic activity is ready", device.wait(Until.hasObject(By.desc("probe_launch_$token")), 8000))
        editor().click()
        key(if (kind in listOf("number", "phone", "numberPassword")) "1" else "g")
        device.waitForIdle()
        if (imePackage != context.packageName && kind !in listOf("password", "numberPassword")) {
            // Preferences belong to the separate optimized app process. Set
            // its scheme through the same visible UI a user operates.
            device.findObject(By.text("拾词")).click()
            val heading = device.wait(Until.findObject(By.text("输入方式")), 5000) ?: error("Quick settings missing")
            heading.parent.parent.findObject(By.text("全拼")).click()
            device.findObject(By.desc("关闭快捷设置")).click()
            device.waitForIdle()
        }
    }
    fun type(text: String, delayMs: Long = 45) {
        if (delayMs > 0) {
            text.forEach {
                tapKey(it.toString())
                SystemClock.sleep(delayMs)
            }
            return
        }
        // For the separate rapid sequence, resolve hit regions after the
        // window layout settles and avoid per-letter automation waits.
        device.waitForIdle(500)
        val points = text.toSet().associateWith { key(it.toString()).visibleCenter }
        text.forEach {
            val point = points.getValue(it)
            device.click(point.x, point.y)
            if (delayMs > 0) SystemClock.sleep(delayMs)
        }
    }
    fun candidate(chinese: String): UiObject2 = device.wait(Until.findObject(By.descContains(chinese)), 8000)
        ?: error("Missing real Chinese candidate: $chinese")
    fun expectText(text: String) {
        assertTrue("Expected synthetic editor content: $text", device.wait(Until.hasObject(By.res(context.packageName, "probe_text").text(text)), 8000))
    }
    fun capture(directory: String, name: String): File {
        device.waitForIdle()
        val file = File(context.filesDir, "$directory/$name.png").apply { parentFile!!.mkdirs() }
        assertTrue(device.takeScreenshot(file))
        device.dumpWindowHierarchy(File(file.parentFile, "$name.xml"))
        return file
    }
}
