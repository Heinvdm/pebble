package nz.pebble.robot.eyes

import org.opencv.core.CvType
import org.opencv.core.Mat
import org.opencv.core.Rect
import org.opencv.core.Size
import org.opencv.imgproc.Imgproc
import kotlin.math.ceil
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sqrt

class PoseFinder(private val runner: Runner) : AutoCloseable {
    val backend get() = runner.backend

    fun points(bgr: Mat, box: Det): FloatArray {
        val w = bgr.cols().toDouble()
        val h = bgr.rows().toDouble()
        val x0 = box.x * w
        val y0 = box.y * h
        val x1 = (box.x + box.w) * w
        val y1 = (box.y + box.h) * h
        val cx = (x0 + x1) / 2
        val cy = (y0 + y1) / 2
        var bw = (x1 - x0) * PADDING
        var bh = (y1 - y0) * PADDING
        val aspect = WIDTH.toDouble() / HEIGHT
        if (bw > bh * aspect) bh = bw / aspect else bw = bh * aspect
        val k = WIDTH / bw
        val warp = Mat(2, 3, CvType.CV_64F)
        warp.put(0, 0, k, 0.0, WIDTH / 2 - k * cx, 0.0, k, HEIGHT / 2 - k * cy)
        val crop = Mat()
        Imgproc.warpAffine(bgr, crop, warp, Size(WIDTH.toDouble(), HEIGHT.toDouble()), Imgproc.INTER_LINEAR)
        Imgproc.cvtColor(crop, crop, Imgproc.COLOR_BGR2RGB)
        val pixels = Pixels.floats(crop)
        crop.release()
        warp.release()
        for (i in pixels.indices) pixels[i] = (pixels[i] - MEAN[i % 3]) / STD[i % 3]
        val outputs = runner.run(Pixels.chw(pixels, HEIGHT, WIDTH), HEIGHT, WIDTH)
        val sx = outputs.firstOrNull { it.name == "simcc_x" } ?: outputs[0]
        val sy = outputs.firstOrNull { it.name == "simcc_y" } ?: outputs[1]
        return decode(sx.data, sy.data, POINTS, cx, cy, bw, bh, w, h)
    }

    override fun close() = runner.close()

    companion object {
        const val WIDTH = 192
        const val HEIGHT = 256
        const val POINTS = 17
        const val PADDING = 1.25
        const val SPLIT = 2.0
        val MEAN = floatArrayOf(123.675f, 116.28f, 103.53f)
        val STD = floatArrayOf(58.395f, 57.12f, 57.375f)

        fun decode(simccX: FloatArray, simccY: FloatArray, count: Int, cx: Double, cy: Double, bw: Double, bh: Double, w: Double, h: Double): FloatArray {
            val nx = simccX.size / count
            val ny = simccY.size / count
            val out = FloatArray(count * 3)
            for (p in 0 until count) {
                var bx = 0
                var mx = Float.NEGATIVE_INFINITY
                for (i in 0 until nx) {
                    val v = simccX[p * nx + i]
                    if (v > mx) {
                        mx = v
                        bx = i
                    }
                }
                var by = 0
                var my = Float.NEGATIVE_INFINITY
                for (i in 0 until ny) {
                    val v = simccY[p * ny + i]
                    if (v > my) {
                        my = v
                        by = i
                    }
                }
                val ux = bx / SPLIT / WIDTH * bw + cx - bw / 2
                val uy = by / SPLIT / HEIGHT * bh + cy - bh / 2
                out[p * 3] = (ux / w).toFloat()
                out[p * 3 + 1] = (uy / h).toFloat()
                out[p * 3 + 2] = min(mx, my)
            }
            return out
        }
    }
}

class PrintFinder(private val runner: OrtRunner, private val mean: FloatArray = floatArrayOf(0.485f, 0.456f, 0.406f), private val std: FloatArray = floatArrayOf(0.229f, 0.224f, 0.225f)) : AutoCloseable {
    val backend get() = runner.backend

    fun crop(bgr: Mat, box: DoubleArray, size: Int): FloatArray {
        val w = bgr.cols()
        val h = bgr.rows()
        val mx = box[2] * MARGIN
        val my = box[3] * MARGIN
        var x0 = max(0, ((box[0] - mx) * w).toInt())
        var y0 = max(0, ((box[1] - my) * h).toInt())
        var x1 = min(w, ceil((box[0] + box[2] + mx) * w).toInt())
        var y1 = min(h, ceil((box[1] + box[3] + my) * h).toInt())
        if (x1 - x0 < 2 || y1 - y0 < 2) {
            x0 = 0
            y0 = 0
            x1 = 2
            y1 = 2
        }
        val part = bgr.submat(Rect(x0, y0, x1 - x0, y1 - y0))
        val shrink = part.rows() > size || part.cols() > size
        val resized = Mat()
        Imgproc.resize(part, resized, Size(size.toDouble(), size.toDouble()), 0.0, 0.0, if (shrink) Imgproc.INTER_AREA else Imgproc.INTER_LINEAR)
        Imgproc.cvtColor(resized, resized, Imgproc.COLOR_BGR2RGB)
        val pixels = Pixels.floats(resized)
        resized.release()
        part.release()
        for (i in pixels.indices) pixels[i] = (pixels[i] / 255f - mean[i % 3]) / std[i % 3]
        return Pixels.chw(pixels, size, size)
    }

    fun embed(bgr: Mat, boxes: List<DoubleArray>, size: Int = SIZE): List<FloatArray> {
        val out = ArrayList<FloatArray>()
        for (start in boxes.indices step BATCH) {
            val group = boxes.subList(start, min(boxes.size, start + BATCH))
            val plane = 3 * size * size
            val batch = FloatArray(group.size * plane)
            group.forEachIndexed { i, box -> crop(bgr, box, size).copyInto(batch, i * plane) }
            val outputs = runner.runBatch(batch, group.size, size, size)
            val cls = outputs.firstOrNull { it.name == "cls" } ?: outputs[0]
            val dims = (cls.data.size / group.size)
            for (i in group.indices) out += normalise(cls.data.copyOfRange(i * dims, (i + 1) * dims))
        }
        return out
    }

    override fun close() = runner.close()

    companion object {
        const val SIZE = 140
        const val MARGIN = 0.08
        const val BATCH = 16

        fun normalise(v: FloatArray): FloatArray {
            var sum = 0.0
            for (x in v) sum += x.toDouble() * x
            val norm = max(sqrt(sum), 1e-9).toFloat()
            return FloatArray(v.size) { v[it] / norm }
        }
    }
}
