// SPDX-License-Identifier: GPL-3.0-or-later
package org.studyime.android.engine

import android.content.Context
import android.util.AtomicFile
import java.io.File
import java.security.MessageDigest
import org.json.JSONObject

/** New resources stage independently of the persistent private user dictionary. */
class DataDeployer(
    context: Context,
    private val root: File = File(context.noBackupFilesDir, "rime"),
    private val asset: (String) -> ByteArray = { name -> context.assets.open(name).use { it.readBytes() } },
) {
    data class Resources(val version: String, val directory: File, val user: File) {
        val shared get() = File(directory, "rime")
        val build get() = File(directory, "build").apply { mkdirs() }
    }
    private val active get() = AtomicFile(File(root, "active-version"))

    private fun hash(bytes: ByteArray) = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }

    private fun child(directory: File, name: String): File = File(directory, name).canonicalFile.also {
        require(it.path.startsWith(directory.canonicalPath + File.separator))
    }

    private fun verified(directory: File, version: String): Boolean = runCatching {
        if (File(directory, ".verified").readTextOrNull() != version) return false
        val manifest = JSONObject(File(directory, "manifest.json").readText())
        if (manifest.getString("version") != version || manifest.getInt("format") != 1) return false
        val hashes = manifest.getJSONObject("files")
        hashes.length() > 0 && hashes.keys().asSequence().all { name ->
            val file = child(directory, name)
            file.isFile && hash(file.readBytes()) == hashes.getString(name)
        }
    }.getOrDefault(false)

    fun prepare(force: Boolean = false): Resources = synchronized(lock) {
        val manifestBytes = asset("generated/manifest.json")
        val manifest = JSONObject(String(manifestBytes, Charsets.UTF_8))
        require(manifest.getInt("format") == 1)
        val version = manifest.getString("version")
        require(version.matches(Regex("[a-f0-9]{20}")))
        val versions = File(root, "resources").apply { mkdirs() }
        val destination = File(versions, version)
        val user = File(root, "user").apply { mkdirs() }
        if (!force && verified(destination, version)) {
            return@synchronized Resources(version, destination, user)
        }
        val pending = File(versions, "$version.pending")
        if (pending.exists()) check(pending.deleteRecursively()) { "staging-cleanup-failed" }
        check(pending.mkdirs())
        val hashes = manifest.getJSONObject("files")
        hashes.keys().forEach { name ->
            val output = child(pending, name)
            val content = asset("generated/$name")
            check(hash(content) == hashes.getString(name)) { "asset-integrity-failed" }
            output.parentFile!!.mkdirs()
            output.outputStream().use { it.write(content) }
        }
        File(pending, "manifest.json").writeBytes(manifestBytes)
        File(pending, ".verified").writeText(version)
        // Rebuild a corrupt/incomplete version without ever moving the user
        // dictionary. Stage all bytes before replacing the resource directory.
        val replaced = File(versions, "$version.replaced")
        if (replaced.exists()) check(replaced.deleteRecursively())
        if (destination.exists()) check(destination.renameTo(replaced)) { "resource-replacement-failed" }
        if (!pending.renameTo(destination)) {
            if (replaced.exists()) replaced.renameTo(destination)
            error("resource-activation-failed")
        }
        Resources(version, destination, user)
    }

    /** One retry from packaged bytes; an older ready version remains a fallback. */
    fun <T> open(initialize: (Resources) -> T, close: (T) -> Unit): T {
        fun activate(resources: Resources): T {
            val value = initialize(resources)
            try { markReady(resources) }
            catch (error: Exception) { close(value); throw error }
            File(resources.directory.parentFile, "${resources.version}.replaced").deleteRecursively()
            return value
        }
        val resources = try { prepare() } catch (error: Exception) {
            return previous()?.let(initialize) ?: throw error
        }
        return try { activate(resources) } catch (first: Exception) {
            try { activate(prepare(force = true)) } catch (_: Exception) {
                previous()?.takeIf { it.version != resources.version }?.let(initialize) ?: throw first
            }
        }
    }

    fun markReady(resources: Resources) {
        root.mkdirs()
        val stream = active.startWrite()
        try {
            stream.write(resources.version.toByteArray())
            active.finishWrite(stream)
            check(String(active.readFully(), Charsets.UTF_8) == resources.version) { "active-version-write-failed" }
        }
        catch (error: Exception) { active.failWrite(stream); throw error }
    }

    fun previous(): Resources? = runCatching {
        val version = String(active.readFully(), Charsets.UTF_8)
        if (!version.matches(Regex("[a-f0-9]{20}"))) return null
        val directory = File(root, "resources/$version")
        if (!verified(directory, version)) return null
        Resources(version, directory, File(root, "user"))
    }.getOrNull()

    private fun File.readTextOrNull(): String? = if (isFile) readText() else null
    companion object { private val lock = Any() }
}
