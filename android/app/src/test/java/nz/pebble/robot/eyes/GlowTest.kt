package nz.pebble.robot.eyes

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.util.Base64

class GlowTest {
    private fun cells(vararg values: Int): ByteArray = ByteArray(values.size) { values[it].toByte() }

    @Test
    fun warmCountsOnlyBrightSaturatedReds() {
        val hsv = cells(
            22, 110, 190,
            23, 110, 190,
            170, 255, 255,
            169, 255, 255,
            0, 109, 255,
            0, 255, 189,
            179, 200, 200,
            90, 255, 255,
        )
        assertEquals(3.0 / 8.0, Glow.warm(hsv), 1e-12)
        assertEquals(0.0, Glow.warm(ByteArray(0)), 0.0)
    }

    @Test
    fun brightestIsTheLargestChannelOfEachCell() {
        val bgr = cells(10, 200, 30, 255, 0, 0, 0, 0, 0, 128, 129, 127)
        assertArrayEquals(cells(200, 255, 0, 129), Glow.brightest(bgr))
    }

    @Test
    fun aWholeGlowGridTravelsAsBase64() {
        val grid = ByteArray(Glow.CELLS) { (it % 256).toByte() }
        val text = Glow.encode(grid)
        assertEquals(6400, text.length)
        assertFalse(text.contains("="))
        assertArrayEquals(grid, Base64.getDecoder().decode(text))
    }

    @Test
    fun theHazardSettingsComeFromTheBrain() {
        val base = "{\"cameras\": {}, \"slow\": {\"on\": true, \"classes\": 2013}}"
        val off = Eyes.Settings.parse(base, "")
        assertFalse(off.hazardsOn)
        assertEquals(0, off.hazardClasses)
        val on = Eyes.Settings.parse("{\"cameras\": {}, \"hazards\": {\"on\": true, \"every_s\": 0.01, \"score\": 0.3, \"threads\": 9, \"classes\": 21}}", "")
        assertTrue(on.hazardsOn)
        assertEquals(HazardLane.MIN_S, on.hazardEvery, 0.0)
        assertEquals(0.3f, on.hazardScore, 1e-6f)
        assertEquals(4, on.hazardThreads)
        assertEquals(21, on.hazardClasses)
        assertEquals(HazardLane.DEFAULT_S, Eyes.Settings.parse("{\"cameras\": {}, \"hazards\": {\"on\": true}}", "").hazardEvery, 0.0)
    }
}
