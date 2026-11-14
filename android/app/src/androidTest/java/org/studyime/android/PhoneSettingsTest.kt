// SPDX-License-Identifier: GPL-3.0-or-later
package org.studyime.android

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.By
import androidx.test.uiautomator.Direction
import androidx.test.uiautomator.UiObject2
import java.io.File
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

/** Preserve just the two product preferences exercised by the phone suite. */
@RunWith(AndroidJUnit4::class)
class PhoneSettingsTest {
    @Test fun preserveOrRestore() {
        val d = ImeDriver()
        val args = InstrumentationRegistry.getArguments()
        val source = File(d.context.filesDir, "phone-preferences-original.json")
        val output = File(d.context.filesDir, "phone-settings-report.json")
        val restore = args.getString("phoneSettings") == "restore"
        val report = JSONObject().put("passed", false).put("restoring", restore)
        try {
            d.launch(kind = "private", configure = false)
            d.openQuickSettings()
            fun english(): UiObject2 {
                var node = d.device.findObject(By.res("quick_settings")).findObject(By.desc("显示英文释义"))
                while (!node.isCheckable) node = node.parent ?: error("English toggle is not checkable")
                return node
            }
            fun schemeNode(name: String): UiObject2 {
                var node = d.device.findObject(By.text(name)) ?: error("Missing scheme $name")
                while (!node.isClickable) node = node.parent ?: error("Scheme is not clickable")
                return node
            }
            fun scheme(): String {
                val scroll = d.device.findObject(By.res("quick_settings_scroll"))
                repeat(3) { if (d.device.findObject(By.text("小鹤")) == null) scroll.scroll(Direction.DOWN, .75f) }
                return listOf("全拼", "自然码", "小鹤").single { schemeNode(it).isSelected || schemeNode(it).isChecked }
            }
            if (!restore) {
                check(!source.exists()) { "Preserve existing restoration record" }
                val originalEnglish = english().isChecked
                val originalScheme = scheme()
                source.writeText(JSONObject().put("english", originalEnglish).put("scheme", originalScheme).toString())
                d.closeQuickSettings()
                d.openQuickSettings()
                if (!english().isChecked) english().click()
                d.chooseScheme("全拼")
            } else {
                val original = JSONObject(source.readText())
                if (english().isChecked != original.getBoolean("english")) english().click()
                d.chooseScheme(original.getString("scheme"))
                assertEquals(original.getString("scheme"), scheme())
                d.closeQuickSettings()
                d.openQuickSettings()
                assertEquals(original.getBoolean("english"), english().isChecked)
            }
            d.closeQuickSettings()
            report.put("passed", true)
        } finally { output.writeText(report.toString(2)) }
    }
}
