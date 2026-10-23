package nz.pebble.robot.brain

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.math.abs

class BrainPartsTest {
    @Test
    fun aSensorRingHandsOutEachSampleOnceAndKeepsTheNewest() {
        val ring = SensorRing("accel", 3, 4)
        for (i in 0 until 6) ring.add(i * 20.0, floatArrayOf(i.toFloat(), 0f, 9.8f))
        val all = ring.read(0, 100, 200.0)
        assertEquals(6L, all.getLong("total"))
        assertEquals(2L, all.getLong("from"))
        val rows = all.getJSONArray("rows")
        assertEquals(4, rows.length())
        assertEquals(40.0, rows.getJSONArray(0).getDouble(0), 0.0)
        assertEquals(5.0, rows.getJSONArray(3).getDouble(1), 0.0)
        assertEquals(200.0, all.getDouble("now_ms"), 0.0)
        assertEquals(0, ring.read(6, 100, 200.0).getJSONArray("rows").length())
        assertArrayEquals(floatArrayOf(5f, 0f, 9.8f), ring.latest(), 0f)
    }

    @Test
    fun theSoundTapKeepsTheLastSecondsAsLittleEndianPcm() {
        val tap = SoundTap(seconds = 1, rate = 8)
        tap.onAudio(shortArrayOf(1, -2, 300, 4, 5, 6, 7, 8, 9, 10), 10, false)
        val info = tap.info(true)
        assertEquals(10L, info.getLong("total"))
        assertEquals(8L, info.getLong("kept"))
        val bytes = tap.read(0, 3)
        assertEquals(6, bytes.size)
        assertEquals(300, (bytes[0].toInt() and 0xFF) or (bytes[1].toInt() shl 8))
        assertEquals(0, tap.read(10, 5).size)
    }

    @Test
    fun theSirenAlternatesTwoLowTonesWithoutClicks() {
        val wave = Alarm.siren()
        assertEquals(Alarm.RATE, wave.size)
        assertTrue(abs(wave[0].toInt()) < 200)
        assertTrue(abs(wave[Alarm.RATE / 2].toInt()) < 200)
        fun crossings(from: Int, to: Int) = (from + 1 until to).count { (wave[it - 1] < 0) != (wave[it] < 0) }
        val low = crossings(0, Alarm.RATE / 2)
        val high = crossings(Alarm.RATE / 2, Alarm.RATE)
        assertTrue(low in 640..660)
        assertTrue(high in 940..960)
    }

    @Test
    fun soundWindowsComeAtTheAgreedCadenceInOrder() {
        val windows = SoundWindows(window = 10, hop = 4)
        val ends = ArrayList<Pair<Float, Float>>()
        var sample = 0
        repeat(5) {
            val chunk = ShortArray(5) { (sample + it).toShort() }
            sample += 5
            windows.add(chunk, 5) { w, _ -> ends += (w.first() * 32768f) to (w.last() * 32768f) }
        }
        assertEquals(listOf(0f to 9f, 4f to 13f, 8f to 17f, 12f to 21f), ends)
        windows.reset()
        ends.clear()
        windows.add(ShortArray(9), 9) { w, _ -> ends += w.first() to w.last() }
        assertTrue(ends.isEmpty())
    }

    @Test
    fun aWrappedKeyBlobIsCheckedBeforeUse() {
        val blob = byteArrayOf(1, 12) + ByteArray(12) { it.toByte() } + ByteArray(48)
        val parts = KeyVault.Blob.parse(blob)
        assertEquals(12, parts.iv.size)
        assertEquals(48, parts.sealed.size)
        for (bad in listOf(byteArrayOf(2, 12) + ByteArray(60), byteArrayOf(1, 12) + ByteArray(20), ByteArray(1))) {
            try {
                KeyVault.Blob.parse(bad)
                throw AssertionError("should have refused")
            } catch (e: IllegalArgumentException) {
                assertTrue(e.message!!.isNotEmpty())
            }
        }
    }
}
