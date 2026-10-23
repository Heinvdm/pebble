package nz.pebble.robot.eyes

import org.opencv.core.Core
import org.opencv.core.CvType
import org.opencv.core.Mat
import org.opencv.core.Scalar
import org.opencv.core.Size
import org.opencv.dnn.Dnn
import org.opencv.dnn.Net
import org.opencv.imgproc.Imgproc
import java.io.File
import kotlin.math.atan2
import kotlin.math.cos
import kotlin.math.hypot
import kotlin.math.max
import kotlin.math.sin

object Mouth {
    const val MODEL = "face_landmarks_detector.tflite"
    const val SIDE = 256
    const val SCALE = 3.0
    const val CENTRE = 0.4
    const val POINTS = 478
    const val MIN_FACE_PX = 32.0
    const val MAX_FACES = 2
    const val MAX_TAIL_S = 10.0
    private const val LIP_TOP = 13
    private const val LIP_BOTTOM = 14
    private const val CORNER_RIGHT = 78
    private const val CORNER_LEFT = 308
    private const val EYE_RIGHT = 33
    private const val EYE_LEFT = 263

    fun crop(marks: DoubleArray): DoubleArray? {
        if (marks.size < 10) return null
        val rx = marks[0]
        val ry = marks[1]
        val lx = marks[2]
        val ly = marks[3]
        val ex = (rx + lx) / 2
        val ey = (ry + ly) / 2
        val mx = (marks[6] + marks[8]) / 2
        val my = (marks[7] + marks[9]) / 2
        val span = max(hypot(lx - rx, ly - ry), hypot(mx - ex, my - ey))
        if (span < 1) return null
        val angle = atan2(ly - ry, lx - rx)
        val cx = ex + (mx - ex) * CENTRE
        val cy = ey + (my - ey) * CENTRE
        val scale = SIDE / (span * SCALE)
        val a = scale * cos(angle)
        val b = scale * sin(angle)
        return doubleArrayOf(a, b, (1 - a) * cx - b * cy + SIDE / 2.0 - cx, -b, a, b * cx + (1 - a) * cy + SIDE / 2.0 - cy)
    }

    fun shape(points: FloatArray): DoubleArray? {
        if (points.size < POINTS * 3) return null
        fun gap(i: Int, j: Int) = hypot(points[i * 3].toDouble() - points[j * 3].toDouble(), points[i * 3 + 1].toDouble() - points[j * 3 + 1].toDouble())
        val eyes = gap(EYE_RIGHT, EYE_LEFT)
        if (eyes < 1e-6) return null
        return doubleArrayOf(gap(LIP_TOP, LIP_BOTTOM) / eyes, gap(CORNER_RIGHT, CORNER_LEFT) / eyes)
    }

    fun pick(faces: List<Det>, width: Int, minFacePx: Double, most: Int): List<Int> =
        faces.indices.filter { faces[it].marks != null && faces[it].w * width >= minFacePx }.sortedByDescending { faces[it].w }.take(most)

    fun pixels(marks: FloatArray, width: Int, height: Int): DoubleArray = DoubleArray(10) { j -> marks[j].toDouble() * (if (j % 2 == 0) width else height) }
}

class MouthReader(path: File) : AutoCloseable {
    private val net: Net = Dnn.readNetFromTFLite(path.path)
    private val names: List<String> = net.unconnectedOutLayersNames
    val backend = "opencv-tflite"

    init {
        net.setPreferableBackend(Dnn.DNN_BACKEND_OPENCV)
        net.setPreferableTarget(Dnn.DNN_TARGET_CPU)
    }

    fun read(bgr: Mat, marks: DoubleArray): DoubleArray? {
        val m = Mouth.crop(marks) ?: return null
        val matrix = Mat(2, 3, CvType.CV_64F)
        matrix.put(0, 0, *m)
        val crop = Mat()
        val side = Size(Mouth.SIDE.toDouble(), Mouth.SIDE.toDouble())
        Imgproc.warpAffine(bgr, crop, matrix, side, Imgproc.INTER_LINEAR, Core.BORDER_CONSTANT)
        val blob = Dnn.blobFromImage(crop, 1.0 / 255.0, side, Scalar(0.0, 0.0, 0.0), true, false, CvType.CV_32F)
        matrix.release()
        crop.release()
        net.setInput(blob)
        val outs = ArrayList<Mat>()
        try {
            net.forward(outs, names)
            var points: FloatArray? = null
            var sure: Float? = null
            for (o in outs) {
                val total = o.total().toInt()
                if (total == Mouth.POINTS * 3 && points == null) points = flat(o, total)
                else if (total == 1 && o.dims() == 4 && sure == null) sure = flat(o, 1)[0]
            }
            if (points == null || sure == null || sure < 0) return null
            return Mouth.shape(points)
        } finally {
            outs.forEach { it.release() }
            blob.release()
        }
    }

    private fun flat(o: Mat, total: Int): FloatArray {
        val out = FloatArray(total)
        val row = o.reshape(1, 1)
        row.get(0, 0, out)
        return out
    }

    override fun close() = Unit
}
