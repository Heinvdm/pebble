package nz.pebble.robot.brain

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class SoundVectorsTest {
    private fun vector(seed: Int) = FloatArray(SoundVectors.SIZE) { ((it * 31 + seed * 7) % 97) / 10f - 2f }

    @Test
    fun halfFloatsMatchPythonsStructPackingBitForBit() {
        val cases = listOf(
            1.0f to 0x3C00, -2.0f to 0xC000, 65504f to 0x7BFF, Math.scalb(1f, -14) to 0x0400, Math.scalb(1f, -24) to 0x0001,
            0.1f to 0x2E66, (1f / 3f) to 0x3555, -0.0f to 0x8000, 1e-8f to 0x0000, 3e-5f to 0x01F7, 2.5e-7f to 0x0004,
            1.0009765625f to 0x3C01, 1.00048828125f to 0x3C00, 1.00146484375f to 0x3C02, Math.scalb(1f, -25) to 0x0000,
            3 * Math.scalb(1f, -26) to 0x0001, 6.04248046875e-05f to 0x03F6, 1234.5678f to 0x64D3, -7.123f to 0xC71F,
        )
        for ((value, bits) in cases) assertEquals("$value", bits, HalfFloats.bits(value))
    }

    @Test
    fun halfFloatsNeverBecomeInfinity() {
        assertEquals(0x7BFF, HalfFloats.bits(1e9f))
        assertEquals(0xFBFF, HalfFloats.bits(-1e9f))
    }

    @Test
    fun theTextIsLittleEndianBase64AsPythonWritesIt() {
        assertEquals("f16:ADwAwA==", HalfFloats.text(floatArrayOf(1f, -2f)))
        assertEquals("f16:ADgAtABCZi4=", HalfFloats.text(floatArrayOf(0.5f, -0.25f, 3f, 0.1f)))
    }

    @Test
    fun aVectorComesBackWithinHalfPrecision() {
        val values = vector(3)
        val back = HalfFloats.unpack(HalfFloats.pack(values))
        assertEquals(values.size, back.size)
        for (i in values.indices) assertEquals(values[i], back[i], Math.abs(values[i]) / 1024f + 1e-6f)
        assertEquals(2 * SoundVectors.SIZE, HalfFloats.pack(values).size)
    }

    @Test
    fun nothingIsKeptUntilTheBrainAsks() {
        val ring = SoundVectors()
        ring.add(1_000.0, vector(1), 1_000.0)
        val first = ring.read(1L shl 62, 2_000.0)
        assertEquals(0, first.getLong("total"))
        assertEquals(0, first.getJSONArray("rows").length())
        ring.add(2_480.0, vector(2), 2_480.0)
        val second = ring.read(0, 2_500.0)
        assertEquals(1, second.getLong("total"))
        val row = second.getJSONArray("rows").getJSONArray(0)
        assertEquals(2_480.0, row.getDouble(0), 0.0)
        assertTrue(row.getString(1).startsWith("f16:"))
        assertEquals(2_500.0, second.getDouble("now_ms"), 0.0)
    }

    @Test
    fun theRingHoldsThirtySecondsAndReadsFromAPosition() {
        val ring = SoundVectors()
        ring.read(1L shl 62, 0.0)
        for (i in 0 until 100) ring.add(i * 480.0, vector(i), i * 480.0)
        val all = ring.read(0, 48_000.0)
        assertEquals(100, all.getLong("total"))
        assertEquals(37, all.getLong("from"))
        assertEquals(SoundVectors.KEEP, all.getJSONArray("rows").length())
        assertTrue(SoundVectors.KEEP * 0.48 >= 30.0)
        val tail = ring.read(90, 48_000.0)
        assertEquals(10, tail.getJSONArray("rows").length())
        assertEquals(90 * 480.0, tail.getJSONArray("rows").getJSONArray(0).getDouble(0), 0.0)
        val decoded = java.util.Base64.getDecoder().decode(tail.getJSONArray("rows").getJSONArray(0).getString(1).removePrefix("f16:"))
        assertArrayEquals(HalfFloats.pack(vector(90)), decoded)
    }

    @Test
    fun theBrainsReaderSeesTheLastTwentyFourThenOnlyNewRows() {
        val ring = SoundVectors()
        ring.read(1L shl 62, 0.0)
        for (i in 0 until 40) ring.add(i * 480.0, vector(i), i * 480.0)
        val total = ring.read(1L shl 62, 20_000.0).getLong("total")
        var position = maxOf(0L, total - 24)
        val first = ring.read(position, 20_000.0)
        assertEquals(24, first.getJSONArray("rows").length())
        position = first.getLong("total")
        ring.add(40 * 480.0, vector(40), 20_100.0)
        val next = ring.read(position, 20_200.0)
        assertEquals(1, next.getJSONArray("rows").length())
    }

    @Test
    fun aMinuteWithoutAskingEmptiesTheRing() {
        val ring = SoundVectors()
        ring.read(1L shl 62, 0.0)
        ring.add(100.0, vector(1), 100.0)
        ring.add(70_000.0, vector(2), 70_000.0)
        val after = ring.read(0, 70_100.0)
        assertEquals(0, after.getInt("kept"))
        assertEquals(1, after.getLong("total"))
        ring.add(70_200.0, vector(3), 70_200.0)
        assertEquals(1, ring.read(after.getLong("total"), 70_300.0).getJSONArray("rows").length())
    }

    @Test
    fun brokenVectorsAreLeftOut() {
        val ring = SoundVectors()
        ring.read(1L shl 62, 0.0)
        ring.add(1.0, FloatArray(10), 1.0)
        ring.add(2.0, vector(1).also { it[5] = Float.NaN }, 2.0)
        assertEquals(0, ring.read(0, 3.0).getLong("total"))
    }
}
