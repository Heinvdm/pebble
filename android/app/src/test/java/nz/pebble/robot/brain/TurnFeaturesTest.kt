package nz.pebble.robot.brain

import org.json.JSONArray
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.nio.ByteBuffer
import java.nio.ByteOrder
import kotlin.math.abs

class TurnFeaturesTest {
    private fun bytes(name: String): ByteArray = javaClass.getResourceAsStream("/turn/$name")!!.readBytes()

    private fun speech(): FloatArray {
        val buffer = ByteBuffer.wrap(bytes("speech.pcm")).order(ByteOrder.LITTLE_ENDIAN).asShortBuffer()
        return FloatArray(buffer.remaining()) { buffer.get(it) / 32768f }
    }

    @Test
    fun theFeaturesMatchWhispersOwnExtractor() {
        val audio = speech()
        val cases = JSONArray(String(bytes("cases.json")))
        assertTrue(cases.length() >= 2)
        for (i in 0 until cases.length()) {
            val case = cases.getJSONObject(i)
            val want = ByteBuffer.wrap(bytes(case.getString("file"))).order(ByteOrder.LITTLE_ENDIAN).asFloatBuffer()
            val got = TurnFeatures.features(TurnFeatures.lastSeconds(audio, case.getInt("samples")))
            assertEquals(TurnFeatures.MELS * TurnFeatures.FRAMES, got.size)
            assertEquals(got.size, want.remaining())
            var worst = 0.0
            for (k in got.indices) worst = maxOf(worst, abs(got[k] - want.get(k)).toDouble())
            assertTrue("${case.getString("name")}: worst difference $worst", worst < 1e-4)
        }
    }

    @Test
    fun shortSoundIsPaddedAtTheStartAndLongSoundKeepsItsEnd() {
        val short = TurnFeatures.lastSeconds(FloatArray(10) { 1f })
        assertEquals(TurnFeatures.SAMPLES, short.size)
        assertEquals(0f, short[0])
        assertEquals(1f, short[TurnFeatures.SAMPLES - 1])
        val long = FloatArray(TurnFeatures.SAMPLES + 5) { it.toFloat() }
        val kept = TurnFeatures.lastSeconds(long)
        assertEquals(5f, kept[0])
        assertEquals((TurnFeatures.SAMPLES + 4).toFloat(), kept[TurnFeatures.SAMPLES - 1])
        val part = TurnFeatures.lastSeconds(long, 100)
        assertEquals(99f, part[TurnFeatures.SAMPLES - 1])
        assertEquals(0f, part[TurnFeatures.SAMPLES - 101])
    }
}
