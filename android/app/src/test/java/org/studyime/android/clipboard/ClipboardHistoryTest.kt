// SPDX-License-Identifier: GPL-3.0-or-later
package org.studyime.android.clipboard

import org.junit.Assert.*
import org.junit.Test

class ClipboardHistoryTest {
    private fun enabled() = ClipboardHistory().setEnabled(true)

    @Test fun recordingIsOptInAndDisablingRemovesPinnedDataToo() {
        assertTrue(ClipboardHistory().record("draft", 1).entries.isEmpty())
        val history = enabled().record("draft", 1)
        val disabled = history.togglePin(history.entries.single().id).setEnabled(false)
        assertFalse(disabled.enabled)
        assertTrue(disabled.entries.isEmpty())
        assertTrue(disabled.record("new", 2).entries.isEmpty())
    }

    @Test fun copiesAreDeduplicatedAndRecencyChangesWithoutLosingThePin() {
        val first = enabled().record("first", 1, 10)
        val id = first.entries.single().id
        val second = first.togglePin(id).record("second", 2, 20).record("first", 3, 30)
        assertEquals(listOf("first", "second"), second.entries.map { it.text })
        assertEquals(id, second.entries.first().id)
        assertTrue(second.entries.first().pinned)
        assertEquals(30L, second.entries.first().copiedAt)
    }

    @Test fun evictionKeepsPinsAndTheMostRecentUnpinnedCopies() {
        var history = enabled().record("keep", 1, 1)
        history = history.togglePin(history.entries.single().id)
        for (index in 2L..80L) history = history.record("copy-$index", index, index)
        assertEquals(50, history.entries.size)
        assertEquals("keep", history.entries.first().text)
        assertEquals("copy-80", history.entries[1].text)
        assertEquals("copy-32", history.entries.last().text)
    }

    @Test fun pinLimitStillAllowsUnpinningAndNewRecords() {
        var history = enabled()
        for (index in 1L..11L) history = history.record("copy-$index", index, index)
        history.entries.take(10).forEach { history = history.togglePin(it.id) }
        val unpinned = history.entries.last()
        assertEquals(history, history.togglePin(unpinned.id))
        history = history.togglePin(history.entries.first().id).togglePin(unpinned.id)
        assertTrue(history.entries.first { it.id == unpinned.id }.pinned)
        assertEquals(10, history.entries.count { it.pinned })
        assertEquals(12, history.record("another", 12, 12).entries.size)
    }

    @Test fun deletingOrClearingDoesNotImportTheUnchangedSystemClipboardAgain() {
        val first = enabled().record("copied", 42, 1)
        for (cleared in listOf(first.clear(), first.remove(first.entries.single().id))) {
            assertEquals(cleared, cleared.record("copied", 42, 2))
            assertTrue(cleared.entries.isEmpty())
            assertEquals("copied", cleared.record("copied", 43, 3).entries.single().text)
        }
    }

    @Test fun ignoredProtectedVersionCannotBeImportedWhenReturningToANormalEditor() {
        val history = enabled().record("ordinary", 1, 1).ignore(2)
        assertEquals(history, history.record("private", 2, 2))
        assertEquals(listOf("next", "ordinary"), history.record("next", 3, 3).entries.map { it.text })
    }

    @Test fun differentTextCopiedInTheSameMillisecondIsNotLost() {
        val history = enabled().record("one", 1, 1).record("two", 1, 2)
        assertEquals(listOf("two", "one"), history.entries.map { it.text })
    }

    @Test fun textPreservesWhitespaceNewlinesAndEmojiWithoutTruncation() {
        val text = "  第一行\nsecond line 🐈\t "
        assertEquals(text, enabled().record(text, 1).entries.single().text)
        assertFalse(ClipboardHistory.accepts(" \n\t"))
        assertFalse(ClipboardHistory.accepts("before\u0000after"))
        assertFalse(ClipboardHistory.accepts("broken\ud83d"))
        assertFalse(ClipboardHistory.accepts("\udc08broken"))
        assertTrue(ClipboardHistory.accepts("a".repeat(4096)))
        assertFalse(ClipboardHistory.accepts("a".repeat(4097)))
        assertTrue(ClipboardHistory.accepts("中".repeat(1365)))
        assertFalse(ClipboardHistory.accepts("中".repeat(1366)))
        assertTrue(ClipboardHistory.accepts("🐈".repeat(1024)))
        assertFalse(ClipboardHistory.accepts("🐈".repeat(1025)))
    }
}
