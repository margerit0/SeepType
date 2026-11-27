// SPDX-License-Identifier: GPL-3.0-or-later
package org.studyime.android

import android.accessibilityservice.AccessibilityServiceInfo
import android.content.Intent
import android.os.Build
import android.os.SystemClock
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.By
import androidx.test.uiautomator.Until
import java.io.File
import java.util.UUID
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.regex.Pattern
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.studyime.android.engine.DataDeployer
import org.studyime.android.engine.EngineSnapshot
import org.studyime.android.engine.NativeCore
import org.studyime.android.engine.event
import org.studyime.android.settings.KeyboardPreferences
import org.studyime.android.settings.KeyboardSkin
import org.studyime.android.settings.Preferences

/** Measures fixed regressions and matched before/after probes with isolated engine data. */
@RunWith(AndroidJUnit4::class)
class OfflineNamesTest {
    private data class Probe(val word: String, val codes: List<String>, val folded: Boolean = false)
    private val schemas = listOf("study", "study_double_pinyin", "study_flypy")
    private val probes = listOf(
        Probe("芙宁娜", listOf("funingna", "funyna", "funkna"), folded = true),
        Probe("钟离", listOf("zhongli", "vsli", "vsli")),
        Probe("那维莱特", listOf("naweilaite", "nawzllte", "nawwldte"), folded = true),
        Probe("纳西妲", listOf("naxida", "naxida", "naxida")),
        Probe("雷电将军", listOf("leidianjiangjun", "lzdmjdjp", "lwdmjljy")),
        Probe("原神", listOf("yuanshen", "yruf", "yruf")),
        Probe("丹恒", listOf("danheng", "djhg", "djhg")),
        Probe("三月七", listOf("sanyueqi", "sjytqi", "sjytqi")),
        Probe("流浪地球", listOf("liulangdiqiu", "lqlhdiqq", "lqlhdiqq")),
        Probe("哪吒之魔童降世", listOf("nezhazhimotongjiangshi", "nevavimotsjdui", "nevavimotsjlui")),
        Probe("千与千寻", listOf("qianyuqianxun", "qmyuqmxp", "qmyuqmxy")),
        Probe("星际穿越", listOf("xingjichuanyue", "xyjiiryt", "xkjiiryt")),
        Probe("琅琊榜", listOf("langyabang", "lhyabh", "lhyabh"), folded = true),
        Probe("艾尔登法环", listOf("aierdengfahuan", "aierdgfahr", "aierdgfahr"), folded = true),
        Probe("浪浪山小妖怪", listOf("langlangshanxiaoyaoguai", "lhlhujxcykgy", "lhlhujxnycgk"), folded = true),
        Probe("鸣潮", listOf("mingchao", "myik", "mkic"), folded = true),
    )
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private val context = instrumentation.targetContext
    private val baseline = InstrumentationRegistry.getArguments().getString("namesBaseline") == "true"

    private fun report(cases: JSONArray) = JSONObject().put("baseline", baseline)
        .put("fingerprint", Build.FINGERPRINT).put("api", Build.VERSION.SDK_INT).put("cases", cases)
    private fun manifest(): JSONObject = context.assets.open("generated/manifest.json").bufferedReader(Charsets.UTF_8)
        .use { JSONObject(it.readText()) }

    private fun checkApkMode() = assertEquals("Baseline runs must use an APK without the names table", !baseline, manifest().has("offlineNames"))

    private fun originalTop(schema: String): String = instrumentation.context.assets
        .open("offline-names/zhongli-baseline.json").bufferedReader(Charsets.UTF_8).use { JSONObject(it.readText()).getString(schema) }

    private fun retainedTop(word: String, schema: String): String? = when (word) {
        "钟离" -> originalTop(schema)
        "鸣潮" -> "明朝" // Measured in all schemes on the 381-entry APK before adding 鸣潮.
        else -> null
    }

    @Test fun nativeCandidates() {
        checkApkMode()
        runNative { probeEngine(probes, "offline-names-engine.json", detailed = true) }
    }

    @Test fun workTitleCandidates() {
        checkApkMode()
        val encode = schemas.map(::encoder)
        val entries = instrumentation.context.assets.open("offline-names/work-title-probes.tsv")
            .bufferedReader(Charsets.UTF_8).useLines { lines ->
                lines.filter { it.isNotBlank() && !it.startsWith('#') }.map { line ->
                    val (word, reading) = line.split('\t')
                    encodedProbe(word, reading, encode)
                }.toList()
            }
        require(entries.isNotEmpty())
        // The same fixture runs on the original 381-name APK and on the update.
        // It includes names we decided not to package, so absence is data here.
        runNative { probeEngine(entries, "offline-names-work-titles.json", detailed = true, allowMissing = true) }
    }

