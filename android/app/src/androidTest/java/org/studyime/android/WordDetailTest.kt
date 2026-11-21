// SPDX-License-Identifier: GPL-3.0-or-later
package org.studyime.android

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
import org.studyime.android.settings.KeyboardSkin
import org.studyime.android.settings.Preferences

@RunWith(AndroidJUnit4::class)
class WordDetailTest {
    @Test fun offlineSensesPreserveKeyboardAndEnglishAction() {
        val d = ImeDriver()
        val ui = d.device
        val prefs = Preferences.get(d.context)
        val original = prefs.state.value
        val font = ui.executeShellCommand("settings get system font_scale").trim()
        val checks = JSONArray()
        val report = JSONObject().put("checks", checks).put("scope", "Real Android IME word details and local APK examples")
        fun check(name: String, ok: Boolean) {
            checks.put(JSONObject().put("name", name).put("passed", ok))
            assertTrue(name, ok)
        }
        fun panel() = ui.wait(Until.findObject(By.res("definition_panel")), 6000) ?: error("Missing word detail")
        fun close() {
            ui.findObject(By.desc("关闭释义")).click()
            check("Close removes the floating card", ui.wait(Until.gone(By.res("definition_panel")), 5000))
        }
        try {
            ui.setOrientationNatural()
            ui.executeShellCommand("wm density 320")
            ui.executeShellCommand("wm size 780x1800")
            ui.executeShellCommand("settings put system font_scale 1.0")
            prefs.update { it.copy(skin = KeyboardSkin.SOFT_POP, textScale = 1f, keyHeight = 1f, userLearning = false) }
            d.launch("send")
            d.type("jiejue")
            val before = d.editor().text
            val candidateBounds = d.candidate("解决").visibleBounds
            val keys = listOf("q", "details", "enter").associateWith(d::keyCenter)
            d.tapKey("details")
            val light = panel()
            val solve = light.findObject(By.text("solve"))
            val settle = light.findObject(By.text("settle"))
            check("Default sense precedes the alternative", solve != null && settle != null &&
                solve.visibleBounds.top < settle.visibleBounds.top && light.hasObject(By.text("动词 · 默认")))
            check("Both bilingual examples and the reading appear without scrolling", listOf("jiějué", "We need to solve this problem.",
                "我们需要解决这个问题。", "They met to settle the dispute.", "他们见面解决这场纠纷。").all { light.hasObject(By.text(it)) })
            check("Each sense shows its own collocation", light.hasObject(By.textContains("solve a problem")) &&
                light.hasObject(By.textContains("settle a dispute")))
            check("Portrait card sits above the candidate strip and does not move the keys", light.visibleBounds.bottom <= candidateBounds.top &&
                keys.all { (id, center) -> d.keyCenter(id) == center })
            check("Opening details leaves the editor unchanged", before.isNotEmpty() && d.editor().text == before)
            d.capture("word-details", "soft-pop-light-solve")
            close()
            d.expectText(before)
            d.tapKey("details")
            val reopened = panel()
            check("The commit button names the existing default", reopened.hasObject(By.text("输入 solve")))
            reopened.findObject(By.res("commit_english")).click()
            d.expectText("solve")
            check("The action commits only the existing default", d.editor().text == "solve")

            d.launch("send", theme = "dark")
            d.type("jiejue")
            d.candidate("解决").longClick()
            check("Long press exposes the same senses", panel().hasObject(By.text("settle")))
            d.capture("word-details", "soft-pop-dark-solve")
            close()
            d.toggleEnglish()
            d.tapKey("details")
            val hidden = panel()
            check("Hidden English leaves only the word and forget action", hidden.hasObject(By.res("forget_candidate")) &&
                !hidden.hasObject(By.res("commit_english")) && !hidden.hasObject(By.text("settle")) && !hidden.hasObject(By.text("jiějué")))
            close()

            ui.executeShellCommand("wm size 640x1688")
            ui.executeShellCommand("settings put system font_scale 2.0")
            d.launch()
            d.type("lianxi")
            d.candidate("联系").longClick()
            val large = panel()
            val senses = large.findObject(By.res("definition_senses"))
            val action = large.findObject(By.res("commit_english"))
            val forget = large.findObject(By.res("forget_candidate"))
            val fixed = listOf(action.visibleBounds, forget.visibleBounds)
            check("At large type sizes the sense list scrolls and both actions remain tappable", senses.isScrollable &&
                fixed.all { it.height() >= 96 } && large.hasObject(By.desc("关闭释义")))
            senses.scroll(Direction.DOWN, .8f)
            check("Scrolling the senses does not scroll the actions", fixed == listOf(action.visibleBounds, forget.visibleBounds))
            d.capture("word-details", "soft-pop-narrow-large-type")
            close()
            report.put("passed", true)
        } finally {
            if (!report.optBoolean("passed")) runCatching { d.capture("word-details", "failure") }
            File(d.context.filesDir, "word-detail-report.json").writeText(report.toString(2))
            ui.unfreezeRotation()
            ui.executeShellCommand("wm size reset")
            ui.executeShellCommand("wm density reset")
            ui.executeShellCommand(if (font == "null") "settings delete system font_scale" else "settings put system font_scale $font")
            prefs.update { original }
        }
    }
}
