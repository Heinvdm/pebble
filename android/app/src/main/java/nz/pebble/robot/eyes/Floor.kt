package nz.pebble.robot.eyes

import android.os.Process
import android.util.Log
import org.json.JSONArray
import org.json.JSONObject
import org.opencv.core.Core
import org.opencv.core.Mat
import org.opencv.core.Point
import org.opencv.core.Size
import org.opencv.imgproc.Imgproc
import kotlin.math.abs
import kotlin.math.atan2
import kotlin.math.cos
import kotlin.math.hypot
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sin
import kotlin.math.tan

object Floor {
    const val MODEL = "depth_anything_v2_small_fp16.onnx"
    const val ROWS = 182
    const val COLS = 238
    const val BINS = 32
    const val REACH_M = 2.0
    const val OPEN_M = 9.0
    const val EVERY_S = 0.2
    const val LEVEL_MIN_DEG = 0.5
    const val MOVING_TAIL_S = 1.0
    const val MOVING = "moving"
    const val ALWAYS = "always"
    const val OFF = "off"
    val MEAN = floatArrayOf(0.485f, 0.456f, 0.406f)
    val STD = floatArrayOf(0.229f, 0.224f, 0.225f)
    private const val SEED_NEAR_M = 0.0
    private const val SEED_FAR_M = 1.3
    private const val UP = 0.35
    private const val DOWN = 0.5
    private const val DROP_REACH_M = 1.5
    private const val RUN = 2
    private const val SLOPE_ROWS = 3
    private const val PLATEAU = 0.35
    private const val LOW = 0.1

    class Ray(val bearing: Double, val distance: Double, val score: Double)

    class Scan(val rays: List<Ray>, val quality: Double)

    fun gate(name: String?): String = if (name == ALWAYS || name == OFF) name else MOVING

    fun rays(depth: FloatArray, rows: Int, cols: Int, fovDeg: Double, heightM: Double, pitchDeg: Double, bins: Int = BINS, reachM: Double = REACH_M): Scan? {
        require(depth.size == rows * cols) { "the depth map is ${depth.size} values, not $rows x $cols" }
        val f = (cols / 2.0) / tan(Math.toRadians(fovDeg) / 2)
        val p = Math.toRadians(pitchDeg)
        val cp = cos(p)
        val sp = sin(p)
        val down = DoubleArray(rows)
        val ahead = DoubleArray(rows)
        val ground = DoubleArray(rows)
        for (r in 0 until rows) {
            val y = (r + 0.5 - rows / 2.0) / f
            down[r] = y * cp - sp
            ahead[r] = cp + y * sp
            ground[r] = if (down[r] > 1e-4) heightM * ahead[r] / down[r] else Double.POSITIVE_INFINITY
        }
        val nearest = if (ground[rows - 1].isFinite()) ground[rows - 1] else SEED_FAR_M
        val limit = max(SEED_FAR_M, 1.6 * nearest)
        val seedRows = (0 until rows).filter { ground[it] >= SEED_NEAR_M && ground[it] <= limit }
        if (seedRows.size < 4) return null
        val c0 = (cols * 0.2).toInt()
        val c1 = (cols * 0.8).toInt()
        val g = DoubleArray(seedRows.size * (c1 - c0))
        val d = DoubleArray(g.size)
        var k = 0
        for (r in seedRows) {
            for (c in c0 until c1) {
                g[k] = down[r]
                d[k] = depth[r * cols + c].toDouble()
                k++
            }
        }
        val fit = fit(g, d) ?: return null
        val alpha = fit[0]
        val beta = fit[1].toFloat()
        val quality = fit[2]
        val top = (alpha * heightM).toFloat()
        val z = FloatArray(rows * cols) { i ->
            val gap = depth[i] - beta
            if (gap > 1e-6f) top / gap else Float.POSITIVE_INFINITY
        }
        val edges = DoubleArray(bins + 1) { if (it == bins) cols.toDouble() else it * (cols.toDouble() / bins) }
        val out = ArrayList<Ray>(bins)
        val hf = heightM.toFloat()
        for (b in 0 until bins) {
            val a = edges[b].toInt()
            val e = max(edges[b].toInt() + 1, edges[b + 1].toInt())
            val width = e - a
            val tallRow = DoubleArray(width)
            val farRow = FloatArray(width)
            val column = DoubleArray(rows)
            val far = FloatArray(rows)
            for (r in 0 until rows) {
                for (i in 0 until width) {
                    val zz = z[r * cols + a + i]
                    farRow[i] = zz
                    tallRow[i] = heightM - zz.toDouble() * down[r]
                }
                column[r] = median(tallRow) / heightM
                far[r] = median(farRow)
            }
            val u = (a + e) / 2.0 / cols
            val x = (u - 0.5) * cols / f
            val gq = FloatArray(rows) { r -> if (far[r].isFinite() && far[r] > 0f) hf / far[r] else 0f }
            val rise = DoubleArray(rows) { 1.0 }
            for (r in 0 until rows - SLOPE_ROWS) rise[r] = (gq[r + SLOPE_ROWS] - gq[r]).toDouble() / max(down[r + SLOPE_ROWS] - down[r], 1e-9)
            val away = DoubleArray(rows) { r -> far[r].toDouble() * hypot(ahead[r], x) }
            val foot = foot(column, away, ground, reachM, rise)
            var distance = Double.NaN
            var bearing = 0.0
            var up = true
            if (foot != null) {
                val row = foot.first
                up = foot.second
                if (up) {
                    distance = far[row].toDouble() * hypot(ahead[row], x)
                    bearing = Math.toDegrees(atan2(x, ahead[row]))
                } else {
                    val spot = floorPoint(u, (row + 1.5) / rows, cols, rows, fovDeg, heightM, pitchDeg)
                    if (spot != null) {
                        distance = spot[0]
                        bearing = spot[1]
                    }
                }
            }
            if (!distance.isFinite() || distance > reachM) {
                val first = (0 until rows).firstOrNull { ground[it] <= reachM } ?: (rows - 1)
                out += Ray(Math.toDegrees(atan2(x, ahead[first])), OPEN_M, quality * 0.8)
                continue
            }
            val sure = quality * (if (up) 1.0 else 0.7) * max(0.4, 1.0 - distance / (2 * reachM))
            out += Ray(bearing, distance, sure)
        }
        return Scan(out, quality)
    }

