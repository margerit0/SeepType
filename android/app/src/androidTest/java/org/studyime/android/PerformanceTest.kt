// SPDX-License-Identifier: GPL-3.0-or-later
package org.studyime.android

import android.os.Build
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

@RunWith(AndroidJUnit4::class)
class PerformanceTest {
    @Test fun optimizedImeDrawAndMemoryBaseline() {
        val d = ImeDriver()
        val ui = d.device
        val output = File(d.context.filesDir, "performance").apply { mkdirs() }
        val artifactNames = listOf("memory-before.txt", "memory-after.txt", "gfxinfo.txt", "failure.png", "failure.xml")
        artifactNames.forEach { File(output, it).delete() }
        val report = JSONObject().put("fingerprint", Build.FINGERPRINT).put("imePackage", d.imePackage)
            .put("runId", InstrumentationRegistry.getArguments().getString("evidenceRunId"))
            .put("scope", "Sequential real touch events, optimized IME when imePackage is release; callback to Compose draw, excludes physical display timings")
        val observations = JSONArray()
        val reopenings = JSONArray()
        report.put("reopeningObservations", reopenings)
        fun metrics(reset: Boolean = false): JSONObject {
            val value = ui.executeShellCommand("dumpsys activity service ${d.component} study-metrics${if (reset) "-reset" else ""}")
            val json = value.lineSequence().firstOrNull { it.trim().startsWith("{\"boundary\"") } ?: error("Missing timing-only service report: $value")
            return JSONObject(json.trim())
        }
        try {
            d.launch()
            d.type("nihao")
            d.tapKey("space")
            d.expectText("nihao")
            report.put("initialServiceTimings", metrics())
            val initialPid = ui.executeShellCommand("pidof ${d.imePackage}").trim()
            assertTrue("The measured IME has one live process", initialPid.matches(Regex("[0-9]+")))
            report.put("initialImePid", initialPid)
            val initialMemory = ui.executeShellCommand("dumpsys meminfo ${d.imePackage}")
            File(output, "memory-before.txt").writeText(initialMemory)
            metrics(reset = true)
            // Warm state; no asset deployment, builds or host screenshot work
            // is performed while measuring this series.
            repeat(30) { iteration ->
                d.type("nihao")
                d.tapKey("space")
                val text = d.editor().text
                observations.put(JSONObject().put("iteration", iteration + 1).put("syntheticEditorText", text))
                assertEquals("Every raw pinyin spelling is committed once and in order", "nihao".repeat(iteration + 2), text)
            }
            report.put("syntheticWordObservations", observations)
            report.put("syntheticFinalText", d.editor().text)
            d.expectText("nihao".repeat(31))
            repeat(20) { iteration ->
                ui.pressBack()
                assertTrue("The keyboard is fully hidden before the next reopening", ui.wait(Until.gone(By.res("study_keyboard")), 5000))
                d.editor().click()
                d.key("g")
                // Accessibility can expose the returning window before it is
                // drawn. Wait for that draw before hiding it again, so a slow
                // reopening cannot be overwritten by the following request.
                val deadline = SystemClock.uptimeMillis() + 5000
                var opening: JSONObject
                var complete: Boolean
                do {
                    SystemClock.sleep(40)
                    opening = metrics()
                    complete = opening.getInt("showRequests") >= iteration + 1 &&
                        opening.getJSONObject("showInputViewToReadyDrawMs").getInt("samples") == opening.getInt("showRequests") &&
                        !opening.getBoolean("pendingReadyDraw")
                } while (!complete && SystemClock.uptimeMillis() < deadline)
                reopenings.put(JSONObject().put("iteration", iteration + 1).put("showRequests", opening.getInt("showRequests"))
                    .put("readyDraws", opening.getJSONObject("showInputViewToReadyDrawMs").getInt("samples"))
                    .put("pendingReadyDraw", opening.getBoolean("pendingReadyDraw")))
                assertTrue("Reopening ${iteration + 1} completes a ready draw before the next hide", complete)
            }
            val warm = metrics()
            report.put("warmTimings", warm)
            val finalPid = ui.executeShellCommand("pidof ${d.imePackage}").trim()
            report.put("finalImePid", finalPid)
            assertEquals("The measured IME must not crash and restart during input", initialPid, finalPid)
            assertEquals("All 180 delivered keys were measured", 180, warm.getJSONObject("keyToDeliveryMs").getInt("samples"))
            assertEquals("All 180 keys reached a draw", 180, warm.getJSONObject("keyToComposeDrawMs").getInt("samples"))
            assertEquals("Every measured draw has ordered, paired phase timestamps", 0, warm.getInt("invalidPhasePairs"))
            assertEquals("Paired phases cover all 180 keys", 180, warm.getJSONArray("pairedKeySamplesMs").length())
            assertEquals("No measured keys share a later draw", 0, warm.getInt("coalescedKeysBeforeDraw"))
            assertEquals("No measured keys were discarded before drawing", 0, warm.getInt("discardedBeforeDraw"))
            assertEquals("No input remains waiting for a draw", 0, warm.getInt("pendingDraws"))
            assertEquals("All 20 requested reopenings were exercised", 20, warm.getInt("showRequests"))
            assertEquals("All 20 reopenings reached a first draw", 20, warm.getJSONObject("showInputViewToDrawMs").getInt("samples"))
            assertEquals("Every reopening reaches a ready draw", warm.getInt("showRequests"), warm.getJSONObject("showInputViewToReadyDrawMs").getInt("samples"))
            assertFalse("No keyboard reopening remains waiting for a first draw", warm.getBoolean("pendingShowDraw"))
            assertFalse("No keyboard reopening remains waiting for a ready draw", warm.getBoolean("pendingReadyDraw"))
            report.put("candidateDrawP95Target50Ms", warm.getJSONObject("keyToComposeDrawMs").getDouble("p95") <= 50)
            report.put("candidateDrawP99Target100Ms", warm.getJSONObject("keyToComposeDrawMs").getDouble("p99") <= 100)
            report.put("warmReadyP95Target100Ms", warm.getJSONObject("showInputViewToReadyDrawMs").optDouble("p95", Double.POSITIVE_INFINITY) <= 100)
            File(output, "memory-after.txt").writeText(ui.executeShellCommand("dumpsys meminfo ${d.imePackage}"))
            File(output, "gfxinfo.txt").writeText(ui.executeShellCommand("dumpsys gfxinfo ${d.imePackage}"))
            report.put("passed", true)
        } catch (failure: Throwable) {
            report.put("passed", false).put("failure", failure.toString())
                .put("syntheticWordObservations", observations)
                .put("failureTimings", runCatching { metrics() }.getOrNull())
            runCatching { d.capture("performance", "failure") }.onFailure {
                report.put("captureFailure", it.toString())
                failure.addSuppressed(it)
            }
            throw failure
        } finally {
            report.put("artifacts", JSONArray(artifactNames.filter { File(output, it).isFile }))
            File(d.context.filesDir, "performance-report.json").writeText(report.toString(2))
        }
    }
}
