// SPDX-License-Identifier: GPL-3.0-or-later
package org.studyime.android.engine

import org.json.JSONObject

data class Candidate(val chinese: String, val english: String)
data class WordSense(
    val english: String, val pos: String = "", val usage: String = "",
    val collocation: String = "", val exampleEn: String = "", val exampleZh: String = "",
)
data class CandidateTarget(
    val token: String, val index: Int, val chinese: String,
    val english: String, val reason: String, val reading: String = "",
    val pinyin: String = "", val senses: List<WordSense> = emptyList(),
) {
    val canCommitEnglish: Boolean get() = reason == "ready"
}
data class EditorCommand(val id: Long, val kind: String, val text: String)
data class EngineSnapshot(
    val generation: Long = 0,
    val revision: Long = 0,
    val input: String = "",
    val preedit: String = "",
    val caret: Int = 0,
    val preeditCursor: Int = 0,
    val page: Int = 0,
    val lastPage: Boolean = true,
    val highlighted: Int = 0,
    val candidates: List<Candidate> = emptyList(),
    val spellingCandidates: List<String> = emptyList(),
    val schema: String = "study",
    val pendingSchema: String? = null,
    val showEnglish: Boolean = true,
    val userLearning: Boolean = true,
    val asciiMode: Boolean = false,
    val target: CandidateTarget? = null,
    val commands: List<EditorCommand> = emptyList(),
    val notice: String = "",
    val ready: Boolean = false,
    val error: Boolean = false,
) {
    companion object {
        fun parse(raw: String): EngineSnapshot {
            val json = JSONObject(raw)
            check(json.optBoolean("ok")) { json.optString("error", "engine-error") }
            val context = json.getJSONObject("context")
            val candidates = context.getJSONArray("candidates")
            val spellings = json.optJSONArray("spellingCandidates")
            val commands = json.getJSONArray("commands")
            val target = json.optJSONObject("target")?.let {
                CandidateTarget(it.getString("token"), it.getInt("index"), it.getString("chinese"),
                    it.getString("english"), it.getString("reason"), it.optString("reading"))
            }
            return EngineSnapshot(
                generation = json.getLong("generation"), revision = json.getLong("revision"),
                input = context.getString("input"), preedit = context.getString("preedit"),
                caret = context.getInt("caret"), preeditCursor = context.getInt("preeditCursor"),
                page = context.getInt("page"), lastPage = context.getBoolean("lastPage"),
                highlighted = context.getInt("highlighted"),
                candidates = List(candidates.length()) { index -> candidates.getJSONObject(index).let {
                    Candidate(it.getString("chinese"), it.getString("english"))
                } },
                spellingCandidates = spellings?.let { List(it.length(), it::getString) }.orEmpty(),
                schema = json.getString("schema"),
                pendingSchema = if (json.isNull("pendingSchema")) null else json.getString("pendingSchema"),
                showEnglish = json.getBoolean("showEnglish"), userLearning = json.getBoolean("userLearning"),
                asciiMode = json.getBoolean("asciiMode"), target = target,
                commands = List(commands.length()) { index -> commands.getJSONObject(index).let {
                    EditorCommand(it.getLong("id"), it.getString("kind"), it.getString("text"))
                } }, notice = json.getString("notice"), ready = true,
            )
        }
    }
}

fun event(type: String, vararg values: Pair<String, Any>): JSONObject = JSONObject().apply {
    put("type", type)
    values.forEach { (key, value) -> put(key, value) }
}

fun schemaName(schema: String): String = when (schema) {
    "study_double_pinyin" -> "自然码双拼"
    "study_flypy" -> "小鹤双拼"
    else -> "全拼"
}