    fun floorPoint(u: Double, v: Double, width: Int, height: Int, fovDeg: Double, heightM: Double, pitchDeg: Double): DoubleArray? {
        val f = (width / 2.0) / tan(Math.toRadians(fovDeg) / 2)
        val x = (u - 0.5) * width / f
        val y = (v - 0.5) * height / f
        val p = Math.toRadians(pitchDeg)
        val ahead = cos(p) + y * sin(p)
        val down = y * cos(p) - sin(p)
        if (down <= 1e-3 || ahead <= 0) return null
        val t = heightM / down
        val gx = t * x
        val gy = t * ahead
        return doubleArrayOf(hypot(gx, gy), Math.toDegrees(atan2(gx, gy)))
    }

    private fun fit(g0: DoubleArray, d0: DoubleArray): DoubleArray? {
        val keep = d0.indices.filter { d0[it].isFinite() }
        var g = DoubleArray(keep.size) { g0[keep[it]] }
        var d = DoubleArray(keep.size) { d0[keep[it]] }
        if (g.size < 20 || g.max() - g.min() < 1e-3) return null
        for (round in 0 until 3) {
            val line = line(g, d)
            val res = DoubleArray(g.size) { abs(d[it] - (line[0] * g[it] + line[1])) }
            val spread = median(res) * 1.4826 + 1e-6
            val inside = res.indices.filter { res[it] <= 2.5 * spread }
            if (inside.size < 20) break
            val ng = DoubleArray(inside.size) { g[inside[it]] }
            val nd = DoubleArray(inside.size) { d[inside[it]] }
            g = ng
            d = nd
        }
        val line = line(g, d)
        val a = line[0]
        val b = line[1]
        val span = a * (g.max() - g.min())
        if (span <= 1e-3 * (abs(medianOfSingles(d)) + 1e-6)) return null
        val res = DoubleArray(g.size) { abs(d[it] - (a * g[it] + b)) }
        val quality = max(0.0, min(1.0, 1.0 - 4.0 * median(res) / max(span, 1e-6)))
        return doubleArrayOf(a, b, quality)
    }

    private fun line(x: DoubleArray, y: DoubleArray): DoubleArray {
        var mx = 0.0
        var my = 0.0
        for (i in x.indices) {
            mx += x[i]
            my += y[i]
        }
        mx /= x.size
        my /= y.size
        var sxx = 0.0
        var sxy = 0.0
        for (i in x.indices) {
            val dx = x[i] - mx
            sxx += dx * dx
            sxy += dx * (y[i] - my)
        }
        val a = sxy / sxx
        return doubleArrayOf(a, my - a * mx)
    }

