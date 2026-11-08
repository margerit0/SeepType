// SPDX-License-Identifier: GPL-3.0-or-later
package org.studyime.android.ime

/** A failed/uncertain editor command is consumed before the platform call. */
class DeliveryGate {
    private var generation = 0L
    private var revision = -1L
    private var lastCommand = 0L
    private var valid = false
    fun bind(value: Long) { generation = value; revision = -1; lastCommand = 0; valid = true }
    fun invalidate() { valid = false }
    fun accept(value: Long, version: Long): Boolean {
        if (!valid || value != generation || version < revision) return false
        revision = version
        return true
    }
    fun consume(id: Long, operation: () -> Boolean): Boolean {
        if (!valid || id <= lastCommand) return valid
        lastCommand = id
        val success = runCatching(operation).getOrDefault(false)
        if (!success) valid = false
        return success
    }
}
