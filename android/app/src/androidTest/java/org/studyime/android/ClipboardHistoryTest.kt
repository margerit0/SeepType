// SPDX-License-Identifier: GPL-3.0-or-later
package org.studyime.android

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Intent
import android.graphics.BitmapFactory
import android.graphics.Rect
import android.net.Uri
import android.os.PersistableBundle
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
import kotlin.math.abs
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.studyime.android.clipboard.ClipboardHistory
import org.studyime.android.clipboard.ClipboardHistoryFile
import org.studyime.android.clipboard.ClipboardHistoryRepository
import org.studyime.android.settings.KeyboardSkin
import org.studyime.android.settings.Preferences

/** Uses only synthetic clipboard data in the debug development app/emulator. */
@RunWith(AndroidJUnit4::class)
class ClipboardHistoryTest {
    @Test fun clipboardHistoryInRealEditors() {
        val d = ImeDriver()
        require(d.imePackage == d.context.packageName) { "Clipboard checks use the isolated debug app" }
        val ui = d.device
        val repository = ClipboardHistoryRepository.get(d.context)
        val manager = d.context.getSystemService(ClipboardManager::class.java)
        val preferences = Preferences.get(d.context)
        val originalPrefs = preferences.state.value
        val originalFont = ui.executeShellCommand("settings get system font_scale").trim()
        val checks = JSONArray()
        val captures = JSONArray()
        val report = JSONObject().put("checks", checks).put("captures", captures)
            .put("scope", "Synthetic clipboard, private editors, actual InputConnection paste, persistence file and native layouts")
        fun check(name: String, value: Boolean) {
            checks.put(JSONObject().put("name", name).put("passed", value)); assertTrue(name, value)
        }
        fun waitFor(name: String, condition: () -> Boolean) {
            val deadline = SystemClock.uptimeMillis() + 6000
            while (!condition() && SystemClock.uptimeMillis() < deadline) SystemClock.sleep(25)
            check(name, condition())
        }
        fun history() = repository.state.value.history
        fun copy(text: String, sensitive: Boolean = false) {
            val before = history().lastTimestamp
            d.instrumentation.runOnMainSync {
                manager.setPrimaryClip(ClipData.newPlainText("StudyIME synthetic clipboard", text).apply {
                    if (sensitive) description.extras = PersistableBundle().apply { putBoolean("android.content.extra.IS_SENSITIVE", true) }
                })
            }
            waitFor("Clipboard version observed", { history().lastTimestamp != before })
        }
        fun open() {
            if (ui.hasObject(By.res("clipboard_panel"))) return
            val entry = ui.findObject(By.desc("剪贴板历史"))
            if (entry != null) entry.click() else {
                d.openQuickSettings()
                ui.findObject(By.desc("剪贴板历史")).click()
            }
            check("Clipboard panel opens", ui.wait(Until.hasObject(By.res("clipboard_panel")), 5000))
        }
        fun close() {
            ui.findObject(By.desc("关闭剪贴板面板")).click()
            check("Keyboard returns", ui.wait(Until.gone(By.res("clipboard_panel")), 5000))
        }
        fun shot(name: String) { captures.put("$name.png"); d.capture("clipboard", name) }
        fun awaitBoardColor(expected: Int) {
            val sample = File(d.context.cacheDir, "clipboard-frame.png")
            val deadline = SystemClock.uptimeMillis() + 5000
            var matches = false
            try {
                while (!matches && SystemClock.uptimeMillis() < deadline) {
                    val bounds = ui.findObject(By.res("study_keyboard")).visibleBounds
                    if (ui.takeScreenshot(sample)) {
                        val bitmap = BitmapFactory.decodeFile(sample.path)
                        matches = bitmap.getPixel(bounds.left + 2, bounds.top + 2) == expected
                        bitmap.recycle()
                    }
                    if (!matches) SystemClock.sleep(50)
                }
                check("Selected theme reaches a rendered clipboard frame", matches)
            } finally { sample.delete() }
        }
        fun verifyToolbar(label: String): List<Rect> {
            val toolbar = ui.wait(Until.findObject(By.res("idle_toolbar").hasDescendant(By.desc("切换浅深色"))), 5000)
                ?: error("Ready toolbar missing")
            val bounds = toolbar.visibleBounds
            val buttons = listOf("键盘设置", "表情符号", "剪贴板历史", "切换浅深色", "显示英文释义").map { description ->
                val button = toolbar.findObject(By.desc(description)) ?: error("Missing toolbar button: $description")
                check("$label: $description has a 48 dp touch target", button.isEnabled && button.visibleBounds.let {
                    it.width() >= 96 && it.height() >= 96 && abs(it.centerY() - bounds.centerY()) <= 1
                })
                button.visibleBounds
            }
            val gaps = buttons.zipWithNext { left, right -> right.left - left.right }
            check("$label: tools are ordered in equal 6 dp gaps and centered",
                gaps.all { abs(it - 12) <= 1 } && abs(buttons.first().left - bounds.left - (bounds.right - buttons.last().right)) <= 1)
            return buttons
        }
        fun verifyGloss(checked: Boolean) {
            check("Bubble reports switch state $checked", ui.wait(Until.hasObject(By.desc("显示英文释义").checked(checked)), 5000))
            d.type("ni")
            val description = if (checked) By.descStartsWith("泥，英文释义：") else By.desc("泥")
            check("Bubble state $checked reaches the real candidate strip", ui.wait(Until.hasObject(description), 5000))
            repeat(2) { d.tapKey("delete") }
            check("Returning to idle after inspecting candidate labels", ui.wait(Until.hasObject(By.res("idle_toolbar")), 5000))
        }
        fun primary(): EditText {
            val activity = ActivityLifecycleMonitorRegistry.getInstance().getActivitiesInStage(Stage.RESUMED).filterIsInstance<ProbeActivity>().single()
            return activity.findViewById(R.id.probe_text)
        }
        try {
            ui.setOrientationNatural()
            ui.executeShellCommand("wm density 320")
            ui.executeShellCommand("wm size 780x1688")
            ui.executeShellCommand("settings put system font_scale 1.0")
            waitFor("History loads without blocking the IME", { repository.state.value.loaded })
            repository.setEnabled(false)
            waitFor("Synthetic history starts disabled", { !history().enabled })
            d.launch("multiline")
            d.instrumentation.runOnMainSync { manager.clearPrimaryClip() }
            preferences.update { it.copy(skin = KeyboardSkin.SOFT_POP) }
            awaitBoardColor(0xfff0eff4.toInt())
            val initialToolbar = verifyToolbar("Light portrait")
            verifyGloss(true)
            shot("toolbar-light-on")
            ui.findObject(By.desc("显示英文释义")).click()
            verifyGloss(false)
            check("Switching off English does not move the toolbar", verifyToolbar("English off") == initialToolbar)
            shot("toolbar-light-off")
            ui.findObject(By.desc("切换浅深色")).click()
            awaitBoardColor(0xff292b36.toInt())
            ui.findObject(By.desc("显示英文释义")).click()
            verifyGloss(true)
            check("Switching theme does not move the toolbar", verifyToolbar("Dark portrait") == initialToolbar)
            shot("toolbar-dark-on")
            ui.findObject(By.desc("切换浅深色")).click()
            awaitBoardColor(0xfff0eff4.toInt())
            open()
            check("Explicit opt-in is available", ui.wait(Until.hasObject(By.res("clipboard_enable")), 5000))
            shot("disabled-light")
            ui.findObject(By.res("clipboard_enable")).click()
            waitFor("Opt-in persists", { history().enabled })
            val first = "第一条测试文本"
            val second = "  剪贴板测试 🐈\nsecond line  "
            copy(first)
            val firstId = history().entries.first { it.text == first }.id
            copy(second)
            copy(first)
            check("Duplicate copies move to the top", history().entries.first().id == firstId && history().entries.count { it.text == first } == 1)
            val secondId = history().entries.first { it.text == second }.id
            ui.wait(Until.findObject(By.res("clipboard_pin_$firstId")), 5000).click()
            waitFor("Pin action persists", { history().entries.first { it.id == firstId }.pinned })
            shot("history-light")
            close()
            d.type("gongyuan")
            d.candidate("公园")
            open()
            ui.wait(Until.findObject(By.res("clipboard_text_$secondId")), 5000).click()
            d.expectText("公园$second")
            check("Paste finishes Chinese composition and preserves exact multiline Unicode", d.editor().text == "公园$second")

            ui.pressHome()
            check("IME hides on a non-editor screen", ui.wait(Until.gone(By.res("study_keyboard")), 5000))
            copy("copied away from the editor")
            check("Running default IME records copies away from an editor", history().entries.any { it.text == "copied away from the editor" })

            d.launch("multiline")
            d.instrumentation.runOnMainSync { primary().apply { setText("replace this"); setSelection(0, length()) } }
            ui.waitForIdle()
            open()
            ui.wait(Until.findObject(By.res("clipboard_text_$firstId")), 5000).click()
            d.expectText(first)
            check("Paste replaces the selected editor range", d.editor().text == first)

            open()
            val point = ui.wait(Until.findObject(By.res("clipboard_text_$firstId")), 5000).visibleCenter
            val downTime = SystemClock.uptimeMillis()
            fun touch(action: Int) {
                val event = MotionEvent.obtain(downTime, SystemClock.uptimeMillis(), action, point.x.toFloat(), point.y.toFloat(), 0)
                d.instrumentation.uiAutomation.injectInputEvent(event, true); event.recycle()
            }
            touch(MotionEvent.ACTION_DOWN)
            d.instrumentation.runOnMainSync {
                val activity = ActivityLifecycleMonitorRegistry.getInstance().getActivitiesInStage(Stage.RESUMED).filterIsInstance<ProbeActivity>().single()
                activity.findViewById<EditText>(R.id.probe_other).apply {
                    requestFocus()
                    activity.getSystemService(InputMethodManager::class.java).showSoftInput(this, InputMethodManager.SHOW_IMPLICIT)
                }
            }
            d.key("g")
            touch(MotionEvent.ACTION_UP)
            ui.waitForIdle()
            check("A held paste cannot reach a different editor", d.editor().text == first &&
                d.editor("probe_other").text.let { it.isNullOrEmpty() || it == "第二个输入位置" })

            for (kind in listOf("password", "numberPassword", "private")) {
                d.launch(kind)
                var entry = ui.findObject(By.desc("剪贴板历史")) ?: error("History entry missing")
                while (!entry.isClickable) entry = entry.parent ?: error("History button missing")
                check("$kind disables history access", !entry.isEnabled)
                val hit = entry.visibleCenter
                ui.click(hit.x, hit.y)
                check("$kind cannot open history by touch", !ui.hasObject(By.res("clipboard_panel")))
                copy("private-$kind")
                check("$kind does not record clipboard text", history().entries.none { it.text == "private-$kind" })
                d.launch("multiline")
                ui.waitForIdle()
                check("Leaving $kind does not import its clipboard", history().entries.none { it.text == "private-$kind" })
            }
            copy("sensitive synthetic token", sensitive = true)
            check("Sensitive clipboard flag is respected", history().entries.none { it.text == "sensitive synthetic token" })
            val beforeUnsupported = history().entries
            d.instrumentation.runOnMainSync { manager.setPrimaryClip(ClipData.newRawUri("synthetic URI", Uri.parse("content://studyime.test/image"))) }
            SystemClock.sleep(300)
            check("URI clipboard is not resolved or stored", history().entries == beforeUnsupported)
            d.instrumentation.runOnMainSync { manager.setPrimaryClip(ClipData.newPlainText("synthetic long clip", "中".repeat(1366))) }
            SystemClock.sleep(300)
            check("Oversized UTF-8 text is skipped without truncation", history().entries == beforeUnsupported)

            // Fresh readers exercise the on-disk format and the deletion tombstone, not a shared in-memory cache.
            val file = File(d.context.cacheDir, "synthetic-clipboard-roundtrip.json")
            try {
                val storage = ClipboardHistoryFile(file)
                storage.write(history())
                check("Pinned history and exact text survive a fresh file reader", ClipboardHistoryFile(file).read() == history())
                val deleted = history().record("roundtrip-deleted", 100, 100).clear()
                storage.write(deleted)
                check("Deleted clipboard stays deleted after reloading", ClipboardHistoryFile(file).read().record("roundtrip-deleted", 100).entries.isEmpty())
                file.writeText("{broken")
                check("Corrupt storage is rejected", runCatching { ClipboardHistoryFile(file).read() }.isFailure)
            } finally { file.delete(); File(file.path + ".bak").delete() }

            copy("布局测试：可以粘贴，也可以置顶。")
            open()
            for ((skin, theme, name) in listOf(Triple(KeyboardSkin.DEFAULT, "dark", "default-dark"),
                Triple(KeyboardSkin.SOFT_POP, "light", "soft-pop-light"), Triple(KeyboardSkin.SOFT_POP, "dark", "soft-pop-dark"))) {
                preferences.update { it.copy(skin = skin, theme = theme) }
                awaitBoardColor(when (skin to theme) {
                    KeyboardSkin.DEFAULT to "dark" -> 0xff202d25.toInt()
                    KeyboardSkin.SOFT_POP to "light" -> 0xfff0eff4.toInt()
                    else -> 0xff292b36.toInt()
                })
                shot(name)
            }
            ui.executeShellCommand("wm size 640x1688")
            ui.executeShellCommand("settings put system font_scale 2.0")
            d.launch("multiline", "dark")
            verifyToolbar("320 dp / 2x font")
            shot("toolbar-narrow-large-dark")
            open()
            val panel = ui.findObject(By.res("clipboard_panel")).visibleBounds
            val controls = listOf(ui.findObject(By.res("clipboard_clear")), ui.findObject(By.res("clipboard_toggle")), ui.findObject(By.desc("关闭剪贴板面板")))
            check("320 dp with 2x font keeps panel controls reachable", controls.all { node ->
                if (node == null) false else {
                    var control = node
                    while (!control.isClickable) control = control.parent ?: error("Panel control missing")
                    control.visibleBounds.let { bounds -> bounds.left >= panel.left && bounds.right <= panel.right && bounds.height() >= 96 }
                }
            })
            shot("narrow-large-dark")
            ui.executeShellCommand("settings put system font_scale 1.0")
            ui.setOrientationLeft()
            // This deliberately tall synthetic editor is outside the resized
            // app viewport in landscape. Its focused connection is still live;
            // operate the IME directly instead of trying to click that editor.
            check("Landscape IME remains visible", ui.wait(Until.hasObject(By.res("study_keyboard")), 5000))
            verifyToolbar("Landscape")
            open()
            preferences.update { it.copy(theme = "light") }
            awaitBoardColor(0xfff0eff4.toInt())
            check("Landscape gives the clipboard the full keyboard width", ui.findObject(By.res("clipboard_panel")).visibleBounds.width() > ui.displayWidth * .9)
            shot("landscape-light")
            ui.setOrientationNatural()
            d.launch("multiline")
            open()
            ui.wait(Until.findObject(By.res("clipboard_delete_$firstId")), 5000).click()
            waitFor("Individual deletion removes pinned entries", { history().entries.none { it.id == firstId } })
            ui.findObject(By.res("clipboard_clear")).click()
            ui.wait(Until.findObject(By.text("取消")), 5000).click()
            check("Cancelling clear preserves entries", history().entries.isNotEmpty())
            ui.findObject(By.res("clipboard_clear")).click()
            ui.wait(Until.findObject(By.res("clipboard_confirm")), 5000).click()
            waitFor("Clear removes all entries", { history().entries.isEmpty() })
            close(); open()
            check("Reopening after clear keeps the history empty", history().entries.isEmpty())
            shot("empty-light")
            copy("fresh synthetic clipboard")
            ui.findObject(By.res("clipboard_toggle")).click()
            ui.wait(Until.findObject(By.res("clipboard_confirm")), 5000).click()
            waitFor("Disabling clears stored history", { !history().enabled && history().entries.isEmpty() })
            val stored = ClipboardHistoryFile(File(d.context.noBackupFilesDir, "clipboard/history-v1.json")).read()
            check("Disabled storage contains no text entries", !stored.enabled && stored.entries.isEmpty())
            d.instrumentation.runOnMainSync { manager.setPrimaryClip(ClipData.newPlainText("synthetic disabled copy", "copied while disabled")) }
            SystemClock.sleep(300)
            check("Disabled history does not collect copies", history().entries.isEmpty())

            d.context.startActivity(Intent(d.context, MainActivity::class.java).putExtra("screen", "settings")
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK))
            val setting = ui.wait(Until.findObject(By.res("settings_clipboard_toggle")), 5000) ?: error("Clipboard setting missing")
            setting.click()
            waitFor("App settings can enable history", { history().enabled })
            check("Settings reflects the enabled state", ui.wait(Until.hasObject(By.res("settings_clipboard_toggle").checked(true)), 5000))
            ui.findObject(By.res("settings_clipboard_toggle")).click()
            check("Disabling in settings asks before clearing", ui.wait(Until.hasObject(By.text("关闭并清空历史？")), 5000) && history().enabled)
            ui.findObject(By.text("关闭并清空")).click()
            waitFor("Settings confirmation disables and clears history", { !history().enabled && history().entries.isEmpty() })
            report.put("passed", true)
        } catch (failure: Throwable) {
            report.put("passed", false).put("failure", failure.toString())
            runCatching { shot("failure") }
            throw failure
        } finally {
            repository.setEnabled(false)
            d.instrumentation.runOnMainSync { manager.clearPrimaryClip() }
            preferences.update { originalPrefs }
            ui.executeShellCommand("settings put system font_scale $originalFont")
            ui.executeShellCommand("wm size reset")
            ui.executeShellCommand("wm density reset")
            ui.unfreezeRotation()
            File(d.context.filesDir, "clipboard-history-report.json").writeText(report.toString(2))
        }
    }
}