    private fun foot(column: DoubleArray, away: DoubleArray, ground: DoubleArray, reachM: Double, rise: DoubleArray): Pair<Int, Boolean>? {
        var runUp = 0
        var runDown = 0
        for (r in column.indices.reversed()) {
            val value = column[r]
            val upright = rise[r] < PLATEAU && value > LOW
            if (!value.isFinite() || value > UP || upright) {
                runUp++
                runDown = 0
            } else if (value < -DOWN) {
                runDown++
                runUp = 0
            } else {
                runUp = 0
                runDown = 0
                if (away[r] > reachM) return null
            }
            if (runUp >= RUN) return (r + RUN - 1) to true
            if (runDown >= RUN && ground[r + RUN - 1] <= min(reachM, DROP_REACH_M)) return (r + RUN - 1) to false
        }
        return null
    }

    fun median(values: DoubleArray): Double {
        if (values.any { it.isNaN() }) return Double.NaN
        val sorted = values.sortedArray()
        val n = sorted.size
        return if (n % 2 == 1) sorted[n / 2] else (sorted[n / 2 - 1] + sorted[n / 2]) / 2
    }

    fun median(values: FloatArray): Float {
        if (values.any { it.isNaN() }) return Float.NaN
        val sorted = values.sortedArray()
        val n = sorted.size
        return if (n % 2 == 1) sorted[n / 2] else (sorted[n / 2 - 1] + sorted[n / 2]) / 2f
    }

    private fun medianOfSingles(values: DoubleArray): Double = median(FloatArray(values.size) { values[it].toFloat() }).toDouble()
}

class Depth(private val runner: Runner) : AutoCloseable {
    val backend get() = runner.backend
    var timings: JSONObject = JSONObject()

    fun run(bgr: Mat, rollDeg: Double): FloatArray {
        val level = if (abs(rollDeg) < Floor.LEVEL_MIN_DEG) bgr else Mat().also {
            val turn = Imgproc.getRotationMatrix2D(Point(bgr.cols() / 2.0, bgr.rows() / 2.0), rollDeg, 1.0)
            Imgproc.warpAffine(bgr, it, turn, Size(bgr.cols().toDouble(), bgr.rows().toDouble()), Imgproc.INTER_LINEAR, Core.BORDER_REPLICATE)
            turn.release()
        }
        val small = Mat()
        Imgproc.resize(level, small, Size(Floor.COLS.toDouble(), Floor.ROWS.toDouble()), 0.0, 0.0, Imgproc.INTER_AREA)
        if (level !== bgr) level.release()
        Imgproc.cvtColor(small, small, Imgproc.COLOR_BGR2RGB)
        val pixels = Pixels.floats(small)
        small.release()
        for (i in pixels.indices) pixels[i] = (pixels[i] / 255f - Floor.MEAN[i % 3]) / Floor.STD[i % 3]
        val out = runner.run(Pixels.chw(pixels, Floor.ROWS, Floor.COLS), Floor.ROWS, Floor.COLS).first()
        check(out.data.size == Floor.ROWS * Floor.COLS) { "the depth model gave ${out.data.size} values" }
        return out.data
    }

    override fun close() = runner.close()
}

