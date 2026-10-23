package nz.pebble.robot.eyes

import android.os.Process
import android.util.Log
import org.json.JSONArray
import org.json.JSONObject
import org.opencv.core.Core
import org.opencv.core.CvType
import org.opencv.core.Mat
import org.opencv.core.Size
import org.opencv.imgproc.Imgproc

class SlowLane(
    private val make: () -> Yoloe?,
    private val everyS: Double,
    private val change: Double,
    private val marks: ((Mat, List<Det>) -> JSONObject?)? = null,
    private val pace: () -> Double = { 1.0 },
    private val publish: (JSONObject) -> Unit,
) {
    private class Offer(val image: Mat, val camera: String, val t: Double)

    private val lock = Object()
    private var offer: Offer? = null
    private var offered = 0L
    private var seen = 0L
    private var busy = false
    private var moved = false
    private val demands = ArrayList<Int>()
    private var lastPass = Double.NEGATIVE_INFINITY
    private var thumb: Mat? = null
    private var thumbCamera: String? = null
    @Volatile private var stop = false
    private var thread: Thread? = null
    @Volatile var passes = 0
    @Volatile var lastMs = 0.0
    @Volatile var problem = ""
    @Volatile var backend: String? = null

    fun start() {
        if (thread != null) return
        stop = false
        thread = Thread({ run() }, "pebble-eyes-slow").also { it.start() }
    }

    fun close() {
        stop = true
        synchronized(lock) {
            lock.notifyAll()
        }
        thread?.join(10_000)
        thread = null
        synchronized(lock) {
            offer?.image?.release()
            offer = null
            thumb?.release()
            thumb = null
        }
    }

    fun offer(image: Mat, camera: String, t: Double) {
        synchronized(lock) {
            offer?.image?.release()
            offer = Offer(image, camera, t)
            offered++
            lock.notifyAll()
        }
    }

    fun forget() {
        val failed: List<Int>
        synchronized(lock) {
            offer?.image?.release()
            offer = null
            thumb?.release()
            thumb = null
            failed = ArrayList(demands)
            demands.clear()
        }
        if (failed.isNotEmpty()) publish(JSONObject().put("failed", true).put("demand", JSONArray(failed)))
    }

    fun setBusy(on: Boolean) = synchronized(lock) {
        busy = on
        lock.notifyAll()
    }

    val isBusy: Boolean get() = busy

    fun moved() = synchronized(lock) {
        moved = true
        lock.notifyAll()
    }

    fun demand(id: Int) = synchronized(lock) {
        demands += id
        lock.notifyAll()
    }

    private fun run() {
        Process.setThreadPriority(Process.THREAD_PRIORITY_BACKGROUND)
        val detector = try {
            make()
        } catch (e: Throwable) {
            problem = "the slow lane is off: ${e.message}"
            Log.w(TAG, problem, e)
            null
        }
        backend = detector?.backend
        while (!stop) {
            var image: Mat? = null
            var camera = ""
            var t = 0.0
            val asked: List<Int>
            val fresh: Boolean
            val wasMoved: Boolean
            val wasBusy: Boolean
            synchronized(lock) {
                val deadline = System.currentTimeMillis() + 1000
                while (!stop && demands.isEmpty() && !(offered > seen && !busy)) {
                    val left = deadline - System.currentTimeMillis()
                    if (left <= 0) break
                    lock.wait(left)
                }
                if (stop) return
                asked = ArrayList(demands)
                demands.clear()
                fresh = offered > seen
                seen = offered
                wasMoved = moved
                wasBusy = busy
                offer?.let {
                    image = it.image.clone()
                    camera = it.camera
                    t = it.t
                }
            }
            val picture = image
            if (detector == null || picture == null) {
                picture?.release()
                if (asked.isNotEmpty()) publish(JSONObject().put("failed", true).put("demand", JSONArray(asked)))
                continue
            }
            if (asked.isEmpty()) {
                val now = System.nanoTime() / 1e9
                if (wasBusy || !fresh || now - lastPass < everyS / pace().coerceIn(0.1, 1.0) || !(wasMoved || changed(picture, camera))) {
                    picture.release()
                    continue
                }
            }
            val started = System.nanoTime()
            val result = try {
                detector.find(picture)
            } catch (e: Throwable) {
                problem = "the slow lane failed on a picture: ${e.message}"
                Log.w(TAG, problem, e)
                null
            }
            lastMs = (System.nanoTime() - started) / 1e6
            val out = JSONObject().put("demand", JSONArray(asked))
            if (result == null) {
                out.put("failed", true)
            } else {
                out.put("camera", camera).put("t", t).put("w", picture.cols()).put("h", picture.rows()).put("ms", lastMs)
                out.put("found", JSONArray(result.map { JSONArray(listOf(it.x, it.y, it.w, it.h, it.score, it.cls)) }))
                try {
                    marks?.invoke(picture, result)?.let { extra ->
                        out.put("print_rows", extra.getJSONArray("print_rows"))
                        out.put("prints", extra.getJSONArray("prints"))
                    }
                } catch (e: Throwable) {
                    Log.w(TAG, "prints of the slow lane's finds failed", e)
                }
                synchronized(lock) {
                    moved = false
                    lastPass = System.nanoTime() / 1e9
                    passes++
                }
                remember(picture, camera)
            }
            picture.release()
            publish(out)
        }
        detector?.close()
    }

    private fun small(image: Mat): Mat {
        val gray = Mat()
        Imgproc.cvtColor(image, gray, Imgproc.COLOR_BGR2GRAY)
        val tiny = Mat()
        Imgproc.resize(gray, tiny, Size(32.0, 24.0), 0.0, 0.0, Imgproc.INTER_AREA)
        gray.release()
        val out = Mat()
        tiny.convertTo(out, CvType.CV_32F)
        tiny.release()
        return out
    }

    private fun changed(image: Mat, camera: String): Boolean {
        val before = thumb ?: return true
        if (thumbCamera != camera) return true
        val now = small(image)
        val diff = Mat()
        Core.absdiff(now, before, diff)
        val mean = Core.mean(diff).`val`[0] / 255.0
        now.release()
        diff.release()
        return mean > change
    }

    private fun remember(image: Mat, camera: String) {
        val made = small(image)
        synchronized(lock) {
            thumb?.release()
            thumb = made
            thumbCamera = camera
        }
    }

    companion object {
        const val TAG = "PebbleEyesSlow"
    }
}
