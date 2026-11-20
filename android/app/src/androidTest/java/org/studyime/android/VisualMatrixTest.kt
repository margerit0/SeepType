// SPDX-License-Identifier: GPL-3.0-or-later
package org.studyime.android

import android.content.Intent
import android.os.Build
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
import org.studyime.android.settings.Preferences

@RunWith(AndroidJUnit4::class)
class VisualMatrixTest {
    @Test fun widthsFontsThemesAndLandscape() {
        val driver = ImeDriver()
        val device = driver.device
        val prefs = Preferences.get(driver.context)
        val original = prefs.state.value
        val originalFont = device.executeShellCommand("settings get system font_scale").trim().ifEmpty { "1.0" }
        val checks = JSONArray()
        val captures = JSONArray()
        val report = JSONObject().put("fingerprint", Build.FINGERPRINT).put("scope", "Real native screenshots and touch bounds; image review is separate from structural assertions")
            .put("checks", checks).put("captures", captures)
        fun check(name: String, value: Boolean) { checks.put(JSONObject().put("name", name).put("passed", value)); assertTrue(name, value) }
        fun capture(name: String) { driver.capture("visual", name); captures.put(name + ".png") }
        try {
            device.setOrientationNatural()
            device.executeShellCommand("wm density 320")
            for (width in listOf(320, 360, 390, 430)) {
                device.executeShellCommand("wm size ${width * 2}x1688")
                for (font in listOf(1.0f, 1.3f, 1.5f, 2.0f)) {
                    device.executeShellCommand("settings put system font_scale $font")
                    for (theme in listOf("light", "dark")) {
                        val name = "${width}dp-font${font}-$theme"
                        prefs.update { it.copy(keyHeight = 1f, textScale = 1f, reduceMotion = false) }
                        driver.launch(theme = theme)
                        if (name == "320dp-font1.0-light") capture("$name-idle")
                        driver.type("gongyuan")
                        driver.candidate("公园")
                        val bounds = "qwertyuiopasdfghjklzxcvbnm".map { driver.key(it.toString()).visibleBounds }
                        val bottom = driver.key("enter").visibleBounds
                        check("$name exposes every key within the window", bounds.all { it.width() > 0 && it.height() > 0 && it.left >= 0 && it.right <= device.displayWidth } && bottom.bottom <= device.displayHeight)
                        capture(name)
                        if (width == 320 && font == 2f) {
                            driver.candidate("公园").longClick()
                            check("$name opens an accessible definition", device.wait(Until.hasObject(By.text("输入英文")), 8000))
                            capture("$name-definition")
                            device.findObject(By.desc("关闭释义")).click()
                        }
                        android.util.Log.i("StudyVerification", "Captured native $name")
                    }
                }
            }
            device.executeShellCommand("wm size 780x1688")
            device.executeShellCommand("settings put system font_scale 1.0")
            driver.launch()
            driver.type("gongyuan")
            driver.candidate("公园")
            device.findObject(By.desc("展开候选")).click()
            check("Expanded candidates expose paging", device.wait(Until.hasObject(By.desc("下一页候选")), 5000))
            capture("390dp-expanded")
            device.findObject(By.text("返回键盘")).click()
            driver.candidate("公园").longClick()
            capture("390dp-definition")
            device.findObject(By.desc("关闭释义")).click()
            driver.toggleEnglish()
            SystemClock.sleep(350)
            capture("390dp-english-hidden")
            check("English toggle preserves Chinese candidate and visible composition", driver.candidate("公园").contentDescription == "公园" && driver.editor().text == "gong yuan")

            for (font in listOf(1.0f, 2.0f)) {
                device.setOrientationNatural()
                device.executeShellCommand("settings put system font_scale $font")
                driver.launch(theme = "dark")
                device.setOrientationLeft()
                driver.key("g")
                driver.type("gongyuan")
                driver.candidate("公园")
                capture("landscape-font$font")
                check("Landscape font $font keeps bottom actions on screen", driver.key("enter").visibleBounds.bottom <= device.displayHeight)
            }
            device.setOrientationNatural()
            device.executeShellCommand("wm size 640x1688")
            device.executeShellCommand("settings put system font_scale 2.0")
            prefs.update { it.copy(textScale = 1.3f) }
            driver.launch()
            driver.type("gongyuan")
            driver.candidate("公园")
            capture("320dp-system2-user1.3")

            device.executeShellCommand("wm size 780x1688")
            device.executeShellCommand("settings put system font_scale 1.0")
            for (theme in listOf("light", "dark")) {
                prefs.update { it.copy(theme = theme, textScale = 1f, keyHeight = 1f) }
                driver.context.startActivity(Intent(driver.context, MainActivity::class.java).putExtra("screen", "practice")
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK))
                device.wait(Until.findObject(By.res(driver.context.packageName, "practice_editor")), 8000)!!.click()
                driver.key("g")
                driver.type("gongyuan")
                driver.candidate("公园")
                capture("practice-$theme")
            }
            report.put("passed", true)
        } finally {
            if (!report.optBoolean("passed")) driver.capture("visual", "failure")
            device.setOrientationNatural()
            device.unfreezeRotation()
            device.executeShellCommand("wm size reset")
            device.executeShellCommand("wm density reset")
            device.executeShellCommand("settings put system font_scale $originalFont")
            prefs.update { original }
            File(driver.context.filesDir, "visual-matrix-report.json").writeText(report.toString(2))
        }
    }
}
