// SPDX-License-Identifier: GPL-3.0-or-later
package org.studyime.android

import android.content.Intent
import androidx.test.platform.app.InstrumentationRegistry

/** Give bounded native tests a visible owner without opening an input field. */
object PhoneForeground {
    fun start() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        if (InstrumentationRegistry.getArguments().getString("privateDevice") != "true") return
        val context = instrumentation.targetContext
        context.startActivity(Intent(context, ProbeActivity::class.java).putExtra("nativeVerification", true)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK))
        instrumentation.waitForIdleSync()
    }
}
