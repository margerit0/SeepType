// SPDX-License-Identifier: GPL-3.0-or-later
package org.studyime.android

import android.content.Intent
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Color
import android.graphics.Rect
import android.os.SystemClock
import android.view.MotionEvent
import android.view.inputmethod.InputMethodManager
import android.widget.EditText
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.runner.lifecycle.ActivityLifecycleMonitorRegistry
import androidx.test.runner.lifecycle.Stage
import androidx.test.uiautomator.By
import androidx.test.uiautomator.Until
import java.io.File
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import kotlin.math.abs

/** Real InputConnection, persisted settings and APK-rendered artwork. No mock candidates. */
@RunWith(AndroidJUnit4::class)
class SkinSwitchTest {
    @Test fun skinsPreserveInputAndRenderAtNativeSizes() {
        val d = ImeDriver()
        val ui = d.device
        val checks = JSONArray()
        val captures = JSONArray()
        val report = JSONObject().put("imePackage", d.imePackage).put("checks", checks).put("captures", captures)
            .put("scope", "Native skin switching, paired key input, persistence and screenshots on a development emulator")
        val alphabet = "qwertyuiopasdfghjklzxcvbnm"
        val symbols = "1234567890!@#¥%&*()~/-_:;?"
        val bottomRow = listOf("details", "page", "comma", "space", ".", "mode", "enter")
        val allKeys = alphabet.map(Char::toString) + listOf("shift", "delete") + bottomRow
        fun boundsOf(id: String) = d.keyBounds(id, enabledOnly = false)
        val originalFont = ui.executeShellCommand("settings get system font_scale").trim()
        val originalNight = ui.executeShellCommand("cmd uimode night").substringAfter(":").trim()
        var originalSkin = "default"
        var originalTheme = "system"
        var originalEnglish = true
        fun check(name: String, value: Boolean) { checks.put(JSONObject().put("name", name).put("passed", value)); assertTrue(name, value) }
        fun shot(name: String): File {
            if (name.endsWith("symbols")) d.key("1")
            // Accessibility can settle before the release frame / key tint.
            // Capture the destination page after its actual nodes appear.
            SystemClock.sleep(200)
            captures.put("$name.png")
            return d.capture("skins", name)
        }
        fun selected(tag: String) = ui.findObject(By.res(tag))?.let { it.isChecked || it.isSelected } == true
        fun englishToggle(): androidx.test.uiautomator.UiObject2 {
            var node = ui.findObject(By.res("quick_settings")).findObject(By.desc("显示英文释义"))
            while (!node.isCheckable) node = node.parent ?: error("English toggle has no checkable parent")
            return node
        }
        fun choose(skin: String, theme: String? = null) {
            d.openQuickSettings()
            ui.findObject(By.res("skin_$skin")).click()
            if (theme != null) ui.findObject(By.res("theme_$theme")).click()
            check("Selected $skin / ${theme ?: "unchanged appearance"}", selected("skin_$skin") && (theme == null || selected("theme_$theme")))
            d.closeQuickSettings()
        }
        fun clear() { d.editor().text = ""; ui.waitForIdle() }
        fun pixels(name: String, expected: Int) {
            val bounds = d.keyBounds("q")
            val bitmap = BitmapFactory.decodeFile(shot(name).absolutePath)
            val observed = bitmap.getPixel(bounds.left + 1, bounds.top + 1)
            bitmap.recycle()
            check("$name renders the selected native background", observed == expected)
        }
        try {
            ui.setOrientationNatural()
            ui.executeShellCommand("wm density 320")
            ui.executeShellCommand("wm size 780x1688")
            ui.executeShellCommand("settings put system font_scale 1.0")
            d.launch("send")
            d.openQuickSettings()
            originalSkin = if (selected("skin_soft-pop")) "soft-pop" else "default"
            originalTheme = listOf("system", "light", "dark").first { selected("theme_$it") }
            originalEnglish = englishToggle().isChecked
            if (!originalEnglish) englishToggle().click()
            d.closeQuickSettings()

            choose("default", "light")
            val defaultBounds = allKeys.associateWith(::boundsOf)
            choose("soft-pop")
            check("Seven bottom keys follow the reference order", bottomRow.map(::boundsOf).zipWithNext().all { (l, r) -> l.right <= r.left && l.top == r.top })
            check("All ${allKeys.size} key bounds are identical across skins", allKeys.all { defaultBounds[it] == boundsOf(it) })
            val idleBounds = d.keyBounds("q")
            val idle = BitmapFactory.decodeFile(shot("soft-pop-idle").absolutePath)
            try {
                val w = boundsOf("w")
                check("Graphite letter sits above and right of its mint stencil digit",
                    hasInk(idle, w, .52f, .16f, .89f, .46f, 0xff636363.toInt()) &&
                    hasInk(idle, w, .19f, .53f, .62f, .86f, 0xff36be99.toInt()))
                check("Space has a centred gold rule", hasInk(idle, boundsOf("space"),
                    .43f, .47f, .57f, .53f, 0xfff8de80.toInt()))
                check("Send editor gets the two-tone send mark and the real send action",
                    ui.hasObject(By.res("key_enter").desc("发送").enabled(true)) && hasInk(idle, boundsOf("enter"),
                    .21f, .52f, .53f, .79f, 0xff9391ea.toInt()))
            } finally { idle.recycle() }
            d.type("gongyuan")
            d.candidate("公园")
            d.expectText("gong yuan")
            check("First candidates do not move the keyboard", idleBounds == d.keyBounds("q"))
            shot("soft-pop-light-candidates")

            d.tapKey("page")
            val pairedBounds = d.keyBounds("1")
            choose("default", "dark")
            d.expectText("gong yuan")
            check("Switching skins preserves the numeric page", ui.hasObject(By.res("key_1")) && !ui.hasObject(By.res("key_q")))
            choose("soft-pop")
            d.expectText("gong yuan")
            check("Paired page returns without moving the first key", pairedBounds == d.keyBounds("1"))
            d.openQuickSettings()
            check("Appearance and English visibility survive skin changes", selected("theme_dark") && englishToggle().isChecked)
            shot("skin-settings-dark")
            d.closeQuickSettings()
            d.tapKey("space")
            d.tapKey("1")
            d.expectText("公园1")
            check("Numeric page commits Chinese normally before a digit", d.editor().text == "公园1")
            d.holdKey("1")
            d.expectText("公园1q")
            check("Numeric secondary letter starts real pinyin composition", ui.hasObject(By.res("candidate_0")))
            d.tapKey("delete")
            d.tapKey("page")
            clear()
            d.type("gongyuan")
            d.candidate("公园")
            d.tapKey("details")
            check("Details key opens the current word without committing it", ui.wait(Until.hasObject(By.res("definition_panel")), 8000) && d.editor().text == "gong yuan")
            shot("soft-pop-definition")
            ui.findObject(By.res("commit_english")).click()
            d.expectText("park")
            check("English is committed only by the explicit definition action", d.editor().text == "park")

            d.launch("email")
            choose("soft-pop", "light")
            d.type(alphabet, 0)
            d.expectText(alphabet)
            check("Vector keycaps retain all 26 ordinary letter inputs", d.editor().text == alphabet)
            clear()
            alphabet.forEach { d.holdKey(it.toString()) }
            d.expectText(symbols)
            check("All 26 letter-page secondary symbols match the design", d.editor().text == symbols)
            clear()
            d.tapKey("page")
            shot("soft-pop-light-symbols")
            symbols.forEach { d.tapKey(it.toString()) }
            d.expectText(symbols)
            check("All 26 numeric-page primary symbols match the design", d.editor().text == symbols)
            clear()
            // UiAutomator setText restarts the editor, which opens its default
            // letter page. Re-enter numbers before testing their secondary keys.
            d.tapKey("page")
            symbols.forEach { d.holdKey(it.toString()) }
            d.expectText(alphabet)
            check("All 26 numeric-page secondary letters avoid duplicate taps", d.editor().text == alphabet)
            d.tapKey("page")
            clear()
            d.tapKey("shift")
            shot("soft-pop-uppercase")
            d.tapKey("q")
            d.tapKey("w")
            d.expectText("Qw")
            check("Shift is a single uppercase letter", d.editor().text == "Qw")
            d.holdKey("page")
            d.tapKey("'")
            d.expectText("Qw'")
            check("More symbols remain available by holding 123 / ABC", d.editor().text == "Qw'")
            d.tapKey("page")
            clear()

            val point = d.keyCenter("q")
            val started = SystemClock.uptimeMillis()
            fun touch(action: Int, y: Float) {
                val event = MotionEvent.obtain(started, SystemClock.uptimeMillis(), action, point.x.toFloat(), y, 0)
                d.instrumentation.uiAutomation.injectInputEvent(event, true)
                event.recycle()
            }
            touch(MotionEvent.ACTION_DOWN, point.y.toFloat())
            SystemClock.sleep(80)
            touch(MotionEvent.ACTION_MOVE, point.y + 24f)
            SystemClock.sleep(600)
            touch(MotionEvent.ACTION_UP, point.y + 24f)
            SystemClock.sleep(100)
            check("Movement inside a key cancels both tap and long press", d.editor().text.isNullOrEmpty() || d.editor().text == "在这里输入")

            for (width in listOf(320, 390)) {
                ui.executeShellCommand("wm size ${width * 2}x1688")
                for (skin in listOf("default", "soft-pop")) {
                    for (theme in listOf("light", "dark")) {
                        d.launch()
                        choose(skin, theme)
                        d.type("gongyuan")
                        d.candidate("公园")
                        val bounds = allKeys.map { d.keyBounds(it) }
                        check("$skin $theme $width dp keeps every key reachable", bounds.all { it.left >= 0 && it.right <= ui.displayWidth && it.bottom <= ui.displayHeight && it.height() >= 96 })
                        val expected = when (skin to theme) {
                            "soft-pop" to "light" -> 0xfff0eff4.toInt()
                            "soft-pop" to "dark" -> 0xff292b36.toInt()
                            "default" to "light" -> 0xffe8eeea.toInt()
                            else -> 0xff202d25.toInt()
                        }
                        pixels("$skin-$theme-${width}dp", expected)
                        d.tapKey("space")
                        d.expectText("公园")
                        if (skin == "soft-pop") {
                            d.tapKey("page")
                            shot("$skin-$theme-${width}dp-symbols")
                            d.tapKey("1")
                            d.expectText("公园1")
                        }
                    }
                }
            }
            for (font in listOf("1.3", "2.0")) {
                ui.executeShellCommand("settings put system font_scale $font")
                ui.executeShellCommand("wm size 640x1688")
                d.launch()
                choose("soft-pop", "dark")
                d.type("gongyuan")
                d.candidate("公园")
                shot("soft-pop-320dp-font$font")
                d.tapKey("page")
                shot("soft-pop-320dp-font$font-symbols")
                check("Font $font retains ${allKeys.size} distinct keys and visible bottom actions", ui.findObjects(By.res(java.util.regex.Pattern.compile("key_.+"))).size == allKeys.size && d.keyBounds("enter").bottom <= ui.displayHeight)
                d.tapKey("space")
                d.expectText("公园")
            }
            ui.executeShellCommand("settings put system font_scale 1.0")
            ui.executeShellCommand("wm size 780x1688")
            d.launch()
            choose("soft-pop", "dark")
            ui.setOrientationLeft()
            d.key("g")
            clear()
            d.type("gongyuan")
            d.candidate("公园")
            shot("soft-pop-landscape")
            check("Landscape keeps enter and paired keys on screen", d.keyBounds("enter").bottom <= ui.displayHeight)
            ui.setOrientationNatural()
            ui.executeShellCommand("settings put system font_scale 2.0")
            d.launch("email")
            choose("soft-pop", "dark")
            ui.setOrientationLeft()
            // Rotation recreates the probe. Do not focus its outgoing portrait
            // EditText or send keys to the temporary non-editor connection.
            fun landscapeEditor(action: (EditText) -> Unit) {
                d.instrumentation.runOnMainSync {
                    val activity = ActivityLifecycleMonitorRegistry.getInstance().getActivitiesInStage(Stage.RESUMED)
                        .filterIsInstance<ProbeActivity>().singleOrNull() ?: return@runOnMainSync
                    if (!activity.hasWindowFocus() || activity.resources.configuration.orientation !=
                        android.content.res.Configuration.ORIENTATION_LANDSCAPE) return@runOnMainSync
                    action(activity.findViewById(R.id.probe_text))
                }
            }
            val emailAction = By.res("key_enter").desc("完成").enabled(true)
            val focusDeadline = SystemClock.uptimeMillis() + 8000
            var focused = false
            while (!(focused && ui.hasObject(emailAction)) && SystemClock.uptimeMillis() < focusDeadline) {
                landscapeEditor { editor ->
                    editor.requestFocus()
                    val imm = editor.context.getSystemService(InputMethodManager::class.java)
                    imm.showSoftInput(editor, 0)
                    focused = editor.hasFocus() && imm.isActive(editor)
                }
                SystemClock.sleep(100)
            }
            check("Rotated email editor has a real input connection", focused && ui.hasObject(emailAction))
            d.key("q")
            d.tapKey("page")
            shot("soft-pop-landscape-font2-symbols")
            d.tapKey("1")
            var nativeText = ""
            val deadline = SystemClock.uptimeMillis() + 8000
            while (nativeText != "1" && SystemClock.uptimeMillis() < deadline) {
                landscapeEditor { nativeText = it.text.toString() }
                if (nativeText != "1") SystemClock.sleep(50)
            }
            check("Large landscape digit reaches the real editor", nativeText == "1")
            check("Large landscape symbols keep both layers and actions reachable", d.keyBounds("enter").bottom <= ui.displayHeight)
            ui.setOrientationNatural()
            ui.executeShellCommand("settings put system font_scale 1.0")
            d.launch()
            choose("soft-pop", "system")
            for ((night, expected) in listOf("yes" to 0xff292b36.toInt(), "no" to 0xfff0eff4.toInt())) {
                ui.executeShellCommand("cmd uimode night $night")
                d.editor().click()
                d.key("q")
                SystemClock.sleep(300)
                pixels("soft-pop-system-$night", expected)
            }

            if (d.imePackage != d.context.packageName) {
                choose("soft-pop", "dark")
                d.openQuickSettings()
                if (englishToggle().isChecked) englishToggle().click()
                d.closeQuickSettings()
                ui.executeShellCommand("am force-stop ${d.imePackage}")
                d.rebind()
                d.editor().click()
                d.key("q")
                d.openQuickSettings()
                check("A fresh IME process restores skin, theme and English preference", selected("skin_soft-pop") && selected("theme_dark") && !englishToggle().isChecked)
                d.closeQuickSettings()
            }
            ui.pressHome()
            d.context.startActivity(Intent().setClassName(d.imePackage, "org.studyime.android.MainActivity")
                .putExtra("screen", "settings").addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK))
            ui.wait(Until.hasObject(By.text("拼音方案")), 8000)
            repeat(4) { if (!ui.hasObject(By.res("settings_skin_default"))) ui.swipe(300, 1100, 300, 450, 20) }
            val defaultChip = ui.wait(Until.findObject(By.res("settings_skin_default")), 5000) ?: error("Full settings skin picker missing")
            defaultChip.click()
            d.launch()
            d.openQuickSettings()
            check("Full settings and inline settings share the same skin", selected("skin_default"))
            d.closeQuickSettings()
            report.put("passed", true)
        } finally {
            if (!report.optBoolean("passed")) shot("failure")
            ui.setOrientationNatural()
            ui.unfreezeRotation()
            ui.executeShellCommand("settings put system font_scale $originalFont")
            ui.executeShellCommand("wm size reset")
            ui.executeShellCommand("wm density reset")
            if (originalNight in listOf("yes", "no", "auto")) ui.executeShellCommand("cmd uimode night $originalNight")
            runCatching {
                d.launch()
                choose(originalSkin, originalTheme)
                d.openQuickSettings()
                if (englishToggle().isChecked != originalEnglish) englishToggle().click()
                d.closeQuickSettings()
            }.onFailure { report.put("restoreError", it.toString()) }
            File(d.context.filesDir, "skin-switch-report.json").writeText(report.toString(2))
        }
    }

    // Test colour and placement, not an emulator-specific antialiasing hash.
    private fun hasInk(image: Bitmap, key: Rect, x1: Float, y1: Float, x2: Float, y2: Float, ink: Int): Boolean {
        val left = key.left + (x1 * key.width()).toInt()
        val top = key.top + (y1 * key.height()).toInt()
        for (y in top until key.top + (y2 * key.height()).toInt()) {
            for (x in left until key.left + (x2 * key.width()).toInt()) {
                val c = image.getPixel(x, y)
                if (abs(Color.red(c) - Color.red(ink)) < 16 && abs(Color.green(c) - Color.green(ink)) < 16 &&
                    abs(Color.blue(c) - Color.blue(ink)) < 16) return true
            }
        }
        return false
    }
}
