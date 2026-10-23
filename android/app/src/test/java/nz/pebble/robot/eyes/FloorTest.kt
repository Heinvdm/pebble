package nz.pebble.robot.eyes

import org.json.JSONArray
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.nio.ByteBuffer
import java.nio.ByteOrder

class FloorTest {
    private val cases = JSONArray(javaClass.getResourceAsStream("/floor/index.json")!!.bufferedReader().readText())

    private fun floats(name: String): FloatArray {
        val bytes = javaClass.getResourceAsStream("/floor/$name")!!.readBytes()
        val buffer = ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN).asFloatBuffer()
        return FloatArray(buffer.remaining()).also { buffer.get(it) }
    }

    @Test
    fun theRaysMatchThePythonEyes() {
        assertTrue(cases.length() >= 9)
        var models = 0
        for (i in 0 until cases.length()) {
            val case = cases.getJSONObject(i)
            val name = case.getString("name")
            if (name.startsWith("model_")) models++
            val got = Floor.rays(floats(case.getString("file")), case.getInt("rows"), case.getInt("cols"), case.getDouble("fov"), case.getDouble("height"), case.getDouble("pitch"), case.getInt("bins"), case.getDouble("reach"))
            if (case.isNull("rays")) {
                assertNull(name, got)
                continue
            }
            assertNotNull(name, got)
            val want = case.getJSONArray("rays")
            assertEquals(name, case.getDouble("quality"), got!!.quality, 1e-9)
            assertEquals(name, want.length(), got.rays.size)
            var differ = 0
            for (k in 0 until want.length()) {
                val row = want.getJSONArray(k)
                val ray = got.rays[k]
                assertEquals("$name ray $k bearing", row.getDouble(0), ray.bearing, 0.005 + 1e-7)
                assertEquals("$name ray $k distance", row.getDouble(1), ray.distance, 0.0005 + 1e-7)
                assertEquals("$name ray $k score", row.getDouble(2), ray.score, 0.0005 + 1e-7)
                if (round(ray.bearing, 2) != row.getDouble(0) || round(ray.distance, 3) != row.getDouble(1) || round(ray.score, 3) != row.getDouble(2)) differ++
            }
            assertTrue("$name: $differ rays differ from Python's after rounding", differ <= 1)
        }
        assertTrue("the fixtures carry depth maps from the real model", models >= 3)
    }

    @Test
    fun theHalfSizeModelGivesThePcModelsFloor() {
        val halves = JSONArray(javaClass.getResourceAsStream("/floor/half.json")!!.bufferedReader().readText())
        assertTrue(halves.length() >= 8)
        var worst = 0.0
        for (i in 0 until halves.length()) {
            val case = halves.getJSONObject(i)
            val name = case.getString("name")
            val got = Floor.rays(floats(case.getString("file")), case.getInt("rows"), case.getInt("cols"), case.getDouble("fov"), case.getDouble("height"), case.getDouble("pitch"), case.getInt("bins"), case.getDouble("reach"))
            if (case.isNull("full_rays")) {
                assertNull(name, got)
                continue
            }
            assertNotNull(name, got)
            val want = case.getJSONArray("full_rays")
            val tolerance = case.getDouble("tolerance_m")
            assertEquals(name, case.getDouble("full_quality"), got!!.quality, case.getDouble("quality_tolerance"))
            assertEquals(name, want.length(), got.rays.size)
            for (k in 0 until want.length()) {
                val full = want.getJSONArray(k).getDouble(1)
                val half = got.rays[k].distance
                assertEquals("$name ray $k is open in one model and not the other", full == Floor.OPEN_M, half == Floor.OPEN_M)
                assertEquals("$name ray $k distance", full, half, tolerance)
                worst = maxOf(worst, Math.abs(full - half))
            }
        }
        assertTrue("worst ray $worst m", worst < 0.05)
    }

    private fun round(value: Double, places: Int): Double = java.math.BigDecimal(value).setScale(places, java.math.RoundingMode.HALF_EVEN).toDouble()

    @Test
    fun aPictureWithNoFloorGivesNoRays() {
        assertNull(Floor.rays(FloatArray(Floor.ROWS * Floor.COLS) { 1f }, Floor.ROWS, Floor.COLS, 70.0, 0.14, 8.0))
        assertNull(Floor.rays(FloatArray(Floor.ROWS * Floor.COLS) { 1f }, Floor.ROWS, Floor.COLS, 70.0, 0.14, -60.0))
    }

    @Test
    fun mediansWorkLikeNumpy() {
        assertEquals(2.0, Floor.median(doubleArrayOf(3.0, 1.0, 2.0)), 0.0)
        assertEquals(2.5, Floor.median(doubleArrayOf(4.0, 1.0, 3.0, 2.0)), 0.0)
        assertTrue(Floor.median(doubleArrayOf(1.0, Double.NaN, 2.0)).isNaN())
        assertEquals(Float.POSITIVE_INFINITY, Floor.median(floatArrayOf(1f, Float.POSITIVE_INFINITY, Float.POSITIVE_INFINITY, 2f)))
        assertTrue(Floor.median(doubleArrayOf(Double.NEGATIVE_INFINITY, Double.POSITIVE_INFINITY)).isNaN())
    }

    @Test
    fun theGateFallsBackToMoving() {
        assertEquals(Floor.ALWAYS, Floor.gate("always"))
        assertEquals(Floor.OFF, Floor.gate("off"))
        assertEquals(Floor.MOVING, Floor.gate("sometimes"))
        assertEquals(Floor.MOVING, Floor.gate(null))
    }

    @Test
    fun aFloorPointIsWhereTheGeometryPutsIt() {
        val spot = Floor.floorPoint(0.5, 1.0, 640, 480, 70.0, 0.14, 0.0)!!
        val f = 320 / Math.tan(Math.toRadians(35.0))
        assertEquals(0.14 * f / 240, spot[0], 1e-9)
        assertEquals(0.0, spot[1], 1e-9)
        assertNull(Floor.floorPoint(0.5, 0.2, 640, 480, 70.0, 0.14, 0.0))
    }
}