class FloorLane(
    private val make: () -> Depth?,
    everyS: Double,
    gate: String,
    private val bins: Int,
    private val reachM: Double,
    private val grab: () -> HazardLane.Picture?,
    private val where: (String) -> Where?,
    private val publish: (JSONObject) -> Boolean,
) {
    class Where(val fov: Double, val height: Double, val pitch: Double, val roll: Double)

    private val lock = Object()
    val gate = Floor.gate(gate)
    val everyS = if (everyS.isNaN()) Floor.EVERY_S else everyS.coerceIn(MIN_S, MAX_S)
    private var lastPass = Double.NEGATIVE_INFINITY
    private var lastT = Double.NaN
    private var generation = 0L
    private var wanted = false
    private var moving = false
    private var movingUntil = Double.NEGATIVE_INFINITY
    @Volatile private var stop = false
    private var thread: Thread? = null
    @Volatile var passes = 0
    @Volatile var taken = 0
    @Volatile var lastMs = 0.0
    @Volatile var depthMs = 0.0
    @Volatile var raysMs = 0.0
    @Volatile var quality = 0.0
    @Volatile var problem = ""
    @Volatile var backend: String? = null
    @Volatile var bench: JSONObject = JSONObject()

    fun start() {
        if (thread != null) return
        stop = false
        thread = Thread({ run() }, "pebble-eyes-floor").also { it.start() }
    }

    fun close() {
        stop = true
        synchronized(lock) {
            lock.notifyAll()
        }
        thread?.join(10_000)
        thread = null
    }

    fun setMoving(on: Boolean) = synchronized(lock) {
        moving = on
        if (!on) movingUntil = now() + Floor.MOVING_TAIL_S
        lock.notifyAll()
    }

    fun isMoving(): Boolean = synchronized(lock) { movingAt(now()) }

    fun want() = synchronized(lock) {
        wanted = true
        lock.notifyAll()
    }

    fun forget() = synchronized(lock) {
        generation++
        lastT = Double.NaN
    }

    private fun now(): Double = System.nanoTime() / 1e9

    private fun movingAt(now: Double): Boolean = moving || now < movingUntil

    private fun due(now: Double): Boolean {
        if (wanted) return true
        if (gate == Floor.OFF || (gate == Floor.MOVING && !movingAt(now))) return false
        return now - lastPass >= everyS
    }

    private fun run() {
        Process.setThreadPriority(NICE)
        val model = try {
            make()
        } catch (e: Throwable) {
            problem = "no floor scan: ${e.message}"
            Log.w(TAG, problem, e)
            null
        }
        backend = model?.backend
        model?.let { bench = it.timings }
        if (model == null) {
            if (problem.isEmpty()) problem = "no floor scan: there is no depth model"
            publish(JSONObject().put("failed", true).put("problem", problem))
            return
        }
        while (!stop) {
            var round: Long
            var seenT: Double
            synchronized(lock) {
                while (!stop && !due(now())) lock.wait(WAIT_MS)
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
            synchronized(lock) {
                wanted = false
            }
            val out = look(model, picture)
            picture.image.release()
            val current = synchronized(lock) {
                lastPass = now()
                lastT = picture.t
                generation
            }
            if (current == round && publish(out)) taken++
        }
        model.close()
    }

    private fun look(model: Depth, picture: HazardLane.Picture): JSONObject {
        val place = where(picture.camera) ?: return JSONObject().put("failed", true).put("problem", "the floor scan does not know the ${picture.camera} camera")
        val started = System.nanoTime()
        return try {
            val depth = model.run(picture.image, place.roll)
            val middle = System.nanoTime()
            val scan = Floor.rays(depth, Floor.ROWS, Floor.COLS, place.fov, place.height, place.pitch, bins, reachM)
            val ended = System.nanoTime()
            depthMs = (middle - started) / 1e6
            raysMs = (ended - middle) / 1e6
            lastMs = (ended - started) / 1e6
            quality = scan?.quality ?: 0.0
            passes++
            problem = ""
            val rays = JSONArray()
            for (ray in scan?.rays ?: emptyList()) rays.put(JSONArray().put(ray.bearing).put(ray.distance).put(ray.score))
            JSONObject()
                .put("camera", picture.camera)
                .put("t", picture.t)
                .put("rays", rays)
                .put("quality", quality)
                .put("ms", Math.round(lastMs * 10) / 10.0)
                .put("depth_ms", Math.round(depthMs * 10) / 10.0)
                .put("rays_ms", Math.round(raysMs * 10) / 10.0)
                .put("head", JSONArray().put(place.height).put(place.pitch).put(place.roll))
        } catch (e: Throwable) {
            problem = "the floor scan failed on a picture: ${e.message}"
            Log.w(TAG, problem, e)
            JSONObject().put("failed", true).put("problem", problem)
        }
    }

    fun status(): JSONObject = JSONObject()
        .put("gate", gate)
        .put("moving", isMoving())
        .put("every_s", everyS)
        .put("passes", passes)
        .put("taken", taken)
        .put("ms", Math.round(lastMs * 10) / 10.0)
        .put("depth_ms", Math.round(depthMs * 10) / 10.0)
        .put("rays_ms", Math.round(raysMs * 10) / 10.0)
        .put("quality", Math.round(quality * 100) / 100.0)
        .put("backend", backend ?: JSONObject.NULL)
        .put("bench", bench)
        .put("problem", problem)

    companion object {
        const val TAG = "PebbleEyesFloor"
        const val NICE = 5
        const val WAIT_MS = 100L
        const val MIN_S = 0.05
        const val MAX_S = 60.0
    }
}
