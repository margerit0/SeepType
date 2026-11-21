// SPDX-License-Identifier: GPL-3.0-or-later
package org.studyime.android.engine

import java.io.IOException
import java.security.MessageDigest
import org.json.JSONException
import org.json.JSONObject

/** APK-only shards. Called on the serial engine worker, only for an inspected target. */
internal class WordDetails(private val readAsset: (String) -> String) {
    private var cachedBucket = -1
    private var cachedShard: JSONObject? = null

    fun enrich(target: CandidateTarget): CandidateTarget {
        if (target.english.isEmpty() || target.reading.isEmpty()) return target
        val bucket = MessageDigest.getInstance("SHA-256").digest(target.chinese.toByteArray(Charsets.UTF_8))[0].toInt() and 0x7f
        return try {
            if (cachedBucket != bucket) {
                cachedShard = JSONObject(readAsset("generated/word-details-v1/${bucket.toString(16).padStart(2, '0')}.json"))
                cachedBucket = bucket
            }
            val entry = cachedShard?.optJSONObject(target.chinese)?.optJSONObject(target.reading) ?: return target
            val rows = entry.getJSONArray("senses")
            // A stale or missing sidecar can never reinterpret the selected
            // candidate. Even on mismatch the original English action works.
            if (rows.optJSONObject(0)?.optString("english") != target.english) return target
            val senses = List(rows.length()) { index -> rows.getJSONObject(index).let {
                WordSense(it.getString("english"), it.optString("pos"), it.optString("usage"),
                    it.optString("collocation"), it.optString("exampleEn"), it.optString("exampleZh"))
            } }
            target.copy(pinyin = entry.optString("pinyin"), senses = senses)
        } catch (_: IOException) {
            target
        } catch (_: JSONException) {
            target
        }
    }
}
