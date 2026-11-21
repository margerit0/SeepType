// SPDX-License-Identifier: GPL-3.0-or-later
package org.studyime.android

import android.os.SystemClock
import android.view.ViewConfiguration
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.uiautomator.By
import androidx.test.uiautomator.Until
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class ShiftInputTest {
    @Test fun shiftPreservesChineseModeAndLocksOnDoubleTap() {
        val d = ImeDriver()
        d.launch()
        fun pickPark() {
            d.type("gongyuan", delayMs = 0)
            d.candidate("公园").click()
        }

        d.type("gongyuan", delayMs = 0)
        d.tapKey("shift")
        d.expectText("gong yuan")
        d.tapKey("q")
        d.expectText("公园Q")
        pickPark()
        d.expectText("公园Q公园")

        d.tapKey("shift")
        SystemClock.sleep(ViewConfiguration.getDoubleTapTimeout().toLong())
        d.tapKey("shift")
        pickPark()
        d.expectText("公园Q公园公园")

        // Reuse the hit point so accessibility lookups do not delay the double tap.
        val shift = d.keyCenter("shift")
        assertTrue(d.device.click(shift.x, shift.y))
        assertTrue(d.device.click(shift.x, shift.y))
        assertTrue("Shift indicates caps lock", d.device.wait(Until.hasObject(By.desc("解除大写锁定")), 8000))
        d.tapKey("q")
        d.tapKey("w")
        d.expectText("公园Q公园公园QW")
        d.tapKey("shift")
        pickPark()
        d.expectText("公园Q公园公园QW公园")
    }
}
