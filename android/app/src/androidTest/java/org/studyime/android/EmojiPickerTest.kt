// SPDX-License-Identifier: GPL-3.0-or-later
package org.studyime.android

import androidx.emoji2.emojipicker.R as PickerResources
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.uiautomator.By
import androidx.test.uiautomator.BySelector
import androidx.test.uiautomator.Until
import java.io.File
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class EmojiPickerTest {
    @Test fun picksUnicodeAndReturnsToKeyboard() {
        val d = ImeDriver()
        val ui = d.device
        val checks = JSONArray()
        val report = JSONObject().put("passed", false).put("checks", checks)
        val entry = By.desc("表情符号").enabled(true)
        val panel = By.res("emoji_panel")
        val header = By.res(d.imePackage, "emoji_picker_header")
        val body = By.res(d.imePackage, "emoji_picker_body")
        fun check(name: String, passed: Boolean) {
            checks.put(JSONObject().put("name", name).put("passed", passed))
            assertTrue(name, passed)
        }
        fun node(selector: BySelector) = ui.wait(Until.findObject(selector), 8000) ?: error("Missing $selector")
        fun category(id: Int) = node(By.desc(d.context.getString(id)).hasAncestor(header)).click()
        fun glyph(emoji: String) = By.desc(d.context.getString(PickerResources.string.emoji_content_desc, emoji))
        fun open(fromCandidates: Boolean = false) {
            if (fromCandidates) node(By.desc("展开候选")).click()
            node(entry).click()
            check("Emoji grid opens in the keyboard", ui.wait(Until.hasObject(body), 8000))
        }
        fun close() {
            node(By.text("返回键盘")).click()
            check("Returning closes the picker", ui.wait(Until.gone(panel), 5000))
        }
        try {
            d.launch("multiline")
            val menu = node(By.desc("键盘设置")).visibleBounds
            val emoji = node(entry).visibleBounds
            val clipboard = node(By.desc("剪贴板历史")).visibleBounds
            check("Emoji icon is the second tool", menu.right <= emoji.left && emoji.right <= clipboard.left)
            d.capture("emoji", "toolbar")

            d.type("gongyuan")
            d.candidate("公园")
            open(fromCandidates = true)
            close()
            check("Closing without a selection preserves pinyin candidates", d.candidate("公园").isEnabled)
            open(fromCandidates = true)
            category(PickerResources.string.emoji_category_emotions)
            d.capture("emoji", "picker")
            node(glyph("😀")).click()
            d.expectText("公园😀")
            node(glyph("😂")).click()
            d.expectText("公园😀😂")

            category(PickerResources.string.emoji_category_people)
            node(By.descContains("🛀").hasAncestor(body)).longClick()
            node(glyph("🛀🏽").hasAncestor(By.res(d.imePackage, "variant_popup"))).click()
            d.expectText("公园😀😂🛀🏽")
            checks.put(JSONObject().put("name", "Pinyin and complete Unicode emoji delivered in order").put("passed", true))
            close()

            d.tapKey("page")
            val numberLayer = By.res("key_page").desc("字母键盘")
            check("123 page is active", ui.wait(Until.hasObject(numberLayer), 5000))
            open()
            category(PickerResources.string.emoji_category_recent)
            check("Recently used includes the selected skin tone", ui.wait(Until.hasObject(glyph("🛀🏽").hasAncestor(body)), 5000))
            close()
            check("Returning restores the 123 page", ui.wait(Until.hasObject(numberLayer), 5000))

            open()
            ui.pressBack()
            check("System Back hides the keyboard", ui.wait(Until.gone(By.res("study_keyboard")), 5000))
            d.editor().click()
            check("Reopening the keyboard does not restore the old picker", ui.wait(Until.hasObject(numberLayer), 5000))

            open()
            d.editor("probe_other").click()
            check("Switching editors dismisses the old picker", ui.wait(Until.gone(panel), 5000))
            for (kind in listOf("password", "number", "email", "private")) {
                d.launch(kind)
                check("$kind does not offer emoji entry", !ui.hasObject(entry))
            }
            report.put("passed", true)
        } finally {
            File(d.context.filesDir, "emoji-picker-report.json").writeText(report.toString(2))
        }
    }
}
