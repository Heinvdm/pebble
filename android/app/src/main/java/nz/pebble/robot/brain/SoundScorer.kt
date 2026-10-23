package nz.pebble.robot.brain

import ai.onnxruntime.OnnxTensor
import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtSession
import android.os.Process
import android.os.SystemClock
import android.util.Log
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.nio.FloatBuffer
import java.util.concurrent.ArrayBlockingQueue
import java.util.concurrent.TimeUnit

class SoundWindows(private val window: Int = WINDOW, private val hop: Int = HOP) {
    private val ring = FloatArray(window)
    private var seen = 0L
    private var next = window.toLong()

    fun reset() {
        seen = 0
        next = window.toLong()
    }

    fun add(pcm: ShortArray, count: Int, ready: (FloatArray, Int) -> Unit) {
        for (i in 0 until count) {
            ring[(seen % window).toInt()] = pcm[i] / 32768f
            seen++
            if (seen == next) {
                val start = (seen % window).toInt()
                val out = FloatArray(window)
                System.arraycopy(ring, start, out, 0, window - start)
                System.arraycopy(ring, 0, out, window - start, start)
                next += hop
                ready(out, count - 1 - i)
            }
        }
    }

    companion object {
        const val WINDOW = 15_600
        const val HOP = 7_680
    }
}

object HalfFloats {
    private const val LARGEST = 65504f

    fun bits(value: Float): Int {
        val raw = java.lang.Float.floatToRawIntBits(value.coerceIn(-LARGEST, LARGEST))
        val sign = (raw ushr 16) and 0x8000
        val exponent = ((raw ushr 23) and 0xFF) - 127 + 15
        val mantissa = raw and 0x7FFFFF
        if (exponent <= 0) {
            if (exponent < -10) return sign
            val full = mantissa or 0x800000
            val shift = 14 - exponent
            val kept = full ushr shift
            val rest = full and ((1 shl shift) - 1)
            val middle = 1 shl (shift - 1)
            return sign or (if (rest > middle || (rest == middle && (kept and 1) == 1)) kept + 1 else kept)
        }
        val kept = (exponent shl 10) or (mantissa ushr 13)
        val rest = mantissa and 0x1FFF
        return sign or (if (rest > 0x1000 || (rest == 0x1000 && (kept and 1) == 1)) kept + 1 else kept)
    }

    fun value(bits: Int): Float {
        val sign = if (bits and 0x8000 != 0) -1f else 1f
        val exponent = (bits ushr 10) and 0x1F
        val mantissa = bits and 0x3FF
        return when (exponent) {
            0 -> sign * mantissa * Math.scalb(1f, -24)
            0x1F -> if (mantissa == 0) sign * Float.POSITIVE_INFINITY else Float.NaN
            else -> sign * (1f + mantissa / 1024f) * Math.scalb(1f, exponent - 15)
        }
    }

    fun pack(values: FloatArray): ByteArray {
        val out = ByteArray(values.size * 2)
        for (i in values.indices) {
            val h = bits(values[i])
            out[2 * i] = (h and 0xFF).toByte()
            out[2 * i + 1] = ((h ushr 8) and 0xFF).toByte()
        }
        return out
    }

    fun unpack(bytes: ByteArray): FloatArray = FloatArray(bytes.size / 2) { value((bytes[2 * it].toInt() and 0xFF) or ((bytes[2 * it + 1].toInt() and 0xFF) shl 8)) }

    fun text(values: FloatArray): String = "f16:" + java.util.Base64.getEncoder().encodeToString(pack(values))
}

class SoundVectors(private val keep: Int = KEEP, private val wantS: Double = WANT_S) {
    private val rows = ArrayDeque<Pair<Double, FloatArray>>()
    private var total = 0L
    @Volatile private var askedAt = Double.NEGATIVE_INFINITY

    fun wanted(nowMs: Double): Boolean = nowMs - askedAt <= wantS * 1000

    @Synchronized
    fun add(t: Double, vector: FloatArray, nowMs: Double) {
        if (!wanted(nowMs)) {
            rows.clear()
            return
        }
        if (vector.size != SIZE || vector.any { !it.isFinite() }) return
        rows.addLast(t to vector)
        while (rows.size > keep) rows.removeFirst()
        total++
    }

    @Synchronized
    fun forgetIfUnwanted(nowMs: Double) {
        if (!wanted(nowMs)) rows.clear()
    }

    @Synchronized
    fun forget() {
        rows.clear()
    }

    @Synchronized
    fun read(from: Long, nowMs: Double): JSONObject {
        askedAt = nowMs
        val oldest = total - rows.size
        val start = from.coerceIn(oldest, total)
        val out = JSONArray()
        for (i in (start - oldest).toInt() until rows.size) {
            val (t, vector) = rows.elementAt(i)
            out.put(JSONArray().put(t).put(HalfFloats.text(vector)))
        }
        return JSONObject().put("total", total).put("from", start).put("rows", out).put("now_ms", nowMs).put("kept", rows.size)
    }

    companion object {
        const val SIZE = 1024
        const val KEEP = 63
        const val WANT_S = 60.0
    }
}

