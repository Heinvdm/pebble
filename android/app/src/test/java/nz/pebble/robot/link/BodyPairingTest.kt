package nz.pebble.robot.link

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.security.SecureRandom
import java.util.ArrayDeque
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

class BodyPairingTest {
    private fun hmac(key: ByteArray, message: ByteArray): ByteArray = Mac.getInstance("HmacSHA256").apply { init(SecretKeySpec(key, "HmacSHA256")) }.doFinal(message)

    private class FakeBody(var key: ByteArray?, val takesKeys: Boolean = true, val knowsHandshake: Boolean = true) : LineChannel {
        val out = ArrayDeque<String>()
        val heard = mutableListOf<String>()
        private var session: ByteArray? = null
        var proven = false

        private fun hmac(key: ByteArray, message: ByteArray): ByteArray = Mac.getInstance("HmacSHA256").apply { init(SecretKeySpec(key, "HmacSHA256")) }.doFinal(message)

        override fun send(line: String) {
            heard += line
            out.add("S 1 0 0 100 45 0 0 3900 8 0")
            val parts = line.split(' ')
            when (parts[0]) {
                "H" -> {
                    proven = false
                    val k = key
                    when {
                        !knowsHandshake -> out.add("err ? unknown")
                        k == null -> out.add("err H key")
                        else -> {
                            val body = "101112131415161718191a1b1c1d1e1f"
                            session = hmac(k, LinkProof.sessionMessage(parts[1], body))
                            out.add("h $body ${LinkProof.proof(session!!, "body")}")
                        }
                    }
                }
                "V" -> if (session != null && parts[1] == LinkProof.proof(session!!, "phone")) {
                    out.add("ok")
                    proven = true
                } else {
                    out.add("err V auth")
                }
                "K" -> if (takesKeys) {
                    key = hexBytes(parts[1])
                    out.add("ok")
                } else {
                    out.add("err K usb")
                }
            }
        }

        override fun receive(timeoutMs: Long): String? = out.pollFirst()
    }

    companion object {
        fun hexBytes(text: String): ByteArray = ByteArray(text.length / 2) { text.substring(it * 2, it * 2 + 2).toInt(16).toByte() }
    }

    @Test
    fun theProofsMatchTheFirmwareAndTheBrain() {
        val key = ByteArray(32) { it.toByte() }
        val session = hmac(key, LinkProof.sessionMessage("00112233445566778899AABBCCDDEEFF", "101112131415161718191a1b1c1d1e1f"))
        assertEquals("c82d126ebaee9f5d482d4a5dcde628f8d8cc33521014ec866e80af85a0f61cf1", LinkProof.hex(session))
        assertEquals("56ca065c618e088268640dc2628ad4c3", LinkProof.proof(session, "body"))
        assertEquals("5c97f3affe363f31e642b9d4d9dd7568", LinkProof.proof(session, "phone"))
        assertEquals("101112131415161718191a1b1c1d1e1f" to "56ca065c618e088268640dc2628ad4c3", LinkProof.challenge("h 101112131415161718191A1B1C1D1E1F 56ca065c618e088268640dc2628ad4c3"))
        assertNull(LinkProof.challenge("h 1011 56ca"))
        assertNull(LinkProof.challenge("ok"))
    }

    @Test
    fun pairingGivesTheKeyThenChecksTheBodyProvesIt() {
        val body = FakeBody(null)
        var kept: ByteArray? = null
        val result = BodyPairing.pair(body, { kept = it.copyOf(); null }, { message -> kept?.let { hmac(it, message) } }, SecureRandom())
        assertTrue(result.message, result.ok)
        assertTrue(body.proven)
        assertTrue(body.key!!.contentEquals(kept!!))
        assertEquals(32, kept!!.size)
        assertTrue(body.heard.first().startsWith("H "))
        assertTrue(body.heard[1].startsWith("K ") && body.heard[1].length == 66)
    }

    @Test
    fun pairingSaysWhyWhenTheBodyWillNotTakeIt() {
        val refused = BodyPairing.pair(FakeBody(null, takesKeys = false), { null }, { null })
        assertFalse(refused.ok)
        assertTrue(refused.message.contains("USB port"))
        val keystore = BodyPairing.pair(FakeBody(null), { "the keystore was full" }, { null })
        assertFalse(keystore.ok)
        assertTrue(keystore.message.contains("keystore was full"))
        val old = BodyPairing.pair(FakeBody(null, knowsHandshake = false), { null }, { null })
        assertFalse(old.ok)
    }

    @Test
    fun aBodyWithAnotherKeyFailsTheProof() {
        val body = FakeBody(ByteArray(32) { 7 })
        val result = BodyPairing.prove(body, { hmac(ByteArray(32) { 8 }, it) }, SecureRandom())
        assertFalse(result.ok)
        assertTrue(result.message.contains("did not prove"))
        assertFalse(body.heard.any { it.startsWith("V ") })
        val good = BodyPairing.prove(FakeBody(ByteArray(32) { 7 }), { hmac(ByteArray(32) { 7 }, it) }, SecureRandom())
        assertTrue(good.message, good.ok)
        val none = BodyPairing.prove(FakeBody(null), { null }, SecureRandom())
        assertEquals("the body has no key", none.message)
    }
}
