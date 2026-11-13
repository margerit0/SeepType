// SPDX-License-Identifier: GPL-3.0-or-later
package org.studyime.android.settings

/** Stored separately from light/dark appearance and from engine configuration. */
enum class KeyboardSkin(val id: String, val title: String) {
    DEFAULT("default", "默认"),
    SOFT_POP("soft-pop", "轻彩");

    companion object {
        fun fromId(id: String?): KeyboardSkin = entries.firstOrNull { it.id == id } ?: DEFAULT
    }
}
