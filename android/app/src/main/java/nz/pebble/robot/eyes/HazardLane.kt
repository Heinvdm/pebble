package nz.pebble.robot.eyes

import android.os.Process
import android.util.Log
import org.json.JSONArray
import org.json.JSONObject
import org.opencv.core.Mat
import kotlin.math.max

class HazardLane(
    private val make: () -> Yoloe?,
    everyS: Double,
    private val grab: () -> Picture?,
    private val publish: (JSONObject) -> Unit,
) {
    class Picture(val image: Mat, val camera: String, val t: Double)

    private val lock = Object()
    private var every = clamp(everyS)
    private var lastPass = Double.NEGATIVE_INFINITY
    private var lastT = Double.NaN
    private var generation = 0L
    @Volatile private var stop = false
    private var thread: Thread? = null
    @Volatile var passes = 0
    @Volatile var lastMs = 0.0
    @Volatile var problem = ""
    @Volatile var backend: String? = null

    val everyS: Double get() = synchronized(lock) { every }

    fun start() {
        if (thread != null) return
        stop = false
        thread = Thread({ run() }, "pebble-eyes-hazards").also { it.start() }
    }

    fun close() {
        stop = true
        synchronized(lock) {
            lock.notifyAll()
        }
        thread?.join(10_000)
        thread = null
    }

    fun setEvery(seconds: Double) = synchronized(lock) {
        every = clamp(seconds)
        lock.notifyAll()
    }

    fun forget() = synchronized(lock) {
        generation++
        lastT = Double.NaN
    }

    private fun now(): Double = System.nanoTime() / 1e9

    private fun run() {
        Process.setThreadPriority(NICE)
        val detector = try {
            make()
        } catch (e: Throwable) {
            problem = "the hazard watch is off: ${e.message}"
            Log.w(TAG, problem, e)
            null
        }
        backend = detector?.backend
        if (detector == null) {
            if (problem.isEmpty()) problem = "the hazard watch is off: there is no hazard model"
            publish(JSONObject().put("failed", true).put("problem", problem))
            return
        }
        while (!stop) {
            var round = 0L
            var seenT = Double.NaN
            synchronized(lock) {
                while (!stop) {
                    val left = lastPass + every - now()
                    if (left <= 0) break
                    lock.wait(max(1L, (left * 1000).toLong()))
                }
                round = generation
                seenT = lastT
            }
            if (stop) break
            val picture = grab()
            if (picture == null || picture.t == seenT) {
                picture?.image?.release()
                synchronized(lock) {
                    if (!stop) lock.wait(WAIT_MS)
                }
                continue
            }
            val started = System.nanoTime()
            val found = try {
                detector.find(picture.image)
            } catch (e: Throwable) {
                problem = "the hazard watch failed on a picture: ${e.message}"
                Log.w(TAG, problem, e)
                null
            }
            lastMs = (System.nanoTime() - started) / 1e6
            val out = JSONObject()
            if (found == null) {
                out.put("failed", true).put("problem", problem)
            } else {
                problem = ""
                passes++
                out.put("camera", picture.camera).put("t", picture.t).put("w", picture.image.cols()).put("h", picture.image.rows()).put("ms", Math.round(lastMs * 10) / 10.0)
                out.put("found", JSONArray(found.map { JSONArray(listOf(it.x, it.y, it.w, it.h, it.score, it.cls)) }))
            }
            picture.image.release()
            val current = synchronized(lock) {
                lastPass = now()
                lastT = picture.t
                generation
            }
            if (current == round) publish(out)
        }
        detector.close()
    }

    companion object {
        const val TAG = "PebbleEyesHazards"
        const val NICE = 5
        const val WAIT_MS = 100L
        const val MIN_S = 0.2
        const val MAX_S = 60.0
        const val DEFAULT_S = 3.0

        fun clamp(seconds: Double): Double = if (seconds.isNaN()) DEFAULT_S else seconds.coerceIn(MIN_S, MAX_S)
    }
}
