package nz.pebble.robot.eyes

import org.json.JSONArray
import org.json.JSONObject
import org.opencv.core.Core
import org.opencv.core.CvType
import org.opencv.core.Mat
import org.opencv.core.Size
import org.opencv.imgproc.Imgproc

class Motion {
    class Step(val dt: Double, val dx: Double, val dy: Double, val sure: Double, val change: Double) {
        fun finite(): Boolean = dt.isFinite() && dx.isFinite() && dy.isFinite() && sure.isFinite() && change.isFinite()

        fun json(): JSONObject = JSONObject().put("dt", dt).put("shift", JSONArray().put(dx).put(dy)).put("sure", sure).put("change", change)
    }

    private var camera: String? = null
    private var t = 0.0
    private var prev: Mat? = null
    private var window: Mat? = null

    fun step(bgr: Mat, camera: String, t: Double): Step? {
        val now = small(bgr)
        val before = prev
        val beforeCamera = this.camera
        val beforeT = this.t
        prev = now
        this.camera = camera
        this.t = t
        if (before == null) return null
        try {
            if (beforeCamera != camera || t - beforeT > MAX_GAP_S || t <= beforeT) return null
            return compare(before, now, t - beforeT)
        } finally {
            before.release()
        }
    }

    fun compare(before: Mat, now: Mat, dt: Double): Step? {
        val diff = Mat()
        Core.absdiff(now, before, diff)
        val change = Core.mean(diff).`val`[0] / 255.0
        diff.release()
        val hann = window ?: Mat().also {
            Imgproc.createHanningWindow(it, Size(WIDTH.toDouble(), HEIGHT.toDouble()), CvType.CV_32F)
            window = it
        }
        val a = before.clone()
        val b = now.clone()
        val response = DoubleArray(1)
        val shift = Imgproc.phaseCorrelate(a, b, hann, response)
        a.release()
        b.release()
        return Step(dt, shift.x, shift.y, response[0], change).takeIf { it.finite() }
    }

    fun reset() {
        prev?.release()
        prev = null
        camera = null
    }

    fun close() {
        reset()
        window?.release()
        window = null
    }

    companion object {
        const val WIDTH = 80
        const val HEIGHT = 60
        const val MAX_GAP_S = 0.5

        fun small(bgr: Mat): Mat {
            val resized = Mat()
            Imgproc.resize(bgr, resized, Size(WIDTH.toDouble(), HEIGHT.toDouble()), 0.0, 0.0, Imgproc.INTER_AREA)
            val gray = Mat()
            Imgproc.cvtColor(resized, gray, Imgproc.COLOR_BGR2GRAY)
            resized.release()
            val out = Mat()
            gray.convertTo(out, CvType.CV_32F)
            gray.release()
            return out
        }
    }
}
