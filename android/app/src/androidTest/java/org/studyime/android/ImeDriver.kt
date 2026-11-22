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
import androidx.test.uiautomator.Direction
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
    val privateDevice = InstrumentationRegistry.getArguments().getString("privateDevice") == "true"
    fun rebind() {
        val latin = InstrumentationRegistry.getArguments().getString("fallbackIme")
            ?: device.executeShellCommand("ime list -s").lineSequence().first { it.contains("inputmethod.latin") }.trim()
        require(latin.matches(Regex("[A-Za-z0-9_.$]+/[A-Za-z0-9_.$]+")))
        device.executeShellCommand("ime set $latin")
        device.executeShellCommand("ime enable $component")
        device.executeShellCommand("ime set $component")
    }
    fun editor(name: String = "probe_text"): UiObject2 = device.wait(Until.findObject(By.res(context.packageName, name)), 8000)
        ?: error("Missing synthetic editor: $name")
    fun key(name: String): UiObject2 = device.wait(Until.findObject(By.res("key_$name").enabled(true)), 15_000)
        ?: error("Missing enabled key: $name")
    // Composition changes may replace the accessibility node. Retry only the
    // coordinate lookup; never send an input gesture twice.
    fun keyBounds(name: String, enabledOnly: Boolean = true): android.graphics.Rect {
        val selector = By.res("key_$name").let { if (enabledOnly) it.enabled(true) else it }
        repeat(4) {
            try {
                val node = device.wait(Until.findObject(selector), 15_000) ?: error("Missing key: $name")
                return node.visibleBounds
            }
            catch (_: StaleObjectException) { device.waitForIdle(); SystemClock.sleep(30) }
        }
        error("Key changed before its hit region could be read: $name")
    }
    fun keyCenter(name: String) = keyBounds(name).let { android.graphics.Point(it.centerX(), it.centerY()) }
    fun tapKey(name: String) {
        val hit = keyCenter(name)
        device.click(hit.x, hit.y)
    }
    fun holdKey(name: String) {
        val hit = keyCenter(name)
        // A stationary 650 ms gesture exercises the real 480 ms IME handler.
        device.executeShellCommand("input swipe ${hit.x} ${hit.y} ${hit.x} ${hit.y} 650")
    }
    fun launch(kind: String = "text", theme: String = "light", configure: Boolean = true) {
        val token = SystemClock.elapsedRealtimeNanos()
        context.startActivity(Intent(context, ProbeActivity::class.java).putExtra("field", kind).putExtra("theme", theme)
            .putExtra("noPersonalization", privateDevice).putExtra("schema", "study").putExtra("english", true).putExtra("launchToken", token)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK))
        assertTrue("Fresh synthetic activity is ready", device.wait(Until.hasObject(By.desc("probe_launch_$token")), 8000))
        editor().click()
        key(if (kind in listOf("number", "phone", "numberPassword")) "1" else "g")
        device.waitForIdle()
        if (configure && imePackage != context.packageName && kind !in listOf("password", "numberPassword")) {
            // Preferences belong to the separate optimized app process. Set
            // its scheme through the same visible UI a user operates.
            openQuickSettings()
            chooseScheme("全拼")
            closeQuickSettings()
            device.waitForIdle()
        }
    }
    fun openQuickSettings() {
        if (device.hasObject(By.res("quick_settings"))) return
        val settings = device.findObject(By.desc("键盘设置"))
        if (settings != null) settings.click()
        else (device.findObject(By.desc("展开候选")) ?: device.findObject(By.desc("收起候选"))
            ?: error("Keyboard settings entry missing")).longClick()
        assertTrue("Inline settings opened", device.wait(Until.hasObject(By.res("quick_settings")), 5000))
    }
    fun closeQuickSettings() {
        device.findObject(By.desc("关闭快捷设置")).click()
        assertTrue("Inline settings closed", device.wait(Until.gone(By.res("quick_settings")), 5000))
    }
    fun chooseScheme(name: String) {
        val scroll = device.wait(Until.findObject(By.res("quick_settings_scroll")), 5000) ?: error("Settings scroll missing")
        repeat(3) { if ((device.findObject(By.text(name))?.visibleBounds?.height() ?: 0) < 40) scroll.scroll(Direction.DOWN, .75f) }
        (device.findObject(By.text(name)) ?: error("Scheme missing: $name")).click()
    }
    fun toggleEnglish() {
        openQuickSettings()
        device.findObject(By.res("quick_settings")).findObject(By.desc("显示英文释义")).click()
        closeQuickSettings()
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
        val points = text.toSet().associateWith { keyCenter(it.toString()) }
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
        val privateFile = File(context.filesDir, "$directory/$name.disabled")
        if (privateDevice) return privateFile
        device.waitForIdle()
        val file = File(context.filesDir, "$directory/$name.png").apply { parentFile!!.mkdirs() }
        assertTrue(device.takeScreenshot(file))
        device.dumpWindowHierarchy(File(file.parentFile, "$name.xml"))
        return file
    }
}
