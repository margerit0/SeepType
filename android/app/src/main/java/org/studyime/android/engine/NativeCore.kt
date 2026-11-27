// SPDX-License-Identifier: GPL-3.0-or-later
package org.studyime.android.engine

import org.studyime.android.diagnostics.StartupTimings
import org.studyime.android.diagnostics.StartupTimings.Phase

object NativeCore {
    init {
        StartupTimings.measure(Phase.NATIVE_LIBRARIES) {
            System.loadLibrary("study_rime")
            System.loadLibrary("study_android")
        }
    }
    fun ensureLoaded() = Unit
    external fun create(shared: String, user: String, build: String): Long
    external fun dispatch(handle: Long, event: String): String
    external fun destroy(handle: Long)
    external fun exportWordFrequency(handle: Long, output: String): Int
    external fun importWordFrequency(handle: Long, input: String): Int
    external fun version(handle: Long): String
}
