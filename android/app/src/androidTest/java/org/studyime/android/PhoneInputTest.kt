// SPDX-License-Identifier: GPL-3.0-or-later
package org.studyime.android

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.uiautomator.By
import androidx.test.uiautomator.Until
import java.io.File
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class PhoneInputTest {
    @Test fun threeSchemesAndDefinitionGuards() {
        val d = ImeDriver()
        require(d.privateDevice && d.imePackage != d.context.packageName)
        val ui = d.device
        val checks = JSONArray()
        val report = JSONObject().put("passed", false).put("checks", checks).put("imePackage", d.imePackage)
        fun check(name: String, passed: Boolean) {
            checks.put(JSONObject().put("name", name).put("passed", passed))
            assertTrue(name, passed)
        }
        try {
            for ((schema, park, phrase) in listOf(Triple("全拼", "gongyuan", "qiuzhixin"),
                    Triple("自然码", "gsyr", "qqvixn"), Triple("小鹤", "gsyr", "qqvixb"))) {
                d.launch()
                d.openQuickSettings(); d.chooseScheme(schema); d.closeQuickSettings()
                d.type(park)
                d.candidate("公园").click()
                d.expectText("公园")
                check("$schema Chinese through Release InputConnection", d.editor().text == "公园")
                d.editor().text = ""
                d.type(phrase)
                d.candidate("求职信").longClick()
                val action = ui.wait(Until.findObject(By.res("commit_english")), 5000) ?: error("Missing English action")
                check("$schema explicit English action is enabled", action.isEnabled)
                action.click()
                d.expectText("cover letter")
                check("$schema commits complete phrase once", d.editor().text == "cover letter")
                check("$schema closes consumed definition action", ui.wait(Until.gone(By.res("commit_english")), 5000))
            }
            for ((input, english) in listOf("hai" to "even", "huan" to "return")) {
                d.launch()
                d.type(input)
                d.candidate("还，英文释义：$english").longClick()
                ui.wait(Until.findObject(By.res("commit_english")), 5000)!!.click()
                d.expectText(english)
                check("Reading $input selects correct English through Release UI", d.editor().text == english)
            }
            d.launch()
            d.type("nihaoma")
            d.candidate("你好，英文释义：hello").longClick()
            val disabled = ui.wait(Until.findObject(By.res("commit_english")), 5000)!!
            check("Partial composition disables English", !disabled.isEnabled)
            check("Partial composition explains rejection", ui.hasObject(By.text("选完整个词后可输入英文")))
            ui.findObject(By.desc("关闭释义")).click()
            d.candidate("你好，英文释义：hello").click()
            check("Partial Chinese selection preserves remaining composition", d.editor().text.startsWith("你好") && d.editor().text.contains("ma"))
            d.tapKey("space")
            check("Remaining syllable can still commit", d.editor().text.startsWith("你好") && !d.editor().text.contains("ma"))
            report.put("passed", true)
        } finally {
            File(d.context.filesDir, "phone-input-report.json").writeText(report.toString(2))
        }
    }
}