    private fun encodedProbe(word: String, reading: String, encode: List<(String) -> String>) =
        Probe(word, encode.map { code -> reading.split(' ').joinToString("", transform = code) })

    @Test fun allPackagedNames() {
        checkApkMode()
        check(!baseline) { "Full coverage requires the names APK" }
        val encode = schemas.map(::encoder)
        val entries = context.assets.open("generated/rime/study_offline_names.dict.yaml").bufferedReader(Charsets.UTF_8).useLines { lines ->
            lines.dropWhile { it != "..." }.drop(1).filter { it.isNotBlank() }.map { row ->
                val (word, reading) = row.split('\t')
                encodedProbe(word, reading, encode)
            }.toList()
        }
        assertEquals(manifest().getJSONObject("offlineNames").getInt("entries"), entries.size)
        runNative { probeEngine(entries, "offline-names-coverage.json", detailed = false) }
    }

    @Test fun curatedPhraseCandidates() {
        val examples = listOf(
            Probe("松弛感", listOf("songchigan", "ssiigj", "ssiigj")),
            Probe("上大分", listOf("shangdafen", "uhdaff", "uhdaff")),
            Probe("游戏攻略", listOf("youxigonglve", "ybxigslt", "yzxigslt")),
            Probe("暴击伤害", listOf("baojishanghai", "bkjiuhhl", "bcjiuhhd")),
            Probe("视频时长", listOf("shipinshichang", "uipnuiih", "uipbuiih")),
            Probe("对局时长", listOf("duijushichang", "dvjuuiih", "dvjuuiih")),
            Probe("请重试", listOf("qingchongshi", "qyisui", "qkisui")),
            Probe("等会儿", listOf("denghuier", "dghver", "dghver")),
        )
        runNative { probeEngine(examples, "curated-phrases-engine.json", detailed = true) }
    }

    @Test fun allCuratedPhrases() {
        val encode = schemas.map(::encoder)
        val entries = context.assets.open("generated/rime/study_phrases.dict.yaml")
            .bufferedReader(Charsets.UTF_8).useLines { lines ->
                lines.dropWhile { it != "..." }.drop(1)
                    .filter { it.isNotBlank() && !it.startsWith('#') }.map { row ->
                        val (word, reading) = row.split('\t')
                        encodedProbe(word, reading, encode)
                    }.toList()
            }
        assertEquals(1000, entries.size)
        runNative { probeEngine(entries, "curated-phrases-coverage.json", detailed = false) }
    }

    private fun encoder(schema: String): (String) -> String {
        if (schema == "study") return { it }
        // Use the packaged scheme's transformations for the long coverage run.
        // The independent fixed probes above also catch regressions in these keys.
        val transforms = context.assets.open("generated/rime/$schema.schema.yaml").bufferedReader(Charsets.UTF_8).useLines { lines ->
            lines.dropWhile { it != "  algebra:" }.drop(1)
                .takeWhile { it.isBlank() || it.startsWith("    ") }
                .filter { it.startsWith("    - ") }.mapNotNull { line ->
                    val (operation, source, target) = line.removePrefix("    - ").split('/')
                    when (operation) {
                        "xform" -> {
                            val regex = source.toRegex()
                            val transform: (String) -> String = { regex.replace(it, target) }
                            transform
                        }
                        "xlit" -> {
                            val pairs = source.zip(target).toMap()
                            val transform: (String) -> String = { syllable -> syllable.map { pairs[it] ?: it }.joinToString("") }
                            transform
                        }
                        "derive", "erase", "abbrev" -> null // alternate spellings and initial keys are not full syllable codes
                        else -> error("Unsupported $schema algebra operation $operation")
                    }
                }.toList()
        }
        check(transforms.isNotEmpty())
        return { syllable -> transforms.fold(syllable) { value, step -> step(value) }.also {
            check(it.matches(Regex("[a-z]{2}"))) { "No canonical double-pinyin key for $schema $syllable: $it" }
        } }
    }

    private fun runNative(work: () -> Unit) {
        val executor = Executors.newSingleThreadExecutor()
        try { executor.submit { work() }.get(5, TimeUnit.MINUTES) }
        finally { executor.shutdownNow() }
    }

