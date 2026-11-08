package org.studyime.android.ime

import org.junit.Assert.*
import org.junit.Test

class DeliveryGateTest {
    @Test fun lateResultsCannotWriteToNewEditor() {
        val gate = DeliveryGate()
        gate.bind(1)
        gate.bind(2)
        assertFalse(gate.accept(1, 90))
        assertTrue(gate.accept(2, 2))
        assertFalse(gate.accept(2, 1))
    }
    @Test fun duplicateAndUncertainCommitsAreNeverRetried() {
        val gate = DeliveryGate()
        gate.bind(1)
        var attempts = 0
        assertTrue(gate.consume(1) { attempts++; true })
        assertTrue(gate.consume(1) { attempts++; true })
        assertFalse(gate.consume(2) { attempts++; false })
        assertFalse(gate.consume(2) { attempts++; true })
        assertEquals(2, attempts)
    }
    @Test fun exceptionInvalidatesConnectionBeforeAnotherCommandCanRun() {
        val gate = DeliveryGate()
        gate.bind(1)
        assertFalse(gate.consume(1) { throw IllegalStateException("lost connection") })
        assertFalse(gate.accept(1, 20))
    }
}
