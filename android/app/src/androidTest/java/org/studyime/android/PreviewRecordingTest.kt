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
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/** Unedited screen recording of the installed app and actual IME touch events. */
@RunWith(AndroidJUnit4::class)
class PreviewRecordingTest {
    @Test fun recordChineseEnglishThemesAndRapidInput() {
        val d = ImeDriver()
        val ui = d.device
        val steps = JSONArray()
        val report = JSONObject().put("imePackage", d.imePackage).put("steps", steps)
            .put("scope", "Unedited Android screenrecord; installed practice editor and real Rime candidates; synthetic local text")
        var recorder = ""
        val recordingHelper = "sh /data/local/tmp/studyime-recording.sh"
        var started = 0L
        fun step(name: String) {
            steps.put(JSONObject().put("name", name).put("elapsedMs", SystemClock.elapsedRealtime() - started))
            SystemClock.sleep(900)
        }
        fun open(screen: String) {
            d.context.startActivity(Intent().setClassName(d.imePackage, "org.studyime.android.MainActivity")
                .putExtra("screen", screen).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK))
        }
        fun expect(text: String) = assertTrue("Practice text: $text",
            ui.wait(Until.hasObject(By.res(d.imePackage, "practice_editor").text(text)), 5000))
        try {
            ui.setOrientationNatural()
            ui.executeShellCommand("wm density 320")
            ui.executeShellCommand("wm size 780x1688")
            ui.executeShellCommand("settings put system font_scale 1.0")
            d.launch()
            open("settings")
            ui.wait(Until.findObject(By.text("浅色")), 8000)!!.click()
            ui.findObject(By.text("全拼")).click()
            open("practice")
            ui.wait(Until.findObject(By.res(d.imePackage, "practice_editor")), 8000)!!.click()
            d.key("g")
            assertTrue("No other screen recording is active", ui.executeShellCommand("pidof screenrecord").isBlank())
            // UiAutomation executes a command directly; shell operators need
            // the explicit helper installed by run_device_checks.py.
            recorder = ui.executeShellCommand("$recordingHelper start").trim()
            assertTrue("Recorder PID is known", recorder.matches(Regex("[0-9]+")))
            started = SystemClock.elapsedRealtime()
            step("Installed practice editor is ready")
            d.type("gongyuan", delayMs = 80)
            if (!d.candidate("公园").contentDescription.contains("英文释义")) {
                d.toggleEnglish()
            }
            assertTrue(ui.wait(Until.hasObject(By.desc("公园，英文释义：park")), 5000))
            step("Light theme shows real bilingual candidates")
            d.capture("recording", "release-light")
            d.candidate("公园").longClick()
            assertTrue(ui.wait(Until.hasObject(By.text("输入英文")), 5000))
            step("Long press opens the complete definition")
            d.capture("recording", "release-definition")
            ui.findObject(By.desc("关闭释义")).click()
            d.candidate("公园").click()
            expect("公园")
            step("Ordinary candidate tap commits Chinese")
            d.type("nihao", delayMs = 80)
            d.candidate("你好").longClick()
            ui.wait(Until.findObject(By.text("输入英文")), 5000)!!.click()
            expect("公园hello")
            step("Explicit English action commits the full dictionary value")
            d.tapKey("enter")
            d.type("gongyuan", delayMs = 60)
            d.candidate("公园")
            d.openQuickSettings()
            ui.findObject(By.res("theme_dark")).click()
            d.closeQuickSettings()
            step("Theme changes during composition")
            d.capture("recording", "release-dark")
            d.toggleEnglish()
            assertTrue(ui.wait(Until.hasObject(By.desc("公园")), 5000))
            expect("公园hello\ngong yuan")
            step("Hiding English retains Chinese and composing text")
            d.toggleEnglish()
            assertTrue(ui.wait(Until.hasObject(By.desc("公园，英文释义：park")), 5000))
            ui.findObject(By.desc("展开候选")).click()
            assertTrue(ui.wait(Until.hasObject(By.desc("下一页候选")), 5000))
            step("Expanded candidates expose page controls")
            d.capture("recording", "release-expanded")
            ui.findObject(By.text("返回键盘")).click()
            d.candidate("公园").click()
            expect("公园hello\n公园")
            d.tapKey("enter")
            val beforeRapid = d.key("h").visibleBounds
            d.type("nihao", delayMs = 0)
            report.put("rapidPreedit", ui.findObject(By.res(d.imePackage, "practice_editor")).text)
            assertTrue("First candidates keep rapid-touch key bounds stable", beforeRapid == d.key("h").visibleBounds)
            d.tapKey("space")
            expect("公园hello\n公园\nnihao")
            step("Rapid touches and space commit the typed pinyin once")
            ui.findObject(By.desc("切换浅深色")).click()
            d.capture("recording", "release-final")
            report.put("passed", true).put("syntheticFinalText", "公园hello\n公园\nnihao")
        } finally {
            if (recorder.matches(Regex("[0-9]+"))) {
                val stopped = ui.executeShellCommand("$recordingHelper stop $recorder").trim()
                if (stopped != "stopped") report.put("passed", false).put("recorderError", stopped)
            }
            if (!report.optBoolean("passed")) d.capture("recording", "failure")
            ui.setOrientationNatural()
            ui.unfreezeRotation()
            ui.executeShellCommand("wm size reset")
            ui.executeShellCommand("wm density reset")
            File(d.context.filesDir, "preview-recording-report.json").writeText(report.toString(2))
        }
    }
}
