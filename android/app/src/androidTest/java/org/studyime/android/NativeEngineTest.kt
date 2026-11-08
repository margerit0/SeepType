// SPDX-License-Identifier: GPL-3.0-or-later
package org.studyime.android

import android.os.Build
import android.os.SystemClock
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import java.io.File
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.studyime.android.engine.*
import org.studyime.android.settings.KeyboardPreferences

/** Every candidate below comes through Kotlin -> JNI -> Rust -> Rime -> Lua. */
@RunWith(AndroidJUnit4::class)
class NativeEngineTest {
    @Test fun realEngineRegressionAndSessionGuards() {
        val executor = Executors.newSingleThreadExecutor()
        try { executor.submit { runCases() }.get(15, TimeUnit.MINUTES) }
        finally { executor.shutdownNow() }
    }

    private fun runCases() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val context = instrumentation.targetContext
        val root = File(context.noBackupFilesDir, "verification-${SystemClock.elapsedRealtime()}")
        val deployer = DataDeployer(context, root)
        val started = SystemClock.elapsedRealtime()
        val resources = deployer.prepare()
        var handle = NativeCore.create(resources.shared.path, resources.user.path, resources.build.path)
        assertTrue(handle > 0)
        deployer.markReady(resources)
        val startupMs = SystemClock.elapsedRealtime() - started
        var generation = 1L
        var config = KeyboardPreferences(userLearning = false)
        val report = JSONObject().put("scope", "Android native release libraries in a debug instrumentation APK; synthetic, isolated user dictionary")
            .put("fingerprint", Build.FINGERPRINT).put("api", Build.VERSION.SDK_INT)
            .put("abis", JSONArray(Build.SUPPORTED_ABIS.toList())).put("engine", NativeCore.version(handle))
            .put("resourceVersion", resources.version).put("firstDeploymentMs", startupMs)
        val checks = JSONArray()
        val regressions = JSONArray()
        val latency = mutableListOf<Double>()
        report.put("checks", checks).put("wordRegressions", regressions)
        fun check(name: String, passed: Boolean) {
            checks.put(JSONObject().put("name", name).put("passed", passed))
            assertTrue(name, passed)
        }
        fun send(command: JSONObject): EngineSnapshot {
            command.put("generation", generation)
            val start = SystemClock.elapsedRealtimeNanos()
            val result = EngineSnapshot.parse(NativeCore.dispatch(handle, command.toString()))
            latency.add((SystemClock.elapsedRealtimeNanos() - start) / 1_000_000.0)
            return result
        }
        fun start() = send(event("start", "config" to config.engineConfig(false, false, false)))
        fun clear() = send(event("clear"))
        fun type(input: String): EngineSnapshot {
            var value = clear()
            for (char in input) value = send(event("key", "code" to char.code))
            return value
        }
        fun find(initial: EngineSnapshot, word: String): Pair<EngineSnapshot, Int> {
            var value = initial
            repeat(100) {
                val index = value.candidates.indexOfFirst { it.chinese == word }
                if (index >= 0) return value to index
                if (value.lastPage) error("Missing candidate: $word")
                value = send(event("page", "backwards" to false, "revision" to value.revision))
            }
            error("Candidate page budget exhausted: $word")
        }
        fun scheme(name: String, learning: Boolean = false) {
            clear()
            config = config.copy(schema = name, userLearning = learning)
            send(event("configure", "config" to config.engineConfig(false, false, false)))
        }
        fun inspect(value: EngineSnapshot, index: Int) = send(event("inspect", "index" to index, "revision" to value.revision))