    private fun probeEngine(probes: List<Probe>, reportFile: String, detailed: Boolean, allowMissing: Boolean = baseline) {
        val root = File(context.cacheDir, "offline-names-${UUID.randomUUID()}")
        val deployer = DataDeployer(context, root)
        val cases = JSONArray()
        val result = report(cases)
        manifest().optJSONObject("offlineNames")?.let { names ->
            result.put("namesTableEntries", names.getInt("entries")).put("namesTsvSha256", names.getString("tsvSha256"))
        }
        var handle = 0L
        try {
            val resources = deployer.prepare()
            result.put("resourceVersion", resources.version)
            handle = NativeCore.create(resources.shared.path, resources.user.path, resources.build.path)
            result.put("engine", NativeCore.version(handle))
            deployer.markReady(resources)
            val config = KeyboardPreferences(userLearning = false, showEnglish = true)
            fun send(command: JSONObject): EngineSnapshot = EngineSnapshot.parse(
                NativeCore.dispatch(handle, command.put("generation", 1).toString())
            )
            send(event("start", "config" to config.engineConfig(false, false, false)))
            fun spell(code: String): EngineSnapshot {
                var value = send(event("clear"))
                for (letter in code) value = send(event("key", "code" to letter.code))
                return value
            }
            val failures = mutableListOf<String>()
            for ((scheme, schema) in schemas.withIndex()) {
                send(event("clear"))
                val configured = send(event("configure", "config" to config.copy(schema = schema).engineConfig(false, false, false)))
                assertEquals(schema, configured.schema)
                for (probe in probes) {
                    val code = probe.codes[scheme]
                    var current = spell(code)
                    assertEquals("$schema $code", code, current.input)
                    val firstPage = current.candidates
                    val top = firstPage.firstOrNull()?.chinese.orEmpty()
                    val row = JSONObject().put("schema", schema).put("input", code).put("word", probe.word)
                    if (detailed) row.put("firstPage", JSONArray(firstPage.map { JSONObject().put("zh", it.chinese).put("en", it.english) }))
                    cases.put(row)
                    var preceding = 0
                    val maxPages = if (detailed) 8 else 20
                    var index = current.candidates.indexOfFirst { it.chinese == probe.word }
                    while (index < 0 && !current.lastPage && current.page + 1 < maxPages) {
                        preceding += current.candidates.size
                        current = send(event("page", "backwards" to false, "revision" to current.revision))
                        index = current.candidates.indexOfFirst { it.chinese == probe.word }
                    }
                    row.put("rank", if (index >= 0) preceding + index + 1 else JSONObject.NULL)
                        .put("pagesSearched", current.page + 1).put("reachedEnd", current.lastPage)
                    if (index >= 0) {
                        row.put("english", current.candidates[index].english)
                        val selected = send(event("select", "index" to index, "revision" to current.revision))
                        row.put("committed", selected.commands.singleOrNull { it.kind == "commit" }?.text ?: JSONObject.NULL)
                        row.put("compositionCleared", selected.input.isEmpty())
                    }
                    if ((!allowMissing || index >= 0) &&
                        (row.optString("committed") != probe.word || !row.optBoolean("compositionCleared"))) {
                        failures += "$schema $code did not commit ${probe.word}"
                    }
                    if (!allowMissing) {
                        val expectedEnglish = if (detailed && probe.word == "芙宁娜") "Furina" else ""
                        if (detailed && row.optString("english") != expectedEnglish) failures += "$schema: unexpected English for ${probe.word}"
                        if (expectedEnglish.isNotEmpty() && preceding == 0 && index >= 0) {
                            val spelled = spell(code)
                            val inspected = send(event("inspect", "index" to index, "revision" to spelled.revision)).target
                            val command = inspected?.let { send(event("english", "token" to it.token)) }?.commands?.singleOrNull()
                            row.put("englishCommitted", command?.text ?: JSONObject.NULL)
                            if (command?.kind != "commit" || command.text != expectedEnglish) {
                                failures += "$schema did not commit $expectedEnglish"
                            }
                        }
                        if (probe.folded && (index < 0 || preceding != 0)) failures += "$schema ${probe.word} not on engine page one"
                        if (detailed) retainedTop(probe.word, schema)?.let { expected ->
                            if (top != expected) failures += "$schema $code first candidate changed: $expected → $top"
                        }
                    }
                }
            }
            assertTrue(failures.joinToString("\n"), failures.isEmpty())
            result.put("passed", true)
        } finally {
            if (handle > 0) NativeCore.destroy(handle)
            File(context.filesDir, reportFile).writeText(result.toString(2))
            // This random root belongs exclusively to the synthetic test.
            root.deleteRecursively()
        }
    }

