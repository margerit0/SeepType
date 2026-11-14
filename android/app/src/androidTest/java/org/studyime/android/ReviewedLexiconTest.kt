// SPDX-License-Identifier: GPL-3.0-or-later
package org.studyime.android

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import java.io.File
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import org.json.JSONArray
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.studyime.android.engine.*
import org.studyime.android.settings.KeyboardPreferences

/** Only packaged synthetic cases and an isolated app-owned dictionary. */
@RunWith(AndroidJUnit4::class)
class ReviewedLexiconTest {
    @Test fun reviewedSnapshotLoadsAndCommitsOnDevice() {
        PhoneForeground.start()
        val worker = Executors.newSingleThreadExecutor()
        try { worker.submit { verifyCases() }.get(15, TimeUnit.MINUTES) }
        finally { worker.shutdownNow() }
    }

    private fun verifyCases() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val root = File(instrumentation.targetContext.noBackupFilesDir, "reviewed-lexicon-smoke")
        val resources = DataDeployer(instrumentation.targetContext, root).prepare()
        val matrix = InstrumentationRegistry.getArguments().getString("lexiconMatrix") ?: "smoke"
        require(matrix in listOf("smoke", "full"))
        val cases = JSONArray(instrumentation.context.assets.open("generated/reviewed-$matrix.json").bufferedReader().use { it.readText() })
        val output = File(instrumentation.targetContext.filesDir, "reviewed-lexicon-smoke.json")
        val handle = NativeCore.create(resources.shared.path, resources.user.path, resources.build.path)
        assertTrue(handle > 0)
        var generation = 0L
        fun send(command: org.json.JSONObject): EngineSnapshot {
            command.put("generation", generation)
            return EngineSnapshot.parse(NativeCore.dispatch(handle, command.toString()))
        }
        val results = JSONArray()
        var failures = 0
        fun save(complete: Boolean) {
            output.writeText(org.json.JSONObject().put("passed", complete && failures == 0)
                .put("matrix", matrix).put("planned", cases.length()).put("checks", results.length())
                .put("failures", failures).put("results", results).put("resourceVersion", resources.version).toString())
        }
        save(false)
        try {
            for (i in 0 until cases.length()) {
                val case = cases.getJSONObject(i)
                val result = org.json.JSONObject(case.toString()).put("index", i)
                try {
                    generation++
                    val started = send(event("start", "config" to KeyboardPreferences(schema = case.getString("schema"), userLearning = false).engineConfig(false, false, false)))
                    assertEquals("Start notice #$i", "", started.notice)
                    assertEquals("Session #$i", generation, started.generation)
                    assertEquals("Schema #$i", case.getString("schema"), started.schema)
                    var value = send(event("clear"))
                    for (char in case.getString("input")) value = send(event("key", "code" to char.code))
                    var index = value.candidates.indexOfFirst { it.chinese == case.getString("chinese") }
                    var pages = 0
                    while (index < 0 && !value.lastPage && pages++ < 100) {
                        value = send(event("page", "backwards" to false, "revision" to value.revision))
                        index = value.candidates.indexOfFirst { it.chinese == case.getString("chinese") }
                    }
                    assertTrue("Missing synthetic candidate #$i", index >= 0)
                    assertEquals("Annotation #$i", case.getString("english"), value.candidates[index].english)
                    val target = send(event("inspect", "index" to index, "revision" to value.revision)).target!!
                    assertEquals("Ready #$i: $case; actual input=${value.input}", "ready", target.reason)
                    assertEquals("Commit #$i", case.getString("english"), send(event("english", "token" to target.token)).commands.single().text)
                    assertTrue("No stale repeat #$i", send(event("english", "token" to target.token)).commands.isEmpty())
                    var chineseValue = send(event("clear"))
                    for (char in case.getString("input")) chineseValue = send(event("key", "code" to char.code))
                    var chineseIndex = chineseValue.candidates.indexOfFirst { it.chinese == case.getString("chinese") }
                    var chinesePages = 0
                    while (chineseIndex < 0 && !chineseValue.lastPage && chinesePages++ < 100) {
                        chineseValue = send(event("page", "backwards" to false, "revision" to chineseValue.revision))
                        chineseIndex = chineseValue.candidates.indexOfFirst { it.chinese == case.getString("chinese") }
                    }
                    assertTrue("Chinese candidate #$i", chineseIndex >= 0)
                    val committed = send(event("select", "index" to chineseIndex, "revision" to chineseValue.revision))
                    assertEquals("Chinese commit #$i", case.getString("chinese"), committed.commands.single().text)
                    assertTrue("Empty composition #$i", committed.input.isEmpty())
                    result.put("passed", true)
                } catch (error: AssertionError) {
                    failures++
                    result.put("passed", false).put("error", error.message)
                } catch (error: Exception) {
                    failures++
                    result.put("passed", false).put("error", error.toString())
                } finally {
                    results.put(result)
                    send(event("clear"))
                    if (results.length() % 30 == 0) {
                        save(false)
                        android.util.Log.i("StudyVerification", "Lexicon: ${results.length()}/${cases.length()}, failures=$failures")
                    }
                }
            }
            save(true)
            assertEquals("Synthetic lexicon failures; see app-owned reviewed-lexicon-smoke.json", 0, failures)
        } finally { NativeCore.destroy(handle) }
    }
}
