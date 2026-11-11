// SPDX-License-Identifier: GPL-3.0-or-later
package org.studyime.android

import android.os.SystemClock
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import java.io.File
import java.io.RandomAccessFile
import java.security.MessageDigest
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.studyime.android.engine.DataDeployer

@RunWith(AndroidJUnit4::class)
class ResourceRecoveryTest {
    @Test fun interruptedUpdatesCorruptionAndFallbackPreserveUserData() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val root = File(context.noBackupFilesDir, "resource-check-${SystemClock.elapsedRealtime()}")
        val checks = JSONArray()
        val report = JSONObject().put("scope", "Android private filesystem and AtomicFile; synthetic versioned assets, no personal dictionary").put("checks", checks)
        fun check(name: String, passed: Boolean) { checks.put(JSONObject().put("name", name).put("passed", passed)); assertTrue(name, passed) }
        fun hash(value: ByteArray) = MessageDigest.getInstance("SHA-256").digest(value).joinToString("") { "%02x".format(it) }
        var assets = mapOf<String, ByteArray>()
        fun version(text: String): String {
            val body = text.toByteArray()
            val version = hash(body).take(20)
            val manifest = JSONObject().put("format", 1).put("version", version)
                .put("files", JSONObject().put("rime/schema.yaml", hash(body)))
            assets = mapOf("generated/manifest.json" to manifest.toString().toByteArray(), "generated/rime/schema.yaml" to body)
            return version
        }
        val deployer = DataDeployer(context, root) { name -> assets[name] ?: error("missing synthetic asset") }
        try {
            val a = version("synthetic version A")
            val first = deployer.prepare()
            File(first.user, "sentinel").writeText("synthetic learned entries")
            deployer.markReady(first)
            val b = version("synthetic version B")
            File(root, "resources/$b.pending/stale-file").apply { parentFile!!.mkdirs(); writeText("interrupted copy") }
            val second = deployer.prepare()
            check("Interrupted staging is replaced by verified complete resources", second.version == b && !File(second.directory, "stale-file").exists())
            check("Preparation alone never advances last-known-good version", deployer.previous()?.version == a)
            val attempts = mutableListOf<String>()
            val fallback = deployer.open(initialize = { value ->
                attempts += value.version
                kotlin.check(value.version != b) { "synthetic engine rejects new data" }
                value.version
            }, close = {})
            check("Failed native initialization retries clean data then opens previous version", fallback == a && attempts == listOf(b, b, a))
            check("Fallback preserves persistent user dictionary", File(first.user, "sentinel").readText() == "synthetic learned entries")

            val activated = deployer.open(initialize = { it.version }, close = {})
            check("Successful initialization atomically activates the new version", activated == b && deployer.previous()?.version == b)
            val corrupt = deployer.prepare()
            File(corrupt.shared, "schema.yaml").writeText("damaged after verification")
            val repaired = deployer.prepare()
            check("Verified marker does not conceal asset corruption", File(repaired.shared, "schema.yaml").readText() == "synthetic version B")
            check("Older complete resources remain available after activation", File(root, "resources/$a/.verified").isFile)

            val c = version("synthetic version C")
            assets = assets + ("generated/rime/schema.yaml" to "wrong downloaded bytes".toByteArray())
            val intact = deployer.open(initialize = { it.version }, close = {})
            check("Bad package hash leaves active resources usable", intact == b && !File(root, "resources/$c/.verified").exists())

            version("synthetic version B")
            File(repaired.build, "broken-index").writeText("incomplete native deployment")
            var nativeAttempts = 0
            val recreated = deployer.open(initialize = {
                nativeAttempts++
                kotlin.check(!File(it.build, "broken-index").exists()) { "synthetic corrupt compiled index" }
                it.version
            }, close = {})
            check("Native deployment failure rebuilds only resource indexes", recreated == b && nativeAttempts == 2 && File(first.user, "sentinel").isFile)

            val largeText = "0123456789".repeat(14_000)
            version(largeText)
            val large = deployer.prepare()
            val largeFile = File(large.shared, "schema.yaml")
            check("Streaming verification covers a resource larger than two buffers", deployer.prepare().version == large.version && largeFile.readText() == largeText)
            val modified = largeFile.lastModified()
            RandomAccessFile(largeFile, "rw").use { file -> file.seek(65_536); file.write('X'.code) }
            largeFile.setLastModified(modified)
            check("Same-size corruption with unchanged mtime is still repaired", File(deployer.prepare().shared, "schema.yaml").readText() == largeText)
            largeFile.delete()
            check("Missing previously verified resource is restored", File(deployer.prepare().shared, "schema.yaml").readText() == largeText)
            version("synthetic version B")

            File(root, "active-version").delete()
            File(root, "active-version").mkdirs()
            File(root, "active-version/occupied").writeText("prevent atomic rename")
            var closed = 0
            val failed = runCatching { deployer.open(initialize = { it.version }, close = { closed++ }) }.isFailure
            check("Activation write failure releases each newly owned native instance", failed && closed == 2)
            check("All recovery paths preserve user bytes", File(first.user, "sentinel").readText() == "synthetic learned entries")
            report.put("passed", true)
        } finally {
            File(context.filesDir, "resource-recovery-report.json").writeText(report.toString(2))
            root.deleteRecursively()
        }
    }
}
