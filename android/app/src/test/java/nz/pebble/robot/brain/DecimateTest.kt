package nz.pebble.robot.brain

import org.json.JSONObject
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.math.PI
import kotlin.math.log10
import kotlin.math.roundToInt
import kotlin.math.sin
import kotlin.math.sqrt

class DecimateTest {
    private val rate = 48_000

    private fun tone(hz: Double, amplitude: Double, seconds: Double = 1.0): ShortArray = ShortArray((rate * seconds).toInt()) { (amplitude * sin(2 * PI * hz * it / rate)).roundToInt().toShort() }

    private fun down(input: ShortArray, chunk: Int = 960, stride: Int = 1, channel: Int = 0, factor: Int = 3): ShortArray {
        val d = Decimate(factor)
        val out = ShortArray(input.size / stride / factor + 8)
        var made = 0
        var at = 0
        val frames = input.size / stride
        while (at < frames) {
            val n = minOf(chunk, frames - at)
            made += d.push(input, at * stride + channel, n, stride, out, made)
            at += n
        }
        return out.copyOf(made)
    }

    private fun rms(values: ShortArray, skip: Int = 200): Double {
        var sum = 0.0
        for (i in skip until values.size) sum += values[i].toDouble() * values[i]
        return sqrt(sum / (values.size - skip))
    }

    private fun gainDb(hz: Double): Double {
        val amplitude = 10_000.0
        return 20 * log10(rms(down(tone(hz, amplitude))) / (amplitude / sqrt(2.0)))
    }

    @Test
    fun theTapsMatchThePythonTwin() {
        val fixture = JSONObject(javaClass.getResource("/hearing/decimate.json")!!.readText())
        for (factor in listOf(2, 3, 6)) {
            val expected = fixture.getJSONObject("taps").getJSONArray(factor.toString())
            val taps = Decimate.design(factor)
            assertEquals(expected.length(), taps.size)
            for (i in taps.indices) assertEquals(expected.getDouble(i), taps[i].toDouble(), 1e-6)
        }
    }

    @Test
    fun theOutputMatchesThePythonTwinWithinOneStep() {
        val fixture = JSONObject(javaClass.getResource("/hearing/decimate.json")!!.readText())
        val input = fixture.getJSONArray("input").let { a -> ShortArray(a.length()) { a.getInt(it).toShort() } }
        val expected = fixture.getJSONArray("output").let { a -> IntArray(a.length()) { a.getInt(it) } }
        val got = down(input, chunk = 333)
        assertEquals(expected.size, got.size)
        for (i in got.indices) assertTrue("sample $i: ${got[i]} vs ${expected[i]}", kotlin.math.abs(got[i] - expected[i]) <= 1)
    }

    @Test
    fun speechFrequenciesPassUnchanged() {
        for (hz in listOf(100.0, 440.0, 1_000.0, 3_100.0, 4_600.0, 6_000.0, 7_000.0)) assertEquals("$hz Hz", 0.0, gainDb(hz), 0.05)
        assertEquals(0.0, gainDb(7_500.0), 1.0)
    }

    @Test
    fun soundAboveEightAndAHalfKilohertzFoldsBackAtLeastSixtyDecibelsDown() {
        for (hz in listOf(8_500.0, 9_000.0, 10_000.0, 12_000.0, 15_000.0, 16_000.0, 17_400.0, 20_000.0, 22_000.0, 23_900.0)) {
            val db = gainDb(hz)
            assertTrue("$hz Hz came through at $db dB", db <= -60.0)
        }
    }

    @Test
    fun chunkSizesDoNotChangeTheOutput() {
        val random = java.util.Random(7)
        val input = ShortArray(48_000) { (random.nextGaussian() * 3_000).roundToInt().toShort() }
        assertArrayEquals(down(input, chunk = 48_000), down(input, chunk = 960))
        assertArrayEquals(down(input, chunk = 960), down(input, chunk = 17))
    }

    @Test
    fun oneChannelIsTakenFromInterleavedStereo() {
        val left = tone(1_000.0, 8_000.0, 0.5)
        val right = tone(2_000.0, 8_000.0, 0.5)
        val both = ShortArray(left.size * 2) { if (it % 2 == 0) left[it / 2] else right[it / 2] }
        assertArrayEquals(down(right), down(both, stride = 2, channel = 1))
        assertArrayEquals(down(left), down(both, stride = 2, channel = 0))
    }

    @Test
    fun aClickComesOutAfterTheFiltersDelay() {
        val input = ShortArray(4_800)
        input[1_200] = 30_000
        val out = down(input)
        val peak = out.indices.maxByOrNull { kotlin.math.abs(out[it].toInt()) }!!
        assertEquals(Math.round((1_200 + Decimate(3).delay - 2) / 3.0).toInt(), peak)
        assertEquals(240, Decimate.taps(3) - 1)
    }

    @Test
    fun ninetySixKilohertzComesDownToo() {
        val input = ShortArray(96_000) { (10_000 * sin(2 * PI * 1_000.0 * it / 96_000)).roundToInt().toShort() }
        val d = Decimate(6)
        val out = ShortArray(16_100)
        var made = 0
        var at = 0
        while (at < input.size) {
            made += d.push(input, at, 1_920, 1, out, made)
            at += 1_920
        }
        assertEquals(16_000, made)
        assertEquals(10_000 / sqrt(2.0), rms(out.copyOf(made)), 10.0)
    }
}
