// SPDX-License-Identifier: GPL-3.0-or-later
package org.studyime.android

import android.graphics.Point
import android.os.SystemClock
import android.view.InputDevice
import android.view.MotionEvent
import android.view.inputmethod.EditorInfo
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.uiautomator.By
import androidx.test.uiautomator.Until
import java.io.File
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/** Exercises the real IME window and InputConnection on the isolated development emulator. */
@RunWith(AndroidJUnit4::class)
class NumberPadTest {
    @Test fun nineGridAndOperatorRail() {
        val d = ImeDriver()
        val ui = d.device
        val checks = JSONArray()
        val captures = JSONArray()
        val report = JSONObject().put("checks", checks).put("captures", captures)
            .put("scope", "Nine-grid layout, touch selection and literal input in real Android editors")
        fun check(name: String, passed: Boolean) {
            checks.put(JSONObject().put("name", name).put("passed", passed))
            assertTrue(name, passed)
        }
        fun shot(name: String) {
            d.capture("number-pad", name)
            captures.put("$name.png")
        }
        fun selected(tag: String) = ui.findObject(By.res(tag))?.let { it.isChecked || it.isSelected } == true
        fun choose(skin: String, theme: String) {
            d.openQuickSettings()
            ui.findObject(By.res("skin_$skin")).click()
            ui.findObject(By.res("theme_$theme")).click()
            assertTrue(selected("skin_$skin") && selected("theme_$theme"))
            d.closeQuickSettings()
        }
        val rows = listOf(listOf("1", "2", "3"), listOf("4", "5", "6"), listOf("7", "8", "9"), listOf("comma", "0", "."))
        val operators = listOf("+" to "加号", "-" to "减号", "×" to "乘号", "÷" to "除号", "%" to "百分号")
        val actions = listOf("delete", "symbols", "space", "enter")
        var originalAppearance: Pair<String, String>? = null
        try {
            d.launch("send")
            d.openQuickSettings()
            originalAppearance = listOf("default", "soft-pop").first { selected("skin_$it") } to
                listOf("system", "light", "dark").first { selected("theme_$it") }
            d.closeQuickSettings()
            choose("default", "dark")
            val letterTop = d.keyBounds("q").top
            val letterBottom = d.keyBounds("enter").bottom
            d.tapKey("page")
            val grid = rows.map { row -> row.map { d.keyBounds(it) } }
            val rail = operators.map { (id, _) -> d.keyBounds(id) }
            // Android expands the accessibility bounds of short buttons. The strip itself
            // reports the actual touch area; its five named buttons must be ordered within it.
            val strip = ui.findObject(By.res("operator_rail")).visibleBounds
            val abc = d.keyBounds("page")
            val right = actions.map { d.keyBounds(it) }
            check("Digits form three aligned columns with comma, zero and dot beneath", grid.all { row ->
                row.zipWithNext().all { (l, r) -> l.right == r.left && l.top == r.top && l.bottom == r.bottom }
            } && grid.zipWithNext().all { (a, b) -> a.zip(b).all { (top, bottom) ->
                top.bottom == bottom.top && top.left == bottom.left && top.right == bottom.right
            } })
            check("The left rail spans the first three rows with ABC directly below",
                strip.top == grid.first().first().top && strip.bottom == abc.top && strip.left == abc.left && strip.right == abc.right &&
                    rail.all { it.left == strip.left && it.right == strip.right && strip.contains(it.centerX(), it.centerY()) } &&
                    rail.zipWithNext().all { (a, b) -> a.bottom == b.top } &&
                    abc.right == grid.last().first().left && abc.top == grid.last().first().top && abc.bottom == letterBottom)
            check("Delete, symbols, space and Send align beside 3, 6, 9 and decimal point respectively",
                right.zip(grid).all { (action, row) ->
                    action.left == row.last().right && action.top == row.last().top && action.bottom == row.last().bottom &&
                        action.right == right.first().right
                } && ui.hasObject(By.res("key_enter").desc("发送")))
            check("Switching from letters to numbers keeps the four-row height",
                grid.first().first().top == letterTop && d.keyBounds("enter").bottom == letterBottom)
            check("Each operator has an independent named accessibility button", operators.all { (id, name) ->
                ui.hasObject(By.res("key_$id").desc(name).clickable(true).enabled(true))
            })
            shot("default-dark")
            d.type("1234567890", 0)
            d.tapKey("comma")
            d.tapKey(".")
            var text = "1234567890,."
            d.expectText(text)
            check("Chinese text editor receives every digit and both half-width punctuation marks", d.editor().text == text)
            operators.forEach { (id, _) -> d.tapKey(id) }
            text += "+-×÷%"
            d.expectText(text)
            check("Tapping each operator inserts its literal character", d.editor().text == text)

            val plus = d.keyCenter("+")
            val times = d.keyCenter("×")
            val percent = d.keyCenter("%")
            val outside = d.keyCenter("5")
            withFinger(d, plus) { move ->
                move(MotionEvent.ACTION_MOVE, times)
                shot("default-dark-sliding")
                check("Dragging previews the symbol without entering anything before release", d.editor().text == text)
                move(MotionEvent.ACTION_UP, times)
            }
            text += "×"
            d.expectText(text)
            assertTrue("Injected an upward swipe", ui.swipe(percent.x, percent.y, plus.x, plus.y, 48))
            text += "+"
            d.expectText(text)
            check("Sliding either way inserts only the released symbol", d.editor().text == text)
            withFinger(d, plus) { move ->
                move(MotionEvent.ACTION_MOVE, outside)
                move(MotionEvent.ACTION_MOVE, percent)
                move(MotionEvent.ACTION_UP, percent)
            }
            withFinger(d, plus) { move -> move(MotionEvent.ACTION_CANCEL, plus) }
            withFinger(d, percent) { move ->
                val below = Point(abc.centerX(), abc.centerY())
                move(MotionEvent.ACTION_MOVE, below)
                move(MotionEvent.ACTION_UP, below)
            }
            ui.waitForIdle()
            check("Leaving the rail, lifting on ABC or canceling the pointer does not type or switch pages",
                d.editor().text == text && ui.hasObject(By.res("number_pad")))

            for ((skin, theme) in listOf("default" to "light", "soft-pop" to "light", "soft-pop" to "dark")) {
                choose(skin, theme)
                check("$skin / $theme keeps every pad key in place and retains editor text", rows.indices.all { i ->
                    rows[i].map { d.keyBounds(it) } == grid[i]
                } && operators.map { (id, _) -> d.keyBounds(id) } == rail && actions.map { d.keyBounds(it) } == right &&
                    d.keyBounds("page") == abc && d.editor().text == text)
                shot("$skin-$theme")
            }
            d.tapKey("symbols")
            d.tapKey("@")
            d.tapKey("symbolSet")
            d.tapKey("【")
            d.expectText(text + "@【")
            d.tapKey("symbols")
            d.tapKey("delete")
            d.tapKey("space")
            text += "@ "
            d.expectText(text)
            check("Both symbol sets, numeric return, deletion and space work", d.editor().text == text)
            d.holdKey("delete")
            ui.waitForIdle()
            val afterDelete = d.editor().text.orEmpty()
            check("Holding upper-right Delete removes multiple trailing characters",
                text.startsWith(afterDelete) && afterDelete.length <= text.length - 2)
            d.tapKey("enter")
            check("The bottom-right button dispatches the editor's original Send action", ui.wait(Until.hasObject(
                By.res(d.context.packageName, "probe_action").text("action:${EditorInfo.IME_ACTION_SEND}")), 5000))
            d.tapKey("page")
            check("ABC returns to the letter keyboard", ui.wait(Until.hasObject(By.res("key_q")), 5000))

            d.launch("number")
            check("A signed decimal editor opens directly on the number pad", ui.hasObject(By.res("number_pad")))
            d.tapKey("-")
            d.type("20")
            d.tapKey(".")
            d.type("5")
            d.expectText("-20.5")
            check("Signed decimals reach an Android number editor", d.editor().text == "-20.5")
            report.put("passed", true)
        } finally {
            File(d.context.filesDir, "number-pad-report.json").writeText(report.toString(2))
            originalAppearance?.let { (skin, theme) ->
                if (!ui.hasObject(By.res("key_q"))) d.launch()
                choose(skin, theme)
            }
        }
    }

    // A held pointer lets us check the editor before lifting a finger, not
    // just the final text after a completed swipe.
    private fun withFinger(d: ImeDriver, start: Point, block: ((Int, Point) -> Unit) -> Unit) {
        val downAt = SystemClock.uptimeMillis()
        var held = false
        fun send(action: Int, point: Point) {
            val event = MotionEvent.obtain(downAt, SystemClock.uptimeMillis(), action, point.x.toFloat(), point.y.toFloat(), 0)
            try {
                event.source = InputDevice.SOURCE_TOUCHSCREEN
                assertTrue("Injected touch action $action", d.instrumentation.uiAutomation.injectInputEvent(event, true))
                held = action == MotionEvent.ACTION_DOWN || action == MotionEvent.ACTION_MOVE
                // Give batched moves their own frame, including the pre-release screenshot.
                if (held) SystemClock.sleep(60)
            } finally {
                event.recycle()
            }
        }
        try {
            send(MotionEvent.ACTION_DOWN, start)
            block(::send)
        } finally {
            if (held) send(MotionEvent.ACTION_CANCEL, start)
        }
    }
}
