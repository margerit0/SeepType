// SPDX-License-Identifier: GPL-3.0-or-later
package org.studyime.android

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.uiautomator.By
import androidx.test.uiautomator.Until
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.studyime.android.settings.Preferences

@RunWith(AndroidJUnit4::class)
class DoublePinyinInteractionTest {
    @Test fun initialsOfferAndCommitNow() {
        val d = ImeDriver()
        val prefs = Preferences.get(d.context)
        val original = prefs.state.value
        try {
            for (scheme in listOf("自然码", "小鹤")) {
                d.launch("private")
                d.openQuickSettings()
                d.chooseScheme(scheme)
                d.closeQuickSettings()
                d.type("xz")
                d.candidate("现在").click()
                d.expectText("现在")
                assertTrue("$scheme finishes the selection", d.device.wait(Until.gone(By.res("candidate_0")), 8000))
            }
        } finally {
            prefs.update { original }
        }
    }
}
