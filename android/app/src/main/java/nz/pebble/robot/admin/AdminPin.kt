package nz.pebble.robot.admin

import nz.pebble.robot.Atomic
import org.json.JSONObject
import java.io.File
import java.security.MessageDigest
import java.security.SecureRandom
import java.util.Base64
import javax.crypto.SecretKeyFactory
import javax.crypto.spec.PBEKeySpec

class AdminPin(private val file: File, private val now: () -> Long = System::currentTimeMillis, private val iterations: Int = ITERATIONS) {

    data class Check(val ok: Boolean, val waitMs: Long, val message: String)

    fun isSet(): Boolean = read() != null

    fun set(pin: String) {
        require(valid(pin)) { "The PIN needs 6 to 12 digits." }
        val salt = ByteArray(16).also { SecureRandom().nextBytes(it) }
        val hash = derive(pin, salt, iterations)
        val o = JSONObject()
            .put("v", 1)
            .put("salt", b64(salt))
            .put("iter", iterations)
            .put("hash", b64(hash))
            .put("failures", 0)
            .put("until", 0L)
        Atomic.write(file, o.toString().toByteArray())
    }

    fun check(pin: String): Check {
        val o = read() ?: return Check(false, 0, "No PIN is set yet.")
        val until = o.optLong("until", 0L)
        val wait = until - now()
        if (wait > 0) return Check(false, wait, "Too many wrong PINs. Try again in ${(wait + 999) / 1000} seconds.")
        val salt = Base64.getDecoder().decode(o.getString("salt"))
        val expected = Base64.getDecoder().decode(o.getString("hash"))
        val got = derive(pin, salt, o.optInt("iter", iterations))
        if (MessageDigest.isEqual(expected, got)) {
            if (o.optInt("failures", 0) != 0) Atomic.write(file, o.put("failures", 0).put("until", 0L).toString().toByteArray())
            return Check(true, 0, "")
        }
        val failures = o.optInt("failures", 0) + 1
        val lock = lockFor(failures)
        Atomic.write(file, o.put("failures", failures).put("until", if (lock > 0) now() + lock else 0L).toString().toByteArray())
        return if (lock > 0) Check(false, lock, "Wrong PIN. Wait ${lock / 1000} seconds before the next try.") else Check(false, 0, "Wrong PIN.")
    }

    private fun read(): JSONObject? = try {
        if (file.exists()) JSONObject(file.readText()).takeIf { it.has("hash") && it.has("salt") } else null
    } catch (e: Exception) {
        null
    }

    companion object {
        const val ITERATIONS = 210_000
        const val FREE_TRIES = 4
        const val MAX_LOCK_MS = 3_600_000L

        fun valid(pin: String): Boolean = pin.length in 6..12 && pin.all { it in '0'..'9' }

        fun lockFor(failures: Int): Long {
            if (failures <= FREE_TRIES) return 0
            val steps = (failures - FREE_TRIES - 1).coerceAtMost(10)
            return (30_000L shl steps).coerceAtMost(MAX_LOCK_MS)
        }

        fun derive(pin: String, salt: ByteArray, iterations: Int): ByteArray {
            val spec = PBEKeySpec(pin.toCharArray(), salt, iterations, 256)
            try {
                return SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256").generateSecret(spec).encoded
            } finally {
                spec.clearPassword()
            }
        }

        private fun b64(bytes: ByteArray): String = Base64.getEncoder().encodeToString(bytes)
    }
}
