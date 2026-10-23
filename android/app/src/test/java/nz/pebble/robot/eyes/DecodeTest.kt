package nz.pebble.robot.eyes

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.nio.ByteBuffer
import java.nio.ByteOrder
import kotlin.math.max
import kotlin.math.min

class DecodeTest {
    private val index = JSONObject(text("index.json"))

    private fun text(name: String): String = javaClass.getResourceAsStream("/decode/$name")!!.bufferedReader().readText()

    private fun floats(name: String): FloatArray {
        val bytes = javaClass.getResourceAsStream("/decode/$name")!!.readBytes()
        val buffer = ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN).asFloatBuffer()
        return FloatArray(buffer.remaining()).also { buffer.get(it) }
    }

    private fun rows(a: JSONArray): List<DoubleArray> = (0 until a.length()).map { i -> a.getJSONArray(i).let { r -> DoubleArray(r.length()) { r.getDouble(it) } } }

    private fun same(expected: List<DoubleArray>, got: List<Det>, tolerance: Double, withClass: Boolean) {
        assertEquals("how many", expected.size, got.size)
        val left = expected.sortedByDescending { it[4] }
        val right = got.sortedByDescending { it.score }
        for ((e, g) in left.zip(right)) {
            assertEquals(e[0], g.x.toDouble(), tolerance)
            assertEquals(e[1], g.y.toDouble(), tolerance)
            assertEquals(e[2], g.w.toDouble(), tolerance)
            assertEquals(e[3], g.h.toDouble(), tolerance)
            assertEquals(e[4], g.score.toDouble(), 1e-4)
            if (withClass) assertEquals(e[5].toInt(), g.cls)
        }
    }

    @Test
    fun nanodetMatchesThePythonEyes() {
        for (picture in index.keys()) {
            val case = index.getJSONObject(picture).getJSONObject("nanodet")
            val rw = case.getInt("rw")
            val rh = case.getInt("rh")
            val scores = HashMap<Int, FloatArray>()
            val boxes = HashMap<Int, FloatArray>()
            val tensors = case.getJSONArray("tensors")
            for (i in 0 until tensors.length()) {
                val t = tensors.getJSONObject(i)
                val shape = t.getJSONArray("shape")
                val data = floats(t.getString("file"))
                val last = shape.getInt(shape.length() - 1)
                if (last == Decode.NANODET_CLASSES) scores[shape.getInt(1)] = data else boxes[shape.getInt(1)] = data
            }
            val got = Decode.nanodet(scores, boxes, rw, rh, 0.4f, 0.45f).map {
                val x0 = it.x / rw
                val y0 = it.y / rh
                Det(x0, y0, min(1f - x0, it.w / rw), min(1f - y0, it.h / rh), it.score, it.cls)
            }
            same(rows(case.getJSONArray("expected")), got, 1e-3, true)
        }
    }

    @Test
    fun yunetMatchesOpenCvsFaceDetector() {
        var faces = 0
        for (picture in index.keys()) {
            val case = index.getJSONObject(picture).getJSONObject("yunet")
            val tensors = case.getJSONObject("tensors")
            fun part(kind: String) = Decode.YUNET_STRIDES.map { floats(tensors.getJSONObject("${kind}_$it").getString("file")) }
            val got = Decode.yunet(part("cls"), part("obj"), part("bbox"), 640, 640, 0.6f, kps = part("kps"))
            val expected = rows(case.getJSONArray("expected"))
            faces += expected.size
            same(expected, got, 0.05, false)
            for ((e, g) in expected.sortedByDescending { it[4] }.zip(got.sortedByDescending { it.score })) {
                val marks = g.marks!!
                for (j in 0 until 10) assertEquals(e[5 + j], marks[j].toDouble(), 0.05)
            }
        }
        assertTrue(faces >= 1)
    }

    @Test
    fun yoloeMatchesTheSlowLane() {
        for (picture in index.keys()) {
            val case = index.getJSONObject(picture).getJSONObject("yoloe")
            val t = case.getJSONArray("tensors").getJSONObject(0)
            val shape = t.getJSONArray("shape")
            val channels = shape.getInt(0)
            val anchors = shape.getInt(1)
            val k = case.getDouble("k")
            val left = case.getInt("left")
            val top = case.getInt("top")
            val w = case.getInt("width")
            val h = case.getInt("height")
            val got = Decode.yoloe(floats(t.getString("file")), channels, anchors, case.getInt("classes"), 0.45f).mapNotNull {
                val x0 = max(0.0, (it.x - left) / k / w)
                val y0 = max(0.0, (it.y - top) / k / h)
                val x2 = min(1.0, (it.x + it.w - left) / k / w)
                val y2 = min(1.0, (it.y + it.h - top) / k / h)
                if (x2 <= x0 || y2 <= y0) null else Det(x0.toFloat(), y0.toFloat(), (x2 - x0).toFloat(), (y2 - y0).toFloat(), it.score, it.cls)
            }
            same(rows(case.getJSONArray("expected")), got, 1e-3, true)
        }
    }

    @Test
    fun overlappingBoxesKeepTheBestOne() {
        val a = Det(0f, 0f, 10f, 10f, 0.9f, 1)
        val b = Det(1f, 1f, 10f, 10f, 0.8f, 1)
        val c = Det(1f, 1f, 10f, 10f, 0.7f, 2)
        assertEquals(listOf(a), Decode.nms(listOf(b, a, c), 0.5f))
        assertEquals(listOf(a, c), Decode.nms(listOf(b, a, c), 0.5f, perClass = true))
    }
}
