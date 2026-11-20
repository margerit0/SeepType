// SPDX-License-Identifier: GPL-3.0-or-later
package org.studyime.android

import android.content.Intent
import android.os.Build
import android.os.Debug
import android.os.SystemClock
import android.view.MotionEvent
import android.view.inputmethod.InputMethodManager
import android.widget.EditText
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.runner.lifecycle.ActivityLifecycleMonitorRegistry
import androidx.test.runner.lifecycle.Stage
import androidx.test.uiautomator.By
import androidx.test.uiautomator.UiObject2
import androidx.test.uiautomator.Until
import java.io.File
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class LifecycleTest {
    @Test fun editorRestartsCursorChangesAndRepeatedReopen() {
        val driver = ImeDriver()
        val device = driver.device
        val checks = JSONArray()
        val report = JSONObject().put("fingerprint", Build.FINGERPRINT).put("imePackage", driver.imePackage)
            .put("scope", "Real Android editor restart, selection, IME lifecycle and synthetic rapid touches").put("checks", checks)
        fun check(name: String, value: Boolean) { checks.put(JSONObject().put("name", name).put("passed", value)); assertTrue(name, value) }
        fun editorAction(work: (ProbeActivity, EditText) -> Unit) {
            driver.instrumentation.runOnMainSync {
                val activity = ActivityLifecycleMonitorRegistry.getInstance().getActivitiesInStage(Stage.RESUMED).filterIsInstance<ProbeActivity>().single()
                work(activity, activity.findViewById(R.id.probe_text))
            }
            device.waitForIdle()
        }
        fun currentText() = driver.editor().text.orEmpty()
        fun candidateAt(index: Int): Pair<UiObject2, String> {
            val card = device.wait(Until.findObject(By.res("candidate_$index")), 5000) ?: error("Candidate $index missing")
            // Compose may expose the merged name through a virtual child of
            // the clickable, selected container. Read either representation.
            val label = card.contentDescription?.takeIf { it.isNotEmpty() }
                ?: card.findObject(By.desc(java.util.regex.Pattern.compile(".+")))?.contentDescription
                ?: error("Candidate $index has no accessible name")
            return card to label
        }
        try {
            device.setOrientationNatural()
            driver.launch()
            driver.type("gongyuan")
            driver.candidate("公园")
            driver.expectText("gong yuan")
            device.pressBack()
            driver.editor().click()
            driver.key("g")
            check("Hiding and reopening the same editor keeps composition", driver.candidate("公园").isEnabled && currentText() == "gong yuan")
            editorAction { activity, view ->
                (activity.getSystemService(android.content.Context.INPUT_METHOD_SERVICE) as InputMethodManager).restartInput(view)
            }
            SystemClock.sleep(200)
            check("Verified framework restart retains Chinese candidates", driver.candidate("公园").isEnabled && currentText() == "gong yuan")
            driver.candidate("公园").click()
            driver.expectText("公园")
            check("Restarted composition commits once", currentText() == "公园")

            editorAction { _, view -> view.setSelection(0, 2) }
            driver.type("nihao")
            driver.candidate("你好").click()
            driver.expectText("你好")
            check("Selected application text is replaced by the next Chinese commit", currentText() == "你好")
            driver.launch("email")
            driver.type("hello")
            driver.expectText("hello")
            editorAction { _, view -> view.setSelection(1, 4) }
            driver.type("a")
            driver.expectText("hao")
            check("Literal input replaces an application selection", currentText() == "hao")

            driver.launch("email")
            val held = driver.key("a").visibleCenter
            val downTime = SystemClock.uptimeMillis()
            driver.instrumentation.uiAutomation.injectInputEvent(MotionEvent.obtain(downTime, downTime,
                MotionEvent.ACTION_DOWN, held.x.toFloat(), held.y.toFloat(), 0), true)
            editorAction { activity, _ -> activity.findViewById<EditText>(R.id.probe_other).requestFocus() }
            SystemClock.sleep(100)
            driver.instrumentation.uiAutomation.injectInputEvent(MotionEvent.obtain(downTime, SystemClock.uptimeMillis(),
                MotionEvent.ACTION_UP, held.x.toFloat(), held.y.toFloat(), 0), true)
            SystemClock.sleep(100)
            check("An old held gesture cannot type into a newly focused editor", driver.editor("probe_other").text.let { it.isNullOrEmpty() || it == "第二个输入位置" })

            driver.launch()
            driver.type("gongyuan")
            driver.candidate("公园")
            driver.openQuickSettings()
            driver.chooseScheme("自然码")
            driver.closeQuickSettings()
            check("Changing scheme preserves pending composition", driver.candidate("公园").isEnabled && currentText() == "gong yuan")
            driver.candidate("公园").click()
            driver.expectText("公园")
            editorAction { _, view -> view.setText("") }
            driver.type("gsyr")
            driver.candidate("公园").click()
            driver.expectText("公园")
            check("Deferred natural-code scheme takes effect after selection", currentText() == "公园")

            driver.launch()
            driver.type("gongyuan")
            driver.candidate("公园")
            val beforeRotation = currentText()
            device.setOrientationLeft()
            driver.key("g")
            check("Activity recreation on rotation retains visible editor text", currentText() == beforeRotation)
            report.put("rotationKeptNativeComposition", device.hasObject(By.descContains("公园")))
            report.put("rotationEditorFocusedBeforeRefocus", driver.editor().isFocused)
            editorAction { _, view -> view.setText("") }
            // Activity recreation can leave the synthetic editor without
            // focus even while Android is still showing its previous IME
            // window. Acquire a real new input connection before testing it.
            driver.editor().click()
            assertTrue("Recreated editor owns input focus", device.wait(Until.hasObject(
                By.res(driver.context.packageName, "probe_text").focused(true)), 5000))
            driver.key("g")
            driver.type("nihao")
            driver.candidate("你好").click()
            driver.expectText("你好")
            check("Fresh input works after refocusing the recreated landscape editor", currentText() == "你好")
            device.setOrientationNatural()
            driver.key("g")

            driver.launch()
            repeat(10) {
                driver.type("nihao", delayMs = 0)
                driver.candidate("你好").click()
            }
            driver.expectText("你好".repeat(10))
            check("Rapid Chinese candidate updates commit every word exactly once", currentText() == "你好".repeat(10))
            driver.launch()
            driver.type("nihaom", delayMs = 0)
            driver.tapKey("delete")
            driver.candidate("你好").click()
            driver.expectText("你好")
            check("Deleting after a rapid Chinese sequence selects the updated candidate", currentText() == "你好")

            driver.launch()
            driver.type("shi")
            val originalCandidate = candidateAt(0).second
            device.findObject(By.desc("展开候选")).click()
            // Icon descriptions live below the clickable button; the icon's
            // own enabled flag does not represent the disabled parent.
            device.wait(Until.findObject(By.clickable(true).enabled(true).hasDescendant(By.desc("下一页候选"))), 5000)!!.click()
            device.wait(Until.findObject(By.clickable(true).enabled(true).hasDescendant(By.desc("上一页候选"))), 5000)!!.click()
            assertTrue("Paging returns to the first page", device.wait(Until.hasObject(
                By.clickable(true).enabled(false).hasDescendant(By.desc("上一页候选"))), 5000))
            val returned = candidateAt(0)
            assertTrue("The original first candidate is restored", returned.second == originalCandidate)
            returned.first.click()
            val selectedChinese = originalCandidate.substringBefore("，英文释义：")
            driver.expectText(selectedChinese)
            check("Paging forward and back commits the current candidate once", currentText() == selectedChinese)

            driver.launch()
            driver.type("shi")
            val strip = device.wait(Until.findObject(By.res("candidate_scroll")), 5000)!!.visibleBounds
            device.swipe(strip.right - 12, strip.centerY(), strip.left + 12, strip.centerY(), 24)
            device.waitForIdle()
            // Android's compact candidate strip now contains nine entries.
            val last = candidateAt(8)
            assertTrue("The final candidate is reachable inside the horizontal viewport", strip.contains(last.first.visibleCenter.x, last.first.visibleCenter.y))
            val lastChinese = last.second.substringBefore("，英文释义：")
            last.first.click()
            driver.expectText(lastChinese)
            check("Horizontal scrolling exposes and commits the final candidate once", currentText() == lastChinese)

            driver.launch("email")
            val alphabet = "qwertyuiopasdfghjklzxcvbnm"
            driver.type(alphabet, delayMs = 0)
            driver.expectText(alphabet)
            check("Rapid adjacent key sequence has no omissions or duplicates", currentText() == alphabet)
            val beforePss = Debug.getPss()
            repeat(15) {
                device.pressBack()
                driver.editor().click()
                driver.key("g")
            }
            check("Fifteen keyboard reopen cycles retain text and active keys", currentText() == alphabet && driver.key("enter").isEnabled)
            report.put("sameProcessPssKbBeforeReopen", beforePss).put("sameProcessPssKbAfterReopen", Debug.getPss())

            device.pressHome()
            driver.context.startActivity(Intent(driver.context, ProbeActivity::class.java)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_REORDER_TO_FRONT))
            driver.editor().click()
            driver.key("g")
            check("Returning from background preserves editor text", currentText() == alphabet)
            if (driver.imePackage != driver.context.packageName) {
                device.executeShellCommand("am force-stop ${driver.imePackage}")
                driver.rebind()
                driver.editor().click()
                driver.key("g")
                editorAction { _, view -> view.setSelection(view.text.length) }
                driver.type("a")
                driver.expectText(alphabet + "a")
                check("Optimized IME process can be recreated and type again", currentText() == alphabet + "a")
            }
            report.put("passed", true)
        } finally {
            if (!report.optBoolean("passed")) driver.capture("lifecycle", "failure")
            device.setOrientationNatural()
            device.unfreezeRotation()
            File(driver.context.filesDir, "lifecycle-report.json").writeText(report.toString(2))
        }
    }
}
