package nz.pebble.robot.recall

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Test
import java.nio.FloatBuffer

class PoolingTest {
    @Test
    fun rowsArePaddedWithZerosAndMaskedLikeThePc() {
        val padded = Pooling.pad(listOf(intArrayOf(101, 7, 102), intArrayOf(101, 102), intArrayOf(101, 5, 6, 102)))
        assertEquals(3, padded.count)
        assertEquals(4, padded.width)
        assertArrayEquals(longArrayOf(101, 7, 102, 0, 101, 102, 0, 0, 101, 5, 6, 102), padded.ids)
        assertArrayEquals(longArrayOf(1, 1, 1, 0, 1, 1, 0, 0, 1, 1, 1, 1), padded.mask)
        assertArrayEquals(LongArray(12), padded.types)
    }

    @Test
    fun theFirstTokensRowIsTakenAndMadeUnitLength() {
        val hidden = FloatArray(2 * 3 * 2)
        hidden[0] = 3f
        hidden[1] = 4f
        hidden[2] = 100f
        hidden[6] = 0f
        hidden[7] = -2f
        hidden[8] = 9f
        val rows = Pooling.first(FloatBuffer.wrap(hidden), longArrayOf(2, 3, 2))
        assertEquals(2, rows.size)
        assertArrayEquals(floatArrayOf(0.6f, 0.8f), rows[0], 1e-6f)
        assertArrayEquals(floatArrayOf(0f, -1f), rows[1], 1e-6f)
        val flat = Pooling.first(FloatBuffer.wrap(floatArrayOf(0f, 0f, 1f, 1f)), longArrayOf(2, 2))
        assertArrayEquals(floatArrayOf(0f, 0f), flat[0], 0f)
        assertArrayEquals(floatArrayOf(0.70710677f, 0.70710677f), flat[1], 1e-6f)
    }

    @Test
    fun numbersCrossAsLittleEndianFloats() {
        val rows = arrayOf(FloatArray(Pooling.DIM) { it / 1000f }, FloatArray(Pooling.DIM) { -it / 7f })
        val bytes = Pooling.pack(rows)
        assertEquals(2 * Pooling.DIM * 4, bytes.size)
        assertEquals(0x80, bytes[250 * 4 + 2].toInt() and 0xff)
        assertEquals(0x3e, bytes[250 * 4 + 3].toInt() and 0xff)
        val back = Pooling.unpack(bytes)
        assertArrayEquals(rows[0], back[0], 0f)
        assertArrayEquals(rows[1], back[1], 0f)
        assertEquals(1.0, Pooling.cosine(rows[0], rows[0]), 1e-9)
        assertEquals(0.0, Pooling.cosine(FloatArray(3), floatArrayOf(1f, 0f, 0f)), 0.0)
    }
}