class SoundScorer(private val model: () -> File?) : AudioSink {
    private val windows = SoundWindows()
    private class Window(val samples: FloatArray, val t: Double, val own: Boolean)

    private val queue = ArrayBlockingQueue<Window>(4)
    private val rows = ArrayDeque<Pair<Double, FloatArray>>()
    private val vectors = SoundVectors()
    private var total = 0L
    @Volatile private var on = false
    @Volatile private var thread: Thread? = null
    @Volatile var problem = ""
    @Volatile var vectorProblem = ""
    @Volatile var lastMs = 0.0
    @Volatile var dropped = 0
    @Volatile private var speakingAt = Double.NEGATIVE_INFINITY

    @Synchronized
    fun restart() {
        windows.reset()
    }

    @Synchronized
    fun enable(wanted: Boolean) {
        if (wanted == on) return
        on = wanted
        windows.reset()
        if (!wanted) vectors.forget()
        if (wanted && thread == null) thread = Thread({ run() }, "pebble-sound-scores").also { it.start() }
    }

    override fun onAudio(pcm: ShortArray, count: Int, speaking: Boolean) {
        if (!on) return
        val now = SystemClock.elapsedRealtimeNanos() / 1e6
        if (speaking) speakingAt = now
        windows.add(pcm, count) { samples, after ->
            val t = now - after * 1000.0 / Microphone.RATE
            if (!queue.offer(Window(samples, t, t - speakingAt < OWN_VOICE_MS))) dropped++
        }
    }

    private fun run() {
        Process.setThreadPriority(Process.THREAD_PRIORITY_BACKGROUND)
        val env = OrtEnvironment.getEnvironment()
        val session: OrtSession = try {
            val file = model() ?: throw IllegalStateException("the sound model is not in this build")
            val options = OrtSession.SessionOptions()
            options.setIntraOpNumThreads(1)
            options.setInterOpNumThreads(1)
            env.createSession(file.path, options)
        } catch (e: Throwable) {
            problem = "the sound model would not load: ${e.message}"
            Log.w(TAG, problem, e)
            thread = null
            return
        }
        val hasVectors = EMBEDDINGS in session.outputNames
        if (!hasVectors) vectorProblem = "this sound model has no $EMBEDDINGS output"
        session.use {
            while (true) {
                val next = queue.poll(1, TimeUnit.SECONDS)
                if (next == null) {
                    vectors.forgetIfUnwanted(SystemClock.elapsedRealtimeNanos() / 1e6)
                    if (on) continue else break
                }
                val started = System.nanoTime()
                val nowMs = SystemClock.elapsedRealtimeNanos() / 1e6
                val withVectors = hasVectors && !next.own && vectors.wanted(nowMs)
                if (!withVectors) vectors.forgetIfUnwanted(nowMs)
                try {
                    OnnxTensor.createTensor(env, FloatBuffer.wrap(next.samples), longArrayOf(1, SoundWindows.WINDOW.toLong())).use { tensor ->
                        session.run(mapOf(INPUT to tensor), if (withVectors) setOf(OUTPUT, EMBEDDINGS) else setOf(OUTPUT)).use { result ->
                            keep(next.t, floats(result.get(OUTPUT).get() as OnnxTensor))
                            if (withVectors) vectors.add(next.t, floats(result.get(EMBEDDINGS).get() as OnnxTensor), nowMs)
                        }
                    }
                } catch (e: Throwable) {
                    problem = "the sound model failed: ${e.message}"
                    Log.w(TAG, problem, e)
                }
                lastMs = (System.nanoTime() - started) / 1e6
            }
        }
        synchronized(this) { thread = null }
    }

    private fun floats(value: OnnxTensor): FloatArray {
        val buffer = value.floatBuffer
        val out = FloatArray(buffer.remaining())
        buffer.get(out)
        return out
    }

    fun readVectors(from: Long): String = vectors.read(from, SystemClock.elapsedRealtimeNanos() / 1e6)
        .put("running", on && thread != null)
        .put("problem", vectorProblem.ifEmpty { problem })
        .toString()

    @Synchronized
    private fun keep(t: Double, scores: FloatArray) {
        rows.addLast(t to scores)
        while (rows.size > KEEP) rows.removeFirst()
        total++
    }

    @Synchronized
    fun read(from: Long): String {
        val oldest = total - rows.size
        val start = from.coerceIn(oldest, total)
        val out = JSONArray()
        for (i in (start - oldest).toInt() until rows.size) {
            val (t, scores) = rows.elementAt(i)
            out.put(JSONArray().put(t).put(JSONArray(scores.map { Math.round(it * 1000) / 1000.0 })))
        }
        return JSONObject().put("total", total).put("from", start).put("rows", out).put("now_ms", SystemClock.elapsedRealtimeNanos() / 1e6).put("ms", lastMs).put("dropped", dropped).put("problem", problem).toString()
    }

    companion object {
        const val TAG = "PebbleSounds"
        const val INPUT = "waveform"
        const val OUTPUT = "scores"
        const val EMBEDDINGS = "embeddings"
        const val OWN_VOICE_MS = SoundWindows.WINDOW * 1000.0 / Microphone.RATE + 500.0
        const val KEEP = 30
    }
}
