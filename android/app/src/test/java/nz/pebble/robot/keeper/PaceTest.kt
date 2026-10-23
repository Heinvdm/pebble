package nz.pebble.robot.keeper

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File

class PaceTest {
    @get:Rule
    val folder = TemporaryFolder()

    @Test
    fun heatRisesAtOnceAndFallsOnlyAfterTwoCoolMinutes() {
        val heat = HeatLevel()
        assertEquals(HeatLevel.COOL, heat.update(0, 0.3, 0))
        assertEquals(HeatLevel.WARM, heat.update(1_000, 0.65, 0))
        assertEquals(HeatLevel.HOT, heat.update(2_000, Double.NaN, 3))
        assertEquals(HeatLevel.HOT, heat.update(3_000, 0.2, 0))
        assertEquals(HeatLevel.HOT, heat.update(100_000, 0.2, 0))
        assertEquals(HeatLevel.HOT, heat.update(110_000, 0.9, 0))
        assertEquals(HeatLevel.HOT, heat.update(120_000, 0.2, 0))
        assertEquals(HeatLevel.COOL, heat.update(240_000, 0.2, 0))
        assertEquals(HeatLevel.WARM, HeatLevel.raw(Double.NaN, 2))
        assertEquals(1.0, HeatLevel.eyesFactor(HeatLevel.COOL, false), 0.0)
        assertEquals(0.6, HeatLevel.eyesFactor(HeatLevel.COOL, true), 0.0)
        assertEquals(0.35, HeatLevel.eyesFactor(HeatLevel.HOT, false), 0.0)
    }

    private fun counters(predicted: Double, seconds: Double) = mapOf("tokens_predicted_total" to predicted, "tokens_predicted_seconds_total" to seconds, "prompt_tokens_total" to predicted * 5, "prompt_seconds_total" to seconds)

    @Test
    fun answersThirtyPercentSlowerThanTheBenchAreSlow() {
        val watch = SpeedWatch()
        assertFalse(watch.slow(6.0))
        watch.add(0, counters(0.0, 0.0))
        watch.add(60_000, counters(50.0, 10.0))
        assertNull(watch.writeTps())
        watch.add(120_000, counters(200.0, 50.0))
        assertEquals(4.0, watch.writeTps()!!, 1e-9)
        assertTrue(watch.slow(6.0))
        assertFalse(watch.slow(5.0))
        assertFalse(watch.slow(null))
        watch.add(180_000, counters(10.0, 2.0))
        assertNull(watch.writeTps())
    }

    @Test
    fun thePaceFileTellsTheEyesHowFastToLook() {
        val file = File(folder.root, PaceFile.NAME)
        PaceFile.write(file, JSONObject().put("headroom", 0.9).put("status", 3).put("level", HeatLevel.HOT), false)
        assertEquals(0.35, PaceReader(file).eyesFactor(), 1e-9)
        PaceFile.write(file, JSONObject().put("level", HeatLevel.COOL), true)
        assertEquals(0.6, PaceReader(file, 0).eyesFactor(), 1e-9)
        assertEquals(1.0, PaceReader(File(folder.root, "missing.json")).eyesFactor(), 1e-9)
        file.writeText(JSONObject().put("eyes", 0.35).put("at", 1L).toString())
        assertEquals(1.0, PaceReader(file).eyesFactor(), 1e-9)
    }
}
