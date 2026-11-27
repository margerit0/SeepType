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
import org.studyime.android.settings.KeyboardSkin
import org.studyime.android.settings.Preferences

@RunWith(AndroidJUnit4::class)
class ScenarioTest {
    @Test fun homeReflectsKeyboardSwitchWhileOpen() {
        val d = ImeDriver()
        val ui = d.device
        val fallback = ui.executeShellCommand("ime list -s").lineSequence().map(String::trim)
            .first { it.contains("inputmethod.latin") }
        val selected = By.text("拾词正在使用中")
        val unselected = By.text("选择拾词，开始自在输入")

        d.context.startActivity(Intent(d.context, MainActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK))
        assertTrue(ui.wait(Until.hasObject(selected), 8000))
        try {
            ui.executeShellCommand("ime set $fallback")
            assertTrue(ui.wait(Until.hasObject(unselected), 5000))
            ui.executeShellCommand("ime set ${d.component}")
            assertTrue(ui.wait(Until.hasObject(selected), 5000))
        } finally {
            ui.executeShellCommand("ime set ${d.component}")
        }
    }

    @Test fun definitionsGesturesNavigationAndSettings() {
        val d = ImeDriver()
        val ui = d.device
        val prefs = Preferences.get(d.context)
        val original = prefs.state.value
        val checks = JSONArray()
        val report = JSONObject().put("scope", "Native long/missing/partial definitions, gestures, navigation and setup/settings").put("checks", checks)
        fun check(name: String, passed: Boolean) { checks.put(JSONObject().put("name", name).put("passed", passed)); assertTrue(name, passed) }
        fun shot(name: String) = d.capture("scenarios", name)
        try {
            // Exercise symbol navigation using the default skin.
            prefs.update { it.copy(skin = KeyboardSkin.DEFAULT) }
            ui.executeShellCommand("wm density 320")
            ui.executeShellCommand("wm size 640x1688")
            d.launch()
            d.type("meiguanxi")
            d.candidate("没关系").longClick()
            check("Full long definition is exposed independently of candidate ellipsis", ui.wait(Until.hasObject(By.text("it doesn't matter")), 5000))
            shot("long-definition")
            ui.findObject(By.res("commit_english")).click()
            d.expectText("it doesn't matter")

            d.launch()
            d.type("gongyuan")
            d.candidate("公元").longClick()
            check("Missing annotation leaves explicit English action disabled", ui.wait(Until.hasObject(By.text("暂未收录释义")), 5000) &&
                !ui.findObject(By.res("commit_english")).isEnabled)
            shot("missing-definition")
            ui.findObject(By.desc("关闭释义")).click()
            d.candidate("公元").click()
            d.expectText("公元")
            check("Missing English does not block Chinese selection", d.editor().text == "公元")

            d.launch()
            d.type("nihaoma")
            val partial = ui.wait(Until.findObject(By.desc("你好，英文释义：hello")), 5000) ?: error("Missing partial candidate")
            partial.longClick()
            check("Partial composition explains unavailable English action", ui.wait(Until.hasObject(By.text("选完整个词后可输入英文")), 5000) &&
                !ui.findObject(By.res("commit_english")).isEnabled)
            shot("partial-definition")

            d.launch()
            val q = d.key("q").visibleCenter
            ui.swipe(q.x, q.y, q.x, q.y - 320, 8)
            SystemClock.sleep(200)
            check("Dragging out cancels a key press", d.editor().text == "在这里输入" || d.editor().text.isNullOrEmpty())
            d.key("q").longClick()
            d.expectText("1")
            check("Long press emits the secondary digit without the letter", d.editor().text == "1")
            d.launch("email")
            d.type("abcdefgh")
            val deletion = d.key("delete").visibleCenter
            ui.swipe(deletion.x, deletion.y, deletion.x, deletion.y, 45)
            check("Held deletion repeats and stops on release", d.editor().text.length < 7)
            val deleted = d.editor().text
            SystemClock.sleep(200)
            check("Released deletion has no trailing repeat", d.editor().text == deleted)
            d.launch("numberPassword")
            d.type("123")
            check("Numeric passwords keep the protected keyboard state", ui.hasObject(By.text("密码输入 · 不记录选词")))
            d.launch("url")
            d.type("abc")
            d.expectText("abc")
            check("URL editor uses literal English", d.editor().text == "abc")
            d.tapKey("page")
            d.tapKey("symbols")
            d.tapKey("_")
            d.expectText("abc_")
            check("English symbols include a literal underscore", d.editor().text == "abc_")

            d.launch()
            d.type("xi")
            d.tapKey("page")
            d.tapKey("symbols")
            d.tapKey("'")
            d.tapKey("page")
            d.type("an")
            d.candidate("西安").click()
            d.expectText("西安")
            check("Pinyin apostrophe is entered without prematurely committing Chinese", d.editor().text == "西安")

            for (mode in listOf("threebutton", "gestural")) {
                ui.executeShellCommand("cmd overlay enable-exclusive --category com.android.internal.systemui.navbar.$mode")
                d.launch(theme = "dark")
                d.type("gongyuan")
                d.candidate("公园")
                check("$mode navigation leaves bottom keys reachable", d.key("enter").visibleBounds.bottom < ui.displayHeight)
                shot("navigation-$mode")
                d.candidate("公园").click()
                d.expectText("公园")
            }

            // Recheck the corrected definition action footer at maximum system
            // font size. Scrolling applies only to the definition body.
            ui.executeShellCommand("settings put system font_scale 2.0")
            d.launch(theme = "dark")
            d.type("gongyuan")
            d.candidate("公园").longClick()
            shot("large-font-definition-footer")
            check("Large font keeps both definition actions on screen", ui.findObject(By.res("commit_english")).visibleBounds.height() >= 96 &&
                ui.findObject(By.text("忘记这个词的选词习惯")).visibleBounds.bottom < ui.displayHeight)
            ui.executeShellCommand("settings put system font_scale 1.0")
            for (theme in listOf("light", "dark")) {
                for (screen in listOf("home", "settings", "about")) {
                    ui.pressHome()
                    d.instrumentation.runOnMainSync { prefs.update { it.copy(theme = theme) } }
                    d.context.startActivity(Intent(d.context, MainActivity::class.java).putExtra("screen", screen)
                        .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK))
                    assertTrue(ui.wait(Until.hasObject(By.textContains(when (screen) { "settings" -> "拼音方案"; "about" -> "关于拾词"; else -> "顺便拾起一个词" })), 8000))
                    ui.waitForIdle()
                    SystemClock.sleep(200)
                    shot("$screen-$theme")
                }
            }
            report.put("passed", true)
        } finally {
            if (!report.optBoolean("passed")) shot("failure")
            ui.executeShellCommand("cmd overlay enable-exclusive --category com.android.internal.systemui.navbar.threebutton")
            ui.executeShellCommand("settings put system font_scale 1.0")
            ui.executeShellCommand("wm size reset")
            ui.executeShellCommand("wm density reset")
            prefs.update { original }
            File(d.context.filesDir, "scenario-report.json").writeText(report.toString(2))
        }
    }
}
