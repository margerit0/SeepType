// SPDX-License-Identifier: GPL-3.0-or-later
package org.studyime.android

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.uiautomator.By
import androidx.test.uiautomator.UiObject2
import androidx.test.uiautomator.Until
import java.util.regex.Pattern
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class EnglishCandidateTest {
    private fun ImeDriver.spelling(index: Int, expected: String): UiObject2 {
        return device.wait(Until.findObject(By.res("spelling_candidate_$index").text(expected)), 8000)
            ?: error("Missing spelling $expected. Editor: ${editor().text}. Candidates: " +
                device.findObjects(By.res(Pattern.compile(".*candidate_[0-9]+")))
                    .map { Triple(it.resourceName, it.text, it.contentDescription) })
    }

    @Test fun selectRawSpellingAcrossChineseSchemes() {
        val driver = ImeDriver()
        for (scheme in listOf("全拼", "自然码", "小鹤")) {
            driver.launch()
            driver.openQuickSettings()
            driver.chooseScheme(scheme)
            driver.closeQuickSettings()
            driver.type("home")
            driver.spelling(0, "home").click()
            driver.expectText("home")
            assertTrue(driver.device.wait(Until.gone(By.res("spelling_candidate_0")), 8000))
        }
    }

    @Test fun completeEnglishAndKeepLiteralEmailInput() {
        val driver = ImeDriver()
        driver.launch()
        driver.tapKey("mode")
        driver.type("hom")
        driver.spelling(0, "hom")
        driver.spelling(1, "home").click()
        driver.expectText("home")
        assertTrue(driver.device.wait(Until.gone(By.res("spelling_candidate_0")), 8000))
        driver.tapKey("space")
        driver.tapKey("shift")
        driver.type("hom")
        driver.spelling(1, "Home")
        driver.tapKey("space")
        driver.type("a")
        driver.expectText("home Hom a")

        driver.launch("email")
        driver.type("hom")
        driver.expectText("hom")
        assertTrue(driver.device.wait(Until.gone(By.res("spelling_candidate_0")), 8000))
    }
}
