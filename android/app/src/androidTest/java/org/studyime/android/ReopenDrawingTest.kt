// SPDX-License-Identifier: GPL-3.0-or-later
package org.studyime.android

import android.os.SystemClock
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.By
import androidx.test.uiautomator.Until
import java.io.File
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

/** Reopen the same ready composition without changing its text or settings. */
@RunWith(AndroidJUnit4::class)
class ReopenDrawingTest {
    @Test fun unchangedKeyboardRecordsEveryReopening() {
        val d = ImeDriver()
        val ui = d.device
        val openings = JSONArray()
        val output = File(d.context.filesDir, "reopen").apply { mkdirs() }
        val artifactNames = listOf("failure.png", "failure.xml")
        artifactNames.forEach { File(output, it).delete() }
        val report = JSONObject().put("runId", InstrumentationRegistry.getArguments().getString("evidenceRunId"))
            .put("reopenings", openings).put("requestedReopenings", 40).put("passed", false)
        fun metrics(reset: Boolean = false): JSONObject {
            val text = ui.executeShellCommand("dumpsys activity service ${d.component} study-metrics${if (reset) "-reset" else ""}")
            val line = text.lineSequence().first { it.trim().startsWith("{\"boundary\"") }
            return JSONObject(line.trim())
        }
        try {
            d.launch()
            d.type("nihao")
            d.tapKey("space")
            d.expectText("你好")
            val pid = ui.executeShellCommand("pidof ${d.imePackage}").trim()
            report.put("initialImePid", pid)
            metrics(reset = true)
            repeat(40) { index ->
                ui.pressBack()
                assertTrue("Keyboard is hidden", ui.wait(Until.gone(By.res("study_keyboard")), 5000))
                d.editor().click()
                d.key("g")
                val deadline = SystemClock.uptimeMillis() + 5000
                var state: JSONObject
                do {
                    SystemClock.sleep(40)
                    state = metrics()
                } while ((state.getInt("showRequests") < index + 1 || state.getBoolean("pendingReadyDraw")) &&
                    SystemClock.uptimeMillis() < deadline)
                openings.put(JSONObject().put("iteration", index + 1)
                    .put("showRequests", state.getInt("showRequests"))
                    .put("readyDraws", state.getJSONObject("showInputViewToReadyDrawMs").getInt("samples"))
                    .put("pendingReadyDraw", state.getBoolean("pendingReadyDraw")))
                assertEquals("Each show callback has a recorded draw", index + 1,
                    state.getJSONObject("showInputViewToReadyDrawMs").getInt("samples"))
                assertEquals("One request per reopening", index + 1, state.getInt("showRequests"))
                assertFalse("An unchanged keyboard still records its reopening draw", state.getBoolean("pendingReadyDraw"))
            }
            report.put("finalImePid", ui.executeShellCommand("pidof ${d.imePackage}").trim())
            assertEquals("The IME process remains alive", pid, report.getString("finalImePid"))
            d.expectText("你好")
            report.put("timings", metrics()).put("passed", true)
        } catch (failure: Throwable) {
            report.put("failure", failure.toString()).put("failureTimings", runCatching { metrics() }.getOrNull())
            runCatching { d.capture("reopen", "failure") }.onFailure { failure.addSuppressed(it) }
            throw failure
        } finally {
            report.put("artifacts", JSONArray(artifactNames.filter { File(output, it).isFile }))
            File(d.context.filesDir, "reopen-drawing-report.json").writeText(report.toString(2))
        }
    }
}
