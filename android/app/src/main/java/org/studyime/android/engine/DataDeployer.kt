// SPDX-License-Identifier: GPL-3.0-or-later
package org.studyime.android.engine

import android.content.Context
import android.util.AtomicFile
import java.io.File
import java.security.MessageDigest
import org.json.JSONObject

/** New resources stage independently of the persistent private user dictionary. */
class DataDeployer(private val context: Context, private val root: File = File(context.noBackupFilesDir, "rime")) {
    data class Resources(val version: String, val directory: File, val user: File) {
        val shared get() = File(directory, "rime")
        val build get() = File(directory, "build").apply { mkdirs() }
    }
    private val active get() = AtomicFile(File(root, "active-version"))

    fun prepare(): Resources = synchronized(lock) {
        val manifestBytes = context.assets.open("generated/manifest.json").use { it.readBytes() }
        val manifest = JSONObject(String(manifestBytes, Charsets.UTF_8))
        require(manifest.getInt("format") == 1)
        val version = manifest.getString("version")
        require(version.matches(Regex("[a-f0-9]{20}")))
        val versions = File(root, "resources").apply { mkdirs() }
        val destination = File(versions, version)
        val user = File(root, "user").apply { mkdirs() }
        if (File(destination, ".verified").readTextOrNull() == version) {
            return@synchronized Resources(version, destination, user)
        }
        val pending = File(versions, "$version.pending").apply { mkdirs() }
        val hashes = manifest.getJSONObject("files")
        hashes.keys().forEach { name ->
            val output = File(pending, name).canonicalFile
            require(output.path.startsWith(pending.canonicalPath + File.separator))
            val content = context.assets.open("generated/$name").use { it.readBytes() }
            val hash = MessageDigest.getInstance("SHA-256").digest(content).joinToString("") { "%02x".format(it) }
            check(hash == hashes.getString(name)) { "asset-integrity-failed" }
            output.parentFile!!.mkdirs()
            output.outputStream().use { it.write(content) }
        }
        File(pending, "manifest.json").writeBytes(manifestBytes)
        File(pending, ".verified").writeText(version)
        // A completed version is immutable. The active pointer is advanced only
        // after Rime successfully initializes its compiled dictionary and Lua.
        check(!destination.exists() && pending.renameTo(destination)) { "resource-activation-failed" }
        Resources(version, destination, user)
    }

    fun markReady(resources: Resources) {
        root.mkdirs()
        val stream = active.startWrite()
        try { stream.write(resources.version.toByteArray()); active.finishWrite(stream) }
        catch (error: Exception) { active.failWrite(stream); throw error }
    }

    fun previous(): Resources? = runCatching {
        val version = String(active.readFully(), Charsets.UTF_8)
        if (!version.matches(Regex("[a-f0-9]{20}"))) return null
        val directory = File(root, "resources/$version")
        if (File(directory, ".verified").readTextOrNull() != version) return null
        Resources(version, directory, File(root, "user"))
    }.getOrNull()

    private fun File.readTextOrNull(): String? = if (isFile) readText() else null
    companion object { private val lock = Any() }
}
