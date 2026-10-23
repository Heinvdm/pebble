package nz.pebble.robot.brain

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.math.PI
import kotlin.math.sin

class MicProbeMathTest {
    private val rate = 48_000

    @Test
    fun aClickHeardHalfAMillisecondLaterOnOneChannelGivesItsDelay() {
        val click = ProbeMath.click(rate, 0.5)
        val a = FloatArray(4_000)
        val b = FloatArray(4_000)
        for (j in click.indices) {
            a[1_000 + j] = click[j]
            b[1_022 + j] = click[j] * 0.8f
        }
        val (lag, peak) = ProbeMath.delay(a, b, 48)
        assertEquals(22.0, lag, 0.3)
        assertTrue(peak > 0.9)
        val (start, _) = ProbeMath.onset(a, click, 500, 2_000)
        assertEquals(1_000, start)
    }

    @Test
    fun clicksThatSwapSidesGiveTheSpacing() {
        val spacing = ProbeMath.spacing(listOf(21.7, -21.5, 0.1), rate)
        assertEquals(0.155, spacing!!, 0.003)
        assertNull(ProbeMath.spacing(listOf(0.2, -0.3), rate))
        assertNull(ProbeMath.spacing(listOf(20.0, 21.0), rate))
    }

    @Test
    fun aFloorThatFallsOffAtEightKilohertzIsACliff() {
        val flat = DoubleArray(24) { -90.0 }
        val cliff = DoubleArray(24) { if (it < 8) -80.0 else -130.0 }
        assertTrue(!ProbeMath.cliff(flat))
        assertTrue(ProbeMath.cliff(cliff))
    }

    @Test
    fun theSweepShowsWhereThePathStops() {
        val rise = DoubleArray(24) { if (it in 10..19) 25.0 else 1.0 }
        assertEquals(19, ProbeMath.top(rise, 10))
        assertEquals(-1, ProbeMath.top(DoubleArray(24), 10))
    }

    @Test
    fun aToneLandsInItsBand() {
        val tone = FloatArray(rate) { (0.1 * sin(2 * PI * 17_400.0 * it / rate)).toFloat() }
        val bands = ProbeMath.bands(tone, rate)
        assertEquals(24, bands.size)
        val loudest = bands.indices.maxByOrNull { bands[it] }!!
        assertEquals(17, loudest)
        assertTrue(bands[17] - bands[10] > 60)
    }

    @Test
    fun theSweepClimbsAndFadesAtItsEnds() {
        val sweep = ProbeMath.sweep(rate, 1.0, 10_000.0, 20_000.0, 0.05)
        assertEquals(rate, sweep.size)
        assertEquals(0f, sweep[0], 1e-6f)
        assertTrue(sweep.maxOrNull()!! <= 0.05f + 1e-6f)
        val early = ProbeMath.bands(sweep.copyOfRange(0, rate / 4), rate)
        val late = ProbeMath.bands(sweep.copyOfRange(rate * 3 / 4, rate), rate)
        assertTrue(early.indices.maxByOrNull { early[it] }!! < late.indices.maxByOrNull { late[it] }!!)
    }
}
