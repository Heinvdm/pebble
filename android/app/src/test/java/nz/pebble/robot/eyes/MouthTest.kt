package nz.pebble.robot.eyes

import org.json.JSONArray
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.nio.ByteBuffer
import java.nio.ByteOrder

class MouthTest {
    private val cases = JSONArray(javaClass.getResourceAsStream("/decode/mouths.json")!!.bufferedReader().readText())

    private fun floats(name: String): FloatArray {
        val bytes = javaClass.getResourceAsStream("/decode/$name")!!.readBytes()
        val buffer = ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN).asFloatBuffer()
        return FloatArray(buffer.remaining()).also { buffer.get(it) }
    }

    private fun doubles(a: JSONArray): DoubleArray = DoubleArray(a.length()) { a.getDouble(it) }

    @Test
    fun theCropMatchesThePythonEyes() {
        assertTrue(cases.length() >= 3)
        for (i in 0 until cases.length()) {
            val case = cases.getJSONObject(i)
            val expected = doubles(case.getJSONArray("matrix"))
            val got = Mouth.crop(doubles(case.getJSONArray("marks")))!!
            for (k in 0 until 6) assertEquals(case.getString("picture"), expected[k], got[k], 1e-4)
        }
    }

    @Test
    fun theLipShapeMatchesThePythonEyes() {
        for (i in 0 until cases.length()) {
            val case = cases.getJSONObject(i)
            val expected = doubles(case.getJSONArray("shape"))
            val got = Mouth.shape(floats(case.getString("points")))!!
            assertEquals(expected[0], got[0], 1e-9)
            assertEquals(expected[1], got[1], 1e-9)
        }
    }

    @Test
    fun tinyOrMarklessFacesAreNotRead() {
        val marks = FloatArray(10) { 0.5f }
        val faces = listOf(
            Det(0.1f, 0.1f, 0.02f, 0.03f, 0.9f, marks = marks),
            Det(0.3f, 0.1f, 0.2f, 0.3f, 0.9f),
            Det(0.5f, 0.1f, 0.1f, 0.15f, 0.8f, marks = marks),
            Det(0.6f, 0.4f, 0.3f, 0.4f, 0.7f, marks = marks),
            Det(0.0f, 0.5f, 0.08f, 0.1f, 0.9f, marks = marks),
        )
        assertEquals(listOf(3, 2), Mouth.pick(faces, 640, Mouth.MIN_FACE_PX, 2))
        assertEquals(listOf(3, 2, 4), Mouth.pick(faces, 640, Mouth.MIN_FACE_PX, 4))
        assertNull(Mouth.crop(DoubleArray(10) { 5.0 }))
        assertNull(Mouth.shape(FloatArray(Mouth.POINTS * 3)))
        val px = Mouth.pixels(FloatArray(10) { if (it % 2 == 0) 0.5f else 0.25f }, 640, 480)
        assertEquals(320.0, px[0], 1e-9)
        assertEquals(120.0, px[1], 1e-9)
    }
}
