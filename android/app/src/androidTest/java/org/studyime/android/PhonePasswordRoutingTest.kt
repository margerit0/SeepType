// SPDX-License-Identifier: GPL-3.0-or-later
package org.studyime.android

import android.content.Intent
import android.os.SystemClock
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.uiautomator.By
import androidx.test.uiautomator.Until
import java.io.File
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

/** Diagnose routing only inside our empty synthetic password editor. */
@RunWith(AndroidJUnit4::class)
class PhonePasswordRoutingTest {
    @Test fun inspectSyntheticPasswordRouting() = inspect("password", "phone-password-routing.json")
    @Test fun inspectSyntheticPrivateRouting() = inspect("private", "phone-private-routing.json")

    private fun inspect(field: String, filename: String) {
        val d = ImeDriver()
        require(d.privateDevice && d.imePackage != d.context.packageName)
        val report = JSONObject().put("passed", false).put("field", field)
        try {
            val token = SystemClock.elapsedRealtimeNanos()
            d.context.startActivity(Intent(d.context, ProbeActivity::class.java)
                .putExtra("field", field).putExtra("noPersonalization", true).putExtra("launchToken", token)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK))
            assertTrue(d.device.wait(Until.hasObject(By.desc("probe_launch_$token")), 8000))
            d.editor().click()
            report.put("studyKeyboardAvailable", d.device.wait(Until.hasObject(By.res("study_keyboard")), 10_000))
            report.put("letterKeyAvailable", d.device.hasObject(By.res("key_g").enabled(true)))
            report.put("keyguardLocked", d.context.getSystemService(android.app.KeyguardManager::class.java).isKeyguardLocked)
            report.put("defaultIme", d.device.executeShellCommand("settings get secure default_input_method").trim())
            // Keep only keyboard component IDs and booleans, never EditorInfo or text.
            val routing = d.device.executeShellCommand("dumpsys input_method").lineSequence().map(String::trim)
                .filter { it.startsWith("mCurId=") || it.startsWith("mCurMethodId=") ||
                    it.startsWith("mSelectedMethodId=") || it.startsWith("mInputShown=") ||
                    it.startsWith("mShowRequested=") || it.contains("mSecurityInputMethod=") ||
                    it.contains("mInputMethodService=") }
                .map { it.take(500) }.toList()
            report.put("routing", JSONArray(routing))
            val metrics = d.device.executeShellCommand("dumpsys activity service ${d.component} study-metrics")
                .lineSequence().firstOrNull { it.trim().startsWith("{\"boundary\"") }
            if (metrics != null) report.put("studyMetrics", JSONObject(metrics.trim()))
            report.put("passed", true)
        } finally {
            File(d.context.filesDir, filename).writeText(report.toString(2))
        }
    }
}
