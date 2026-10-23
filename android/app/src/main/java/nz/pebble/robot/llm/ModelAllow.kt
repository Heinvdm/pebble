package nz.pebble.robot.llm

import nz.pebble.robot.Atomic
import org.json.JSONObject
import java.io.File
import java.io.InputStream
import java.io.OutputStream
import java.security.MessageDigest

object ModelAllow {
    data class Known(val name: String, val bytes: Long, val sha256: String, val what: String)

    val KNOWN = listOf(
        Known("gemma-4-E4B_q4_0-it.gguf", 5_154_941_280L, "676c35070db6dbe52f93e9c864ee0fba4eddea94b9c875d9cb10daff453fbaee", "Gemma 4 E4B, Google's 4-bit QAT file"),
        Known("LFM2.5-230M-Q8_0.gguf", 246_598_496L, "855be85429300602eda72958547614703541b7d6dd965a8f8f6052b85a7aa935", "LFM2.5-230M, the small model"),
        Known("mtp-gemma-4-E4B-it-Q8_0.gguf", 98_653_280L, "f38ae62962657c7a6303c49bbb147e9ae23634e911cfa532fac0818c2e18b665", "Gemma 4 E4B's drafter"),
    )

    private const val BUFFER = 1 shl 20

    fun known(bytes: Long, sha256: String): Known? = KNOWN.firstOrNull { it.bytes == bytes && it.sha256.equals(sha256, ignoreCase = true) }

    fun maybeKnown(bytes: Long): Boolean = KNOWN.any { it.bytes == bytes }

    fun hex(digest: ByteArray): String = digest.joinToString("") { String.format("%02x", it.toInt() and 0xFF) }

    fun copy(input: InputStream, output: OutputStream, limit: Long): Pair<Long, String> {
        val digest = MessageDigest.getInstance("SHA-256")
        val buffer = ByteArray(BUFFER)
        var total = 0L
        while (total < limit) {
            val count = input.read(buffer, 0, minOf(buffer.size.toLong(), limit - total).toInt())
            if (count < 0) break
            digest.update(buffer, 0, count)
            output.write(buffer, 0, count)
            total += count
        }
        return total to hex(digest.digest())
    }

    fun hash(file: File): String = file.inputStream().use { input ->
        val digest = MessageDigest.getInstance("SHA-256")
        val buffer = ByteArray(BUFFER)
        while (true) {
            val count = input.read(buffer)
            if (count < 0) break
            digest.update(buffer, 0, count)
        }
        hex(digest.digest())
    }

    class Seen(private val file: File) {
        private val lock = Any()

        private fun read(): JSONObject = try {
            if (file.exists()) JSONObject(file.readText()) else JSONObject()
        } catch (e: Exception) {
            JSONObject()
        }

        fun note(model: File, sha256: String) = synchronized(lock) {
            val all = read()
            all.put(model.name, JSONObject().put("bytes", model.length()).put("modified", model.lastModified()).put("sha256", sha256))
            Atomic.write(file, all.toString().toByteArray())
        }

        fun forget(name: String) = synchronized(lock) {
            val all = read()
            if (all.has(name)) {
                all.remove(name)
                Atomic.write(file, all.toString().toByteArray())
            }
        }

        fun allowed(model: File): Boolean = synchronized(lock) {
            val entry = read().optJSONObject(model.name) ?: return false
            if (entry.optLong("bytes", -1L) != model.length() || entry.optLong("modified", -1L) != model.lastModified()) return false
            known(model.length(), entry.optString("sha256")) != null
        }

        fun checked(model: File): Boolean = synchronized(lock) {
            val entry = read().optJSONObject(model.name) ?: return false
            entry.optLong("bytes", -1L) == model.length() && entry.optLong("modified", -1L) == model.lastModified()
        }
    }
}