        try {
            start()
            check("Kotlin loads Rust and fixed Rime/Lua", NativeCore.version(handle).contains("Rime 1.13.1"))
            val smoke = type("gongyuan")
            check("P0 returns real park candidate and Lua annotation", smoke.candidates.any { it.chinese == "公园" && it.english == "park" })
            val cases = JSONArray(instrumentation.context.assets.open("generated/engine-cases.json").bufferedReader().use { it.readText() })
            assertEquals(600, cases.length())
            var failures = 0
            for (number in 0 until cases.length()) {
                val case = cases.getJSONObject(number)
                val record = JSONObject(case.toString())
                try {
                    scheme(case.getString("schema"))
                    var (value, index) = find(type(case.getString("input")), case.getString("chinese"))
                    assertEquals(case.getString("english"), value.candidates[index].english)
                    value = inspect(value, index)
                    val target = value.target!!
                    assertEquals("ready", target.reason)
                    assertEquals(case.getString("english"), target.english)
                    val english = send(event("english", "token" to target.token))
                    assertEquals(case.getString("english"), english.commands.single().text)
                    assertTrue(english.input.isEmpty())
                    assertTrue(send(event("english", "token" to target.token)).commands.isEmpty())
                    val chineseTarget = find(type(case.getString("input")), case.getString("chinese"))
                    val chinese = send(event("select", "index" to chineseTarget.second, "revision" to chineseTarget.first.revision))
                    assertEquals(case.getString("chinese"), chinese.commands.single().text)
                    assertTrue(chinese.input.isEmpty())
                    record.put("passed", true)
                } catch (error: AssertionError) {
                    failures++
                    record.put("passed", false).put("error", error.message)
                } catch (error: Exception) {
                    failures++
                    record.put("passed", false).put("error", error.message)
                }
                regressions.put(record)
                if ((number + 1) % 50 == 0) android.util.Log.i("StudyVerification", "Synthetic engine cases: ${number + 1}/600; failures=$failures")
            }
            check("600 dictionary annotations and Chinese/English commits", failures == 0)

            scheme("study")
            var (word, index) = find(type("gongyuan"), "公园")
            var inspected = inspect(word, index)
            val oldToken = inspected.target!!.token
            val originalInput = inspected.input
            config = config.copy(showEnglish = false)
            val hidden = send(event("configure", "config" to config.engineConfig(false, false, false)))
            check("English toggle preserves input and selected Chinese", hidden.input == originalInput &&
                hidden.candidates[hidden.highlighted].chinese == "公园" && hidden.candidates.all { it.english.isEmpty() })
            check("Closed English row invalidates old target", send(event("english", "token" to oldToken)).commands.isEmpty())
            config = config.copy(showEnglish = true)
            send(event("configure", "config" to config.engineConfig(false, false, false)))

            val partial = find(type("nihaoma"), "你好")
            inspected = inspect(partial.first, partial.second)
            check("Partial composition disables English", inspected.target!!.reason == "partial-composition")
            val rejected = send(event("english", "token" to inspected.target!!.token))
            check("Rejected partial action retains the remaining input", rejected.commands.isEmpty() && rejected.input == "nihaoma")

            word = type("gongyuan")
            word = send(event("caret", "position" to 3))
            inspected = inspect(word, word.highlighted)
            check("Caret away from end disables English", inspected.target!!.reason == "partial-composition")
            check("Caret rejection keeps composition", send(event("english", "token" to inspected.target!!.token)).input == "gongyuan")

            word = type("gongyuan")
            val stale = word.revision
            send(event("key", "code" to 'm'.code))
            val staleSelect = send(event("select", "index" to 0, "revision" to stale))
            check("Stale Chinese candidate cannot commit newer input", staleSelect.commands.isEmpty() && staleSelect.input == "gongyuanm")
            generation++
            start()
            val late = EngineSnapshot.parse(NativeCore.dispatch(handle, event("key", "code" to 'a'.code, "generation" to generation - 1).toString()))
            check("Old editor generation cannot type into new editor", late.input.isEmpty() && late.commands.isEmpty())

            generation++
            val secure = send(event("start", "config" to config.engineConfig(false, true, true)))
            val password = send(event("key", "code" to 'n'.code))
            check("Password bypasses engine learning and annotations", secure.asciiMode && !secure.showEnglish && !secure.userLearning &&
                password.commands.single().text == "n" && password.input.isEmpty())
            generation++
            val privateEditor = send(event("start", "config" to config.engineConfig(false, false, true)))
            check("No-personalized-learning flag preserves English feature", !privateEditor.userLearning && privateEditor.showEnglish)
            generation++
            start()

            scheme("study_flypy", learning = true)
            val ni = find(type("nihc"), "拟")
            val segment = send(event("select", "index" to ni.second, "revision" to ni.first.revision))
            val hao = find(segment, "好")
            val phrase = send(event("select", "index" to hao.second, "revision" to hao.first.revision))
            check("Segmented input learns synthetic phrase", phrase.commands.single().text == "拟好")
            listOf("study_flypy" to "nihc", "study" to "nihao", "study_double_pinyin" to "nihk").forEach { (schema, input) ->
                scheme(schema, learning = true)
                check("$schema shares learned Chinese phrase", type(input).candidates.first().chinese == "拟好")
            }
            clear()
            NativeCore.destroy(handle)
            handle = 0
            handle = NativeCore.create(resources.shared.path, resources.user.path, resources.build.path)
            generation++
            start()
            scheme("study", learning = false)
            check("Learned phrase survives native restart", type("nihao").candidates.first().chinese == "拟好")
            val current = type("nihao")
            val forgetTarget = inspect(current, 0).target!!
            val forgotten = send(event("forget", "token" to forgetTarget.token))
            check("Forget retains composition and emits no editor text", forgotten.input == "nihao" && forgotten.commands.isEmpty())
            scheme("study_flypy")
            check("Forget is shared across schemes", type("nihc").candidates.first().chinese != "拟好")
            val pausedNi = find(type("nihc"), "拟")
            val pausedSegment = send(event("select", "index" to pausedNi.second, "revision" to pausedNi.first.revision))
            val pausedHao = find(pausedSegment, "好")
            send(event("select", "index" to pausedHao.second, "revision" to pausedHao.first.revision))
            check("Paused learning does not add the new phrase again", type("nihc").candidates.first().chinese != "拟好")

            report.put("passed", true)
        } finally {
            if (handle != 0L) NativeCore.destroy(handle)
            val sorted = latency.sorted()
            if (sorted.isNotEmpty()) report.put("jniSynchronousLatencyMs", JSONObject().put("samples", sorted.size)
                .put("p50", sorted[(sorted.size * .5).toInt().coerceAtMost(sorted.lastIndex)])
                .put("p95", sorted[(sorted.size * .95).toInt().coerceAtMost(sorted.lastIndex)])
                .put("p99", sorted[(sorted.size * .99).toInt().coerceAtMost(sorted.lastIndex)]))
            report.put("elapsedMs", SystemClock.elapsedRealtime() - started)
            File(context.filesDir, "native-engine-report.json").writeText(report.toString(2))
        }
    }
}
