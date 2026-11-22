// SPDX-License-Identifier: GPL-3.0-or-later
package org.studyime.android.ui

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class PadOperatorTest {
    @Test fun positionsMapToTheDisplayedSymbolsAndTheirLiteralOutputs() {
        val rows = (0 until 5).map { PadOperator.at(20f, 10f + 20 * it, 40, 100)!! }
        assertEquals(listOf("+", "−", "×", "÷", "%"), rows.map { it.label })
        assertEquals(listOf("+", "-", "×", "÷", "%"), rows.map { it.output })
        assertEquals(PadOperator.MINUS, PadOperator.at(0f, 20f, 40, 100))
        assertEquals(PadOperator.PERCENT, PadOperator.at(39.99f, 99.99f, 40, 100))
    }

    @Test fun leavingAnyEdgeCancelsInsteadOfClampingToAnEndSymbol() {
        for ((x, y) in listOf(-.01f to 20f, 40f to 20f, 10f to -.01f, 10f to 100f)) {
            assertNull(PadOperator.at(x, y, 40, 100))
        }
        assertNull(PadOperator.at(0f, 0f, 0, 0))
    }
}