    @Test fun foldedCandidates() {
        checkApkMode()
        val d = ImeDriver()
        val ui = d.device
        val prefs = Preferences.get(context)
        val original = prefs.state.value
        instrumentation.uiAutomation.serviceInfo = instrumentation.uiAutomation.serviceInfo.apply {
            flags = flags or AccessibilityServiceInfo.FLAG_INCLUDE_NOT_IMPORTANT_VIEWS
        }
        val cases = JSONArray()
        val result = report(cases).put("widthPx", ui.displayWidth).put("heightPx", ui.displayHeight)
            .put("densityDpi", context.resources.displayMetrics.densityDpi).put("skin", "default").put("userLearning", false)
        try {
            assertTrue("This probe measures the portrait candidate strip", ui.displayHeight > ui.displayWidth)
            instrumentation.runOnMainSync {
                prefs.update { it.copy(skin = KeyboardSkin.DEFAULT, textScale = 1f, keyHeight = 1f, userLearning = false) }
            }
            for ((scheme, schema) in schemas.withIndex()) {
                for (probe in probes.filter { it.folded || it.word == "钟离" }) {
                    val token = SystemClock.elapsedRealtimeNanos()
                    context.startActivity(Intent(context, ProbeActivity::class.java).putExtra("schema", schema)
                        .putExtra("theme", "light").putExtra("english", true).putExtra("launchToken", token)
                        .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK))
                    assertTrue(ui.wait(Until.hasObject(By.desc("probe_launch_$token")), 8000))
                    d.editor().click()
                    assertTrue("IME accessibility root appears", ui.wait(Until.hasObject(By.res("study_keyboard")), 30_000))
                    d.type(probe.codes[scheme])
                    val expand = ui.wait(Until.findObject(By.desc("展开候选")), 8000) ?: error("Folded candidate strip missing")
                    ui.waitForIdle()
                    val visible = (0 until 9).mapNotNull { index ->
                        val cell = ui.findObject(By.res("candidate_$index")) ?: return@mapNotNull null
                        if (cell.visibleBounds.isEmpty) return@mapNotNull null
                        val label = cell.contentDescription ?: cell.findObject(By.desc(Pattern.compile(".+")))?.contentDescription
                        label?.let { index + 1 to it }
                    }
                    val row = JSONObject().put("schema", schema).put("input", probe.codes[scheme]).put("word", probe.word)
                        .put("folded", JSONArray(visible.map { (rank, label) -> JSONObject().put("rank", rank).put("label", label) }))
                    cases.put(row)
                    val label = By.descStartsWith(probe.word)
                    val foldedTarget = ui.findObjects(label).firstOrNull {
                        it.contentDescription?.toString()?.substringBefore("，英文释义：") == probe.word && !it.visibleBounds.isEmpty
                    }
                    row.put("visibleWithoutScroll", foldedTarget != null)
                    row.put("screenshot", d.capture("offline-names-ui", "$schema-${probes.indexOf(probe)}").name)
                    if (!baseline) {
                        retainedTop(probe.word, schema)?.let { expected ->
                            assertEquals("$schema ${probe.word}: original first candidate in folded UI", expected,
                                visible.firstOrNull()?.second?.substringBefore("，英文释义："))
                        }
                        if (probe.folded) assertTrue("$schema: ${probe.word} must be tappable without scrolling", foldedTarget != null)
                        var target = foldedTarget
                        if (target == null) {
                            expand.click()
                            repeat(8) {
                                if (target != null) return@repeat
                                target = ui.wait(Until.findObject(By.desc(probe.word)), 600)
                                if (target == null) ui.findObject(By.desc("下一页候选").enabled(true))?.click()
                            }
                        }
                        requireNotNull(target) { "$schema: missing candidate ${probe.word}" }.click()
                        d.expectText(probe.word)
                        row.put("committed", d.editor().text)
                        if (probe.word == "芙宁娜") {
                            assertTrue(visible.any { it.second == "芙宁娜，英文释义：Furina" })
                            d.editor().text = ""
                            d.type(probe.codes[scheme])
                            ui.wait(Until.findObject(By.desc("芙宁娜，英文释义：Furina")), 8000)!!.longClick()
                            (ui.wait(Until.findObject(By.res("commit_english")), 8000)
                                ?: error("Missing verified English action")).click()
                            d.expectText("Furina")
                            row.put("englishCommitted", d.editor().text)
                        }
                    }
                }
            }
            result.put("passed", true)
        } finally {
            File(context.filesDir, "offline-names-ui.json").writeText(result.toString(2))
            if (!result.optBoolean("passed")) runCatching { d.capture("offline-names-ui", "failure") }
            instrumentation.runOnMainSync { prefs.update { original } }
        }
    }
}
