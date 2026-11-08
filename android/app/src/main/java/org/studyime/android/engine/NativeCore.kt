// SPDX-License-Identifier: GPL-3.0-or-later
package org.studyime.android.engine

object NativeCore {
    init {
        System.loadLibrary("study_rime")
        System.loadLibrary("study_android")
    }
    external fun create(shared: String, user: String, build: String): Long
    external fun dispatch(handle: Long, event: String): String
    external fun destroy(handle: Long)
    external fun version(handle: Long): String
}
