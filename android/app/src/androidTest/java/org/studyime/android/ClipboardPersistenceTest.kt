// SPDX-License-Identifier: GPL-3.0-or-later
package org.studyime.android

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Intent
import android.os.SystemClock
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.uiautomator.By
import androidx.test.uiautomator.UiObject2
import androidx.test.uiautomator.Until
import java.io.File
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/** A separate optimized IME process is stopped and reopened; the debug runner stays alive. */
@RunWith(AndroidJUnit4::class)
class ClipboardPersistenceTest {
    @Test fun optimizedImeRestoresPinnedHistoryAfterProcessDeath() {
        val d = ImeDriver()
        require(d.imePackage == "org.studyime.android") { "Use --ime-package org.studyime.android for the separate release process" }
        val ui = d.device
        val manager = d.context.getSystemService(ClipboardManager::class.java)
        val text = "重启后粘贴 🐈 ${SystemClock.elapsedRealtime()}"
        val checks = JSONArray()
        val report = JSONObject().put("checks", checks).put("imePackage", d.imePackage)
            .put("scope", "Optimized APK: exact paste through InputConnection, pinned history after process death, UI cleanup")
        var originallyEnabled = false
        fun check(name: String, value: Boolean) { checks.put(JSONObject().put("name", name).put("passed", value)); assertTrue(name, value) }
        fun open() {
            if (!ui.hasObject(By.res("clipboard_panel"))) {
                if (!ui.hasObject(By.desc("剪贴板历史"))) d.openQuickSettings()
                ui.findObject(By.desc("剪贴板历史")).click()
            }
            check("Optimized clipboard panel opens", ui.wait(Until.hasObject(By.res("clipboard_panel")), 5000))
        }
        fun row(): UiObject2 {
            val panel = ui.wait(Until.findObject(By.res("clipboard_panel").hasDescendant(By.text(text))), 6000)
                ?: error("Synthetic persisted clipboard entry missing")
            var node = panel.findObject(By.text(text))
            while (!node.resourceName.orEmpty().startsWith("clipboard_item_")) node = node.parent ?: error("Clipboard row missing")
            return node
        }
        fun restartProcess() {
            val previousPid = ui.executeShellCommand("pidof ${d.imePackage}").trim()
            ui.pressHome()
            ui.executeShellCommand("am force-stop ${d.imePackage}")
            // Android can back off repeated bound-service restarts. Start the
            // app explicitly so this tests persisted data in a new process,
            // independently of the system's automatic IME restart delay.
            d.context.startActivity(Intent().setClassName(d.imePackage, "org.studyime.android.MainActivity")
                .putExtra("screen", "home").addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK))
            check("A fresh app process starts", ui.wait(Until.hasObject(By.pkg(d.imePackage).textContains("顺便拾起一个词")), 10000))
            val currentPid = ui.executeShellCommand("pidof ${d.imePackage}").trim()
            check("The previous process was replaced", previousPid.isNotEmpty() && currentPid.isNotEmpty() && previousPid != currentPid)
            d.rebind()
            d.launch("multiline")
        }
        try {
            d.launch("multiline")
            open()
            originallyEnabled = ui.findObject(By.res("clipboard_toggle")).isChecked
            if (!originallyEnabled) ui.findObject(By.res("clipboard_enable")).click()
            d.instrumentation.runOnMainSync { manager.setPrimaryClip(ClipData.newPlainText("StudyIME synthetic restart test", text)) }
            val entry = row()
            entry.findObject(By.desc("置顶条目")).click()
            check("Optimized app pins the copied text", ui.wait(Until.hasObject(By.desc("取消置顶")), 5000))
            ui.findObject(By.desc("关闭剪贴板面板")).click()
            d.type("gongyuan")
            d.candidate("公园")
            open()
            row().findObject(By.text(text)).click()
            d.expectText("公园$text")
            check("Optimized paste finishes composition and retains Unicode", d.editor().text == "公园$text")
            restartProcess()
            open()
            check("A new process restores the pinned entry", row().findObject(By.desc("取消置顶")) != null)
            row().findObject(By.text(text)).click()
            d.expectText(text)
            check("Restored clipboard pastes exactly once", d.editor().text == text)
            open()
            row().findObject(By.desc("删除条目")).click()
            check("Deleting the persisted entry removes it", ui.wait(Until.gone(By.res("clipboard_panel").hasDescendant(By.text(text))), 5000))
            ui.findObject(By.desc("关闭剪贴板面板")).click()
            restartProcess()
            open()
            check("Deleted current clipboard stays deleted after a new process", !ui.hasObject(By.res("clipboard_panel").hasDescendant(By.text(text))))
            report.put("passed", true)
        } catch (failure: Throwable) {
            report.put("passed", false).put("failure", failure.toString())
            runCatching { d.capture("clipboard-persistence", "failure") }
            throw failure
        } finally {
            val cleanup = runCatching {
                open()
                if (!originallyEnabled && ui.findObject(By.res("clipboard_toggle")).isChecked) {
                    ui.findObject(By.res("clipboard_toggle")).click()
                    ui.findObject(By.res("clipboard_confirm")).click()
                    check("Original disabled preference is restored", ui.wait(Until.hasObject(By.res("clipboard_enable")), 5000))
                }
            }
            d.instrumentation.runOnMainSync { manager.clearPrimaryClip() }
            if (cleanup.isFailure) report.put("passed", false).put("cleanupFailure", cleanup.exceptionOrNull().toString())
            File(d.context.filesDir, "clipboard-persistence-report.json").writeText(report.toString(2))
            cleanup.getOrThrow()
        }
    }
}
