// SPDX-License-Identifier: GPL-3.0-or-later
package org.studyime.android

import android.os.SystemClock
import android.view.WindowManager
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.size
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawWithContent
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.ComposeView
import androidx.compose.ui.unit.dp
import androidx.lifecycle.setViewTreeLifecycleOwner
import androidx.lifecycle.setViewTreeViewModelStoreOwner
import androidx.savedstate.setViewTreeSavedStateRegistryOwner
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import java.io.File
import java.util.concurrent.atomic.AtomicInteger
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.studyime.android.ime.InputMetrics
import org.studyime.android.ime.ImeViewOwner

/** A cached Compose child must observe a new show even if its content is unchanged. */
@RunWith(AndroidJUnit4::class)
class DrawRequestTest {
    @Test fun cachedComposeChildAcknowledgesShow() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val draws = AtomicInteger()
        val report = JSONObject().put("passed", false)
        var view: ComposeView? = null
        var owner: ImeViewOwner? = null
        fun await(condition: () -> Boolean): Boolean {
            val deadline = SystemClock.uptimeMillis() + 3000
            while (!condition() && SystemClock.uptimeMillis() < deadline) SystemClock.sleep(20)
            return condition()
        }
        try {
            ActivityScenario.launch(ProbeActivity::class.java).use { scenario ->
                scenario.onActivity { activity ->
                    // The service first touches metrics from onStartInputView,
                    // before drawing. Keep that initialization order here too.
                    InputMetrics.reset()
                    activity.window.setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_STATE_ALWAYS_HIDDEN)
                    val lifecycle = ImeViewOwner().also { owner = it }
                    activity.window.decorView.apply {
                        setViewTreeLifecycleOwner(lifecycle)
                        setViewTreeViewModelStoreOwner(lifecycle)
                        setViewTreeSavedStateRegistryOwner(lifecycle)
                    }
                    view = ComposeView(activity).apply {
                        setContent {
                            Box(Modifier.size(100.dp).background(Color.Green).drawWithContent {
                                drawContent()
                                draws.incrementAndGet()
                                InputMetrics.frame(0, 0, true)
                            })
                        }
                    }
                    activity.setContentView(view)
                    lifecycle.resume()
                }
                assertTrue("Initial Compose content draws", await { draws.get() > 0 })
                instrumentation.waitForIdleSync()
                SystemClock.sleep(200)
                val initial = draws.get()
                instrumentation.runOnMainSync {
                    InputMetrics.reset()
                    InputMetrics.showRequested()
                    // This is the original IME's parent View invalidation path.
                    view!!.invalidate()
                }
                val acknowledged = await { !JSONObject(InputMetrics.report()).getBoolean("pendingReadyDraw") }
                report.put("drawsBeforeShow", initial).put("drawsAfterShow", draws.get())
                    .put("timings", JSONObject(InputMetrics.report()))
                assertTrue("An unchanged cached Compose child redraws for a new show request", acknowledged)
                assertEquals(1, JSONObject(InputMetrics.report()).getJSONObject("showInputViewToReadyDrawMs").getInt("samples"))
                report.put("passed", true)
            }
        } catch (failure: Throwable) {
            report.put("failure", failure.toString())
            throw failure
        } finally {
            instrumentation.runOnMainSync {
                view?.disposeComposition()
                owner?.destroy()
            }
            File(instrumentation.targetContext.filesDir, "draw-request-report.json").writeText(report.toString(2))
        }
    }
}
