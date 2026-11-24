// SPDX-License-Identifier: GPL-3.0-or-later
package org.studyime.android

import android.content.res.Configuration
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.width
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsNotDisplayed
import androidx.compose.ui.test.getUnclippedBoundsInRoot
import androidx.compose.ui.test.hasAnyAncestor
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.unit.Density
import androidx.compose.ui.unit.DpRect
import androidx.compose.ui.unit.dp
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.studyime.android.clipboard.ClipboardHistoryState
import org.studyime.android.engine.Candidate
import org.studyime.android.engine.EngineSnapshot
import org.studyime.android.ime.EditorSpec
import org.studyime.android.settings.KeyboardPreferences
import org.studyime.android.settings.KeyboardSkin
import org.studyime.android.ui.StudyKeyboard
import org.studyime.android.ui.StudyTheme

private val DpRect.width get() = right - left
private val DpRect.height get() = bottom - top

class CandidateWidthTest {
    @get:Rule val compose = createComposeRule()

    private val prefs = KeyboardPreferences(skin = KeyboardSkin.SOFT_POP)
    private val state = mutableStateOf(EngineSnapshot(ready = true))
    private val events = mutableListOf<JSONObject>()

    private fun showKeyboard(width: Int) {
        compose.setContent {
            val configuration = Configuration(LocalConfiguration.current).apply {
                screenWidthDp = width
                screenHeightDp = 700
            }
            CompositionLocalProvider(
                LocalConfiguration provides configuration,
                LocalDensity provides Density(LocalDensity.current.density, fontScale = 1f),
            ) {
                Box(Modifier.width(width.dp)) {
                    StudyTheme(skin = prefs.skin) {
                        StudyKeyboard(state.value, prefs, EditorSpec(), {}, { events.add(it) }, {}, {}, {},
                            onPickEmoji = { _, _ -> }, clipboard = ClipboardHistoryState(), onClipboardEnabled = {}, onPasteClipboard = { _, _ -> },
                            onPinClipboard = {}, onDeleteClipboard = {}, onClearClipboard = {})
                    }
                }
            }
        }
    }

    @Test fun compactStripFitsShortWordsAndScrollsToLongOnes() {
        showKeyboard(390)
        val key = compose.onNodeWithTag("key_q")
        val idleKey = key.getUnclippedBoundsInRoot()
        val initial = EngineSnapshot(ready = true, input = "shi", revision = 1,
            candidates = List(6) { Candidate("公园", "park") } + listOf(
                Candidate("一件意想不到的事", ""),
                Candidate("保持", "keep it going over time"),
            ))
        compose.runOnIdle { state.value = initial }
        val strip = compose.onNodeWithTag("candidate_scroll").getUnclippedBoundsInRoot()
        val tool = compose.onNodeWithContentDescription("展开候选")
        val toolBounds = tool.getUnclippedBoundsInRoot()
        val short = compose.onNodeWithTag("candidate_0")
        val sixth = compose.onNodeWithTag("candidate_5")
        val longChinese = compose.onNodeWithTag("candidate_6")
        val longEnglish = compose.onNodeWithTag("candidate_7")
        assertTrue(sixth.getUnclippedBoundsInRoot().right <= strip.right)
        assertTrue(longChinese.getUnclippedBoundsInRoot().width >= short.getUnclippedBoundsInRoot().width * 2)
        assertTrue(longEnglish.getUnclippedBoundsInRoot().width > short.getUnclippedBoundsInRoot().width)
        longEnglish.assertIsNotDisplayed()
        longEnglish.performScrollTo().assertIsDisplayed()
        assertTrue(longEnglish.getUnclippedBoundsInRoot().right <= strip.right + 1.dp)
        assertEquals(toolBounds, tool.getUnclippedBoundsInRoot())
        assertEquals(idleKey, key.getUnclippedBoundsInRoot())
        longEnglish.performClick()
        compose.runOnIdle {
            assertEquals("select", events.single().getString("type"))
            assertEquals(7, events.single().getInt("index"))
            assertEquals(1L, events.single().getLong("revision"))
            state.value = initial.copy(input = "shijie", revision = 2, showEnglish = false)
        }
        short.assertIsDisplayed()
        assertEquals(short.getUnclippedBoundsInRoot().width, longEnglish.getUnclippedBoundsInRoot().width)
    }

    @Test fun expandedPanelWrapsWordsWiderThanTheScreen() {
        val phrase = "不积跬步无以至千里不积小流无以成江海".repeat(2)
        state.value = EngineSnapshot(ready = true, showEnglish = false,
            candidates = listOf(Candidate(phrase, ""), Candidate("公园", "")))
        showKeyboard(320)
        val stripTag = hasTestTag("candidate_scroll")
        val insideStrip = hasAnyAncestor(stripTag)
        val stripWidth = compose.onNode(stripTag).getUnclippedBoundsInRoot().width
        val compact = compose.onNode(hasTestTag("candidate_0") and insideStrip).getUnclippedBoundsInRoot()
        assertTrue(compact.width > stripWidth)
        compose.onNodeWithContentDescription("展开候选").performClick()
        val expanded = compose.onNode(hasTestTag("candidate_0") and !insideStrip).assertIsDisplayed()
            .getUnclippedBoundsInRoot()
        val next = compose.onNode(hasTestTag("candidate_1") and !insideStrip).getUnclippedBoundsInRoot()
        assertTrue(expanded.width <= 320.dp)
        assertTrue(expanded.height > compact.height)
        assertTrue(next.top >= expanded.bottom)
    }

    @Test fun newInputStartsCollapsedAfterSelectingFromExpandedCandidates() {
        val initial = EngineSnapshot(ready = true, generation = 1, revision = 1, input = "nihao",
            candidates = listOf(Candidate("你好", "hello")))
        state.value = initial
        showKeyboard(320)
        val expand = compose.onNodeWithContentDescription("展开候选")
        val collapse = compose.onNodeWithContentDescription("收起候选")
        val keyboardKey = compose.onNodeWithTag("key_q")
        expand.performClick()
        collapse.assertIsDisplayed()

        compose.runOnIdle { state.value = initial.copy(revision = 2, page = 1) }
        collapse.assertIsDisplayed()
        val insideStrip = hasAnyAncestor(hasTestTag("candidate_scroll"))
        compose.onNode(hasTestTag("candidate_0") and !insideStrip).performClick()
        compose.runOnIdle {
            assertEquals("select", events.single().getString("type"))
            state.value = initial.copy(revision = 3, input = "", page = 0, candidates = emptyList())
        }
        keyboardKey.assertIsDisplayed()

        compose.runOnIdle {
            state.value = initial.copy(revision = 4, input = "shi", candidates = listOf(Candidate("是", "to be")))
        }
        expand.assertIsDisplayed()
        keyboardKey.assertIsDisplayed()
    }
}
