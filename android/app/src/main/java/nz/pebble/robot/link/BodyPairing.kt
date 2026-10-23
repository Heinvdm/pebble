package nz.pebble.robot.link

import java.security.MessageDigest
import java.security.SecureRandom
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

interface LineChannel {
    fun send(line: String)
    fun receive(timeoutMs: Long): String?
}

object LinkProof {
    const val LABEL = "pebble-link-1"
    const val NONCE_BYTES = 16
    const val PROOF_BYTES = 16
    const val KEY_BYTES = 32
    private val HEX = Regex("^[0-9a-fA-F]+$")

    fun hex(bytes: ByteArray): String = bytes.joinToString("") { String.format("%02x", it.toInt() and 0xFF) }

    fun sessionMessage(phoneNonce: String, bodyNonce: String): ByteArray = "$LABEL ${phoneNonce.lowercase()} ${bodyNonce.lowercase()}".toByteArray(Charsets.US_ASCII)

    fun proof(session: ByteArray, who: String): String {
        val mac = Mac.getInstance("HmacSHA256")
        mac.init(SecretKeySpec(session, "HmacSHA256"))
        return hex(mac.doFinal(who.toByteArray(Charsets.US_ASCII)).copyOf(PROOF_BYTES))
    }

    fun challenge(line: String): Pair<String, String>? {
        val parts = line.trim().split(' ')
        if (parts.size != 3 || parts[0] != "h") return null
        val (nonce, proof) = parts[1] to parts[2]
        if (nonce.length != NONCE_BYTES * 2 || proof.length != PROOF_BYTES * 2 || !HEX.matches(nonce) || !HEX.matches(proof)) return null
        return nonce.lowercase() to proof.lowercase()
    }

    fun same(a: String, b: String): Boolean = MessageDigest.isEqual(a.toByteArray(), b.toByteArray())
}

object BodyPairing {
    const val REPLY_MS = 3_000L

    data class Result(val ok: Boolean, val message: String)

    fun prove(channel: LineChannel, mac: (ByteArray) -> ByteArray?, random: SecureRandom): Result {
        val nonce = ByteArray(LinkProof.NONCE_BYTES).also { random.nextBytes(it) }
        val phone = LinkProof.hex(nonce)
        channel.send("H $phone")
        val answer = wait(channel) { it.startsWith("h ") || it.startsWith("err H") } ?: return Result(false, "the body did not answer the handshake; is its firmware up to date?")
        if (answer.startsWith("err H")) return Result(false, if (answer.endsWith("key")) "the body has no key" else "the body refused the handshake ($answer)")
        val (body, bodyProof) = LinkProof.challenge(answer) ?: return Result(false, "the body's answer was malformed")
        val session = mac(LinkProof.sessionMessage(phone, body)) ?: return Result(false, "the phone's keystore would not use the body key")
        if (!LinkProof.same(LinkProof.proof(session, "body"), bodyProof)) return Result(false, "the body did not prove the key")
        channel.send("V ${LinkProof.proof(session, "phone")}")
        val done = wait(channel) { it == "ok" || it.startsWith("err V") } ?: return Result(false, "the body did not answer Pebble's proof")
        return if (done == "ok") Result(true, "the body proved the key") else Result(false, "the body refused Pebble's proof")
    }

    fun pair(channel: LineChannel, keep: (ByteArray) -> String?, mac: (ByteArray) -> ByteArray?, random: SecureRandom = SecureRandom()): Result {
        val raw = ByteArray(LinkProof.KEY_BYTES).also { random.nextBytes(it) }
        try {
            channel.send("H " + "0".repeat(LinkProof.NONCE_BYTES * 2))
            wait(channel, 1_000L) { it.startsWith("h ") || it.startsWith("err H") }
            channel.send("K ${LinkProof.hex(raw)}")
            val answer = wait(channel) { it == "ok" || it.startsWith("err K") } ?: return Result(false, "the body did not answer; is it plugged into the phone, switched on, with up-to-date firmware?")
            if (answer != "ok") return Result(false, if (answer.endsWith("usb")) "the body takes a key only over its own USB port" else "the body refused the key ($answer)")
            keep(raw)?.let { return Result(false, "the body took the key but $it; pair again") }
        } finally {
            raw.fill(0)
        }
        val proved = prove(channel, mac, random)
        return if (proved.ok) Result(true, "Paired: the body and this phone share a key, and the body proved it.") else Result(false, "the key was given but ${proved.message}; pair again")
    }

    private fun wait(channel: LineChannel, timeoutMs: Long = REPLY_MS, wanted: (String) -> Boolean): String? {
        val until = System.currentTimeMillis() + timeoutMs
        while (true) {
            val left = until - System.currentTimeMillis()
            if (left <= 0) return null
            val line = channel.receive(left)?.trim() ?: return null
            if (wanted(line)) return line
        }
    }
}
