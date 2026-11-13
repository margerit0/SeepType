// SPDX-License-Identifier: GPL-3.0-or-later
package org.studyime.android.settings

import android.content.Context
import android.content.SharedPreferences
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import org.json.JSONObject

data class KeyboardPreferences(
    val schema: String = "study",
    val showEnglish: Boolean = true,
    val userLearning: Boolean = true,
    val theme: String = "system",
    val skin: KeyboardSkin = KeyboardSkin.DEFAULT,
    val keyHeight: Float = 1f,
    val textScale: Float = 1f,
    val haptics: Boolean = true,
    val reduceMotion: Boolean = false,
) {
    fun engineConfig(ascii: Boolean, sensitive: Boolean, noPersonalization: Boolean) = JSONObject().apply {
        put("version", 1)
        put("schema", schema)
        put("showEnglish", showEnglish)
        put("userLearning", userLearning)
        put("asciiMode", ascii)
        put("sensitive", sensitive)
        put("noPersonalization", noPersonalization)
    }
}

class Preferences private constructor(context: Context) {
    private val storage = context.applicationContext.getSharedPreferences("preferences-v1", Context.MODE_PRIVATE)
    private fun read() = KeyboardPreferences(
        schema = storage.getString("schema", "study")!!.takeIf { it in listOf("study", "study_double_pinyin", "study_flypy") } ?: "study",
        showEnglish = storage.getBoolean("showEnglish", true),
        userLearning = storage.getBoolean("userLearning", true),
        theme = storage.getString("theme", "system")!!.takeIf { it in listOf("system", "light", "dark") } ?: "system",
        skin = KeyboardSkin.fromId(storage.getString("skin", null)),
        keyHeight = storage.getFloat("keyHeight", 1f).coerceIn(.9f, 1.2f),
        textScale = storage.getFloat("textScale", 1f).coerceIn(1f, 1.3f),
        haptics = storage.getBoolean("haptics", true),
        reduceMotion = storage.getBoolean("reduceMotion", false),
    )
    private val mutable = MutableStateFlow(read())
    val state: StateFlow<KeyboardPreferences> = mutable
    private val listener = SharedPreferences.OnSharedPreferenceChangeListener { _, _ -> mutable.value = read() }
    init { storage.registerOnSharedPreferenceChangeListener(listener) }

    fun update(change: (KeyboardPreferences) -> KeyboardPreferences) {
        val value = change(mutable.value)
        // apply() changes memory immediately and schedules disk I/O away from the key path.
        storage.edit().putString("schema", value.schema).putBoolean("showEnglish", value.showEnglish)
            .putBoolean("userLearning", value.userLearning).putString("theme", value.theme)
            .putString("skin", value.skin.id)
            .putFloat("keyHeight", value.keyHeight).putFloat("textScale", value.textScale)
            .putBoolean("haptics", value.haptics).putBoolean("reduceMotion", value.reduceMotion).apply()
        mutable.value = value
    }

    companion object {
        @Volatile private var instance: Preferences? = null
        fun get(context: Context): Preferences = instance ?: synchronized(this) {
            instance ?: Preferences(context).also { instance = it }
        }
    }
}
