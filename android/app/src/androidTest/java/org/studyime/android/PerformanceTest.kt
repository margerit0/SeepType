// SPDX-License-Identifier: GPL-3.0-or-later
package org.studyime.android

import android.os.Build
import android.os.SystemClock
import androidx.test.ext.junit.runners.AndroidJUnit4
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
        val report = JSONObject().put("fingerprint", Build.FINGERPRINT).put("imePackage", d.imePackage)
            .put("scope", "Sequential real touch events, optimized IME when imePackage is release; emulator SwiftShader, not physical display timings")
        val observations = JSONArray()
        fun metrics(reset: Boolean = false): JSONObject {
            val value = ui.executeShellCommand("dumpsys activity service ${d.component} study-metrics${if (reset) "-reset" else ""}")
            val json = value.lineSequence().firstOrNull { it.trim().startsWith("{\"boundary\"") } ?: error("Missing timing-only service report: $value")
            return JSONObject(json.trim())
        }
        try {
            d.launch()
            d.type("nihao")
            d.tapKey("space")
            d.expectText("你好")
            report.put("initialServiceTimings", metrics())
            val initialMemory = ui.executeShellCommand("dumpsys meminfo ${d.imePackage}")
            File(output, "memory-before.txt").writeText(initialMemory)
            metrics(reset = true)
            // Warm state; no asset deployment, builds or host screenshot work
            // is performed while measuring this series.
            repeat(30) { iteration ->
                d.type("nihao")
                d.tapKey("space")
                observations.put(JSONObject().put("iteration", iteration + 1).put("syntheticEditorText", d.editor().text))
            }
            report.put("syntheticWordObservations", observations)
            report.put("syntheticFinalText", d.editor().text)
            d.expectText("你好".repeat(31))
            repeat(20) {
                ui.pressBack()
                d.editor().click()
                d.key("g")
                SystemClock.sleep(40)
            }
            val warm = metrics()
            report.put("warmTimings", warm)
            assertTrue("At least 180 delivered keys were measured", warm.getJSONObject("keyToDeliveryMs").getInt("samples") >= 180)
            assertTrue("The visible keyboard was drawn", warm.getJSONObject("keyToComposeDrawMs").getInt("samples") >= 170)
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
            d.capture("performance", "failure")
            throw failure
        } finally {
            File(d.context.filesDir, "performance-report.json").writeText(report.toString(2))
        }
    }
}
