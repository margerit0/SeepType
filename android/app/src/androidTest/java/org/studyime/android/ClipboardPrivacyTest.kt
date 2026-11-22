// SPDX-License-Identifier: GPL-3.0-or-later
package org.studyime.android

import android.content.ClipData
import android.content.ClipboardManager
import android.os.SystemClock
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.uiautomator.By
import androidx.test.uiautomator.Direction
import androidx.test.uiautomator.Until
import java.io.File
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/** Exercise the installed optimized IME through its UI, without reading its files. */
@RunWith(AndroidJUnit4::class)
class ClipboardPrivacyTest {
    @Test fun optimizedImeNeverKeepsClipsFromProtectedEditors() {
        val d = ImeDriver()
        require(d.imePackage == "org.studyime.android" && !d.privateDevice)
        val ui = d.device
        val manager = d.context.getSystemService(ClipboardManager::class.java)
        val panel = By.res("clipboard_panel")
        val list = By.res("clipboard_list")
        val stem = "StudyIME QA ${SystemClock.elapsedRealtimeNanos()}"
        val control = "$stem regular"
        val checks = JSONArray()
        val report = JSONObject().put("passed", false).put("checks", checks).put("imePackage", d.imePackage)
            .put("scope", "Dedicated emulator, separate Release IME, real synthetic editors and clipboard UI")
        var originallyEnabled: Boolean? = null
        var failureSeen: Throwable? = null

        fun check(name: String, passed: Boolean) {
            checks.put(JSONObject().put("name", name).put("passed", passed))
            assertTrue(name, passed)
        }
        fun entry() = ui.wait(Until.findObject(By.desc("剪贴板历史")), 5000)
            ?.let { found ->
                var node = found
                while (!node.isClickable && node.isEnabled) node = node.parent ?: error("Clipboard button missing")
                node
            } ?: error("Clipboard history entry not available")
        fun open() {
            if (!ui.hasObject(panel)) entry().click()
            check("Optimized clipboard panel is visible", ui.wait(Until.hasObject(panel), 5000))
        }
        fun copy(text: String) = d.instrumentation.runOnMainSync {
            manager.setPrimaryClip(ClipData.newPlainText("StudyIME synthetic clipboard privacy test", text))
        }
        fun historyText(text: String): Boolean {
            // Traverse the entire list, including entries below pinned rows. A
            // failed or incomplete traversal cannot count as a privacy pass.
            val exists = By.res("clipboard_panel").hasDescendant(By.text(text))
            repeat(80) {
                if (ui.hasObject(exists)) return true
                val scroller = ui.wait(Until.findObject(list), 5000) ?: error("History control entry unexpectedly absent")
                if (!scroller.scroll(Direction.DOWN, .6f)) {
                    ui.waitForIdle()
                    return ui.hasObject(exists)
                }
            }
            error("Did not reach the end of clipboard history")
        }

        try {
            d.launch("text", configure = false)
            val initialPid = ui.executeShellCommand("pidof ${d.imePackage}").trim()
            check("Release IME process starts", initialPid.isNotEmpty())
            open()
            originallyEnabled = ui.wait(Until.findObject(By.res("clipboard_toggle")), 5000)!!.isChecked
            if (originallyEnabled == false) ui.wait(Until.findObject(By.res("clipboard_enable")), 5000)!!.click()
            copy(control)
            ui.wait(Until.hasObject(By.res("clipboard_list")), 5000)
            check("Positive control: regular text enters Release clipboard history", historyText(control))

            for (kind in listOf("password", "numberPassword", "private")) {
                d.launch(kind, configure = false)
                val button = entry()
                check("$kind disables clipboard history", !button.isEnabled)
                val point = button.visibleCenter
                ui.click(point.x, point.y)
                check("$kind cannot open clipboard history", !ui.wait(Until.hasObject(panel), 500))
                val protectedText = "$stem $kind"
                copy(protectedText)
                SystemClock.sleep(350)
                // Leave the copied token in the system clipboard while changing
                // editors, so accidental import on focus change also fails.
                d.launch("text", configure = false)
                open()
                check("Leaving $kind does not add its clipboard text to history", !historyText(protectedText))
            }
            check("Release IME never restarted during the privacy test",
                ui.executeShellCommand("pidof ${d.imePackage}").trim() == initialPid)
            report.put("passed", true)
        } catch (failure: Throwable) {
            failureSeen = failure
            report.put("failure", failure.toString())
            throw failure
        } finally {
            val cleanup = runCatching {
                d.instrumentation.runOnMainSync { manager.clearPrimaryClip() }
                if (originallyEnabled != null) {
                    d.launch("text", configure = false)
                    open()
                    val toggle = ui.wait(Until.findObject(By.res("clipboard_toggle")), 5000)!!
                    if (originallyEnabled == false && toggle.isChecked) {
                        toggle.click()
                        ui.wait(Until.findObject(By.res("clipboard_confirm")), 5000)!!.click()
                        check("Original disabled history setting restored", ui.wait(Until.hasObject(By.res("clipboard_enable")), 5000))
                    } else if (originallyEnabled == true && historyText(control)) {
                        var row = ui.findObject(By.text(control))
                        while (!row.resourceName.orEmpty().startsWith("clipboard_item_")) row = row.parent ?: error("Control row missing")
                        row.findObject(By.desc("删除条目")).click()
                        check("Synthetic control entry removed", ui.wait(Until.gone(By.text(control)), 5000))
                    }
                }
            }
            cleanup.exceptionOrNull()?.let { error ->
                report.put("passed", false).put("cleanupFailure", error.toString())
                failureSeen?.addSuppressed(error)
            }
            File(d.context.filesDir, "clipboard-privacy-report.json").writeText(report.toString(2))
            if (failureSeen == null) cleanup.getOrThrow()
        }
    }
}
