package nz.pebble.robot.brain

import org.json.JSONArray
import org.json.JSONObject
import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.cos
import kotlin.math.log10
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sin
import kotlin.math.sqrt

class Fft(val size: Int) {
    private val bits = Integer.numberOfTrailingZeros(size)
    private val cosines = DoubleArray(size / 2) { cos(2 * PI * it / size) }
    private val sines = DoubleArray(size / 2) { -sin(2 * PI * it / size) }
    private val order = IntArray(size) { Integer.reverse(it) ushr (32 - bits) }

    init {
        require(size >= 2 && size and (size - 1) == 0) { "the FFT size must be a power of two" }
    }

    fun power(input: FloatArray, window: DoubleArray, re: DoubleArray, im: DoubleArray, out: DoubleArray) {
        for (i in 0 until size) {
            re[order[i]] = input[i] * window[i]
            im[order[i]] = 0.0
        }
        var length = 2
        while (length <= size) {
            val halfLength = length / 2
            val step = size / length
            var start = 0
            while (start < size) {
                var k = 0
                for (j in start until start + halfLength) {
                    val c = cosines[k]
                    val s = sines[k]
                    val xr = re[j + halfLength] * c - im[j + halfLength] * s
                    val xi = re[j + halfLength] * s + im[j + halfLength] * c
                    re[j + halfLength] = re[j] - xr
                    im[j + halfLength] = im[j] - xi
                    re[j] += xr
                    im[j] += xi
                    k += step
                }
                start += length
            }
            length *= 2
        }
        for (k in out.indices) out[k] = re[k] * re[k] + im[k] * im[k]
    }
}

class HighBand(private val now: () -> Double = { android.os.SystemClock.elapsedRealtimeNanos() / 1e6 }) : WideSink {
    private class Tone(var hz: Double, val start: Double, var last: Double) {
        var frames = 0
        var misses = 0
        var levelSum = 0.0
        var overSum = 0.0
        var riseSum = 0.0
        var strong = 0
        var lowest = hz
        var highest = hz
        var ups = 0
        var downs = 0
        var told = false
        var steadyTold = false
        var own = false
        var inData = false
    }

    private class Ended(val start: Double, val end: Double, val hz: Double)

    private var rate = 0
    private var fft: Fft? = null
    private var window = DoubleArray(0)
    private var frame = FloatArray(0)
    private var filled = 0
    private var re = DoubleArray(0)
    private var im = DoubleArray(0)
    private var power = DoubleArray(0)
    private var mean = DoubleArray(0)
    private var unsettledUntil = 0.0
    private var louder = 0
    private var first = 0
    private var last = 0
    private var norm = 1.0
    private var seconds = 0.0
    private val tones = ArrayList<Tone>()
    private val ended = ArrayDeque<Ended>()
    private var dataSince = -1.0
    private var dataOn = false
    private var dataSeen = -1.0
    private var dataBins = HashSet<Int>()
    private var dataHz = ArrayList<Double>()
    private var bandSums = DoubleArray(0)
    private var bandFrames = 0
    private var bandStart = 0.0
    private val rows = ArrayDeque<JSONObject>()
    private var total = 0L
    @Volatile var topHz = MAX_TOP_HZ
    @Volatile var moving = false
    @Volatile var problem = "the high band needs a 48 or 96 kHz feed, and the microphone runs at 16 kHz"
    @Volatile var frames = 0L
        private set

    @Synchronized
    override fun onWide(pcm: ShortArray, frames: Int, channels: Int, rate: Int, speaking: Boolean) {
        if (rate != this.rate) setUp(rate)
        val transform = fft ?: return
        val stamp = now()
        for (i in 0 until frames) {
            frame[filled++] = pcm[i * channels] / 32768f
            if (filled == frame.size) {
                filled = 0
                seconds += frame.size.toDouble() / rate
                if (!speaking) look(transform, stamp - (frames - 1 - i) * 1000.0 / rate)
            }
        }
    }

    private fun setUp(newRate: Int) {
        rate = newRate
        tones.clear()
        ended.clear()
        filled = 0
        val size = Integer.highestOneBit(max(2, Math.round(newRate / BIN_HZ).toInt()))
        if (newRate / 2.0 <= LOW_HZ + 8 * BIN_HZ || abs(newRate.toDouble() / size - BIN_HZ) > 1.0) {
            fft = null
            problem = "the high band needs a 48 or 96 kHz feed, not ${newRate / 1000.0} kHz"
            return
        }
        fft = Fft(size)
        window = DoubleArray(size) { 0.5 - 0.5 * cos(2 * PI * (it + 0.5) / size) }
        norm = (window.sum() / 2).let { it * it }
        frame = FloatArray(size)
        re = DoubleArray(size)
        im = DoubleArray(size)
        power = DoubleArray(size / 2)
        first = Math.ceil(LOW_HZ / BIN_HZ).toInt()
        last = min(size / 2 - 3, Math.floor(min(topHz, newRate / 2.0) / BIN_HZ).toInt() - 1)
        mean = DoubleArray(size / 2) { -1.0 }
        frames = 0
        bandSums = DoubleArray(bands())
        bandFrames = 0
        problem = if (last - first < 8) "this phone's microphone path stops at ${Math.round(topHz / 100) / 10.0} kHz, so the high band is off" else ""
    }

    private fun bands(): Int = max(0, Math.floor((last * BIN_HZ - LOW_HZ) / BAND_HZ).toInt())

    private fun db(p: Double): Double = if (p > 0) 10 * log10(p / norm) else SILENT_DB

    private fun look(transform: Fft, at: Double) {
        if (last - first < 8) return
        frames++
        transform.power(frame, window, re, im, power)
        val lowBin = max(1, first - NOISE_FAR)
        val highBin = min(power.size - 1, last + NOISE_FAR)
        for (k in lowBin..highBin) if (mean[k] < 0) mean[k] = power[k]
        val now = middle(power.copyOfRange(first, last + 1), last - first + 1)
        val usual = middle(mean.copyOfRange(first, last + 1), last - first + 1)
        louder = if (frames > WARM_FRAMES && now > OUTLIER * usual) louder + 1 else 0
        val jumped = louder >= JUMP_FRAMES
        if (jumped) unsettledUntil = at + SETTLE_S * 1000
        if (louder == JUMP_FRAMES) tones.removeAll { !it.told }
        val settling = at < unsettledUntil
        val peaks = ArrayList<DoubleArray>()
        val near = DoubleArray(2 * (NEIGHBOUR_FAR - NEIGHBOUR_NEAR + 1))
        val far = DoubleArray(2 * (NOISE_FAR - NEIGHBOUR_NEAR + 1))
        for (k in first..last) {
            val p = power[k]
            if (k - NEIGHBOUR_FAR < 1 || k + NEIGHBOUR_FAR >= power.size) continue
            if (p < power[k - 1] || p < power[k + 1] || db(p) < MIN_DB) continue
            var n = 0
            for (d in NEIGHBOUR_NEAR..NEIGHBOUR_FAR) {
                near[n++] = power[k - d]
                near[n++] = power[k + d]
            }
            val level = db(p)
            val around = middle(near, n)
            if (level - db(around) < SHARP_DB) continue
            n = 0
            for (d in NEIGHBOUR_NEAR..NOISE_FAR) {
                if (k - d >= lowBin) far[n++] = mean[k - d]
                if (k + d <= highBin) far[n++] = mean[k + d]
            }
            val over = level - db(max(middle(far, n), around))
            if (over < PROMINENCE_DB) continue
            val a = db(power[k - 1])
            val c = db(power[k + 1])
            val bend = a - 2 * level + c
            val shift = if (bend < 0) (0.5 * (a - c) / bend).coerceIn(-0.5, 0.5) else 0.0
            peaks += doubleArrayOf((k + shift) * BIN_HZ, level, level - db(mean[k]), over, k.toDouble())
        }
        peaks.sortByDescending { it[1] }
        val kept = peaks.take(MAX_PEAKS)
        data(if (settling) emptyList() else kept, at)
        track(kept, at, !settling)
        val speed = if (frames <= WARM_FRAMES) WARM_RATE else if (jumped || settling) FAST_RATE else MEAN_RATE
        for (k in lowBin..highBin) {
            val p = power[k]
            mean[k] += (if (frames <= WARM_FRAMES || jumped || settling || p < OUTLIER * mean[k]) speed else CREEP) * (p - mean[k])
        }
        levels(at)
    }

    private fun middle(values: DoubleArray, count: Int): Double {
        if (count <= 0) return 0.0
        val sorted = values.copyOf(count)
        sorted.sort()
        return if (count % 2 == 1) sorted[count / 2] else (sorted[count / 2 - 1] + sorted[count / 2]) / 2
    }

    private fun track(peaks: List<DoubleArray>, at: Double, fresh: Boolean) {
        val free = peaks.toMutableList()
        for (tone in tones.sortedByDescending { it.frames }) {
            val need = if (tone.told) PROMINENCE_DB else STAND_OUT_DB
            val reach = if (tone.told) MATCH_HZ else PENDING_MATCH_HZ
            val floor = tone.levelSum / tone.frames - DROP_DB
            val best = free.filter { it[3] >= need && it[1] >= floor && abs(it[0] - tone.hz) <= reach }.maxByOrNull { it[1] }
            if (best != null) {
                free.remove(best)
                val step = best[0] - tone.hz
                if (step > STEP_HZ) tone.ups++ else if (step < -STEP_HZ) tone.downs++
                tone.hz = best[0]
                tone.last = at
                tone.frames++
                tone.misses = 0
                tone.levelSum += best[1]
                tone.overSum += best[3]
                tone.riseSum += best[2]
                if (best[3] >= STAND_OUT_DB) tone.strong++
                tone.lowest = min(tone.lowest, best[0])
                tone.highest = max(tone.highest, best[0])
                if (moving && abs(best[0] - MOTOR_HZ) <= MOTOR_SPREAD_HZ) tone.own = true
                if (!tone.told && !tone.inData && tone.strong >= MIN_FRAMES && (at - tone.start) / 1000 >= START_S) {
                    tone.told = true
                    keep(row(tone, "start", at))
                }
                if (!tone.steadyTold && tone.told && (at - tone.start) / 1000 >= STEADY_S && tone.highest - tone.lowest <= STEADY_SPREAD_HZ) {
                    tone.steadyTold = true
                    keep(row(tone, "steady", at))
                }
            } else {
                tone.misses++
            }
        }
        val gone = tones.filter { it.misses > GAP_FRAMES }
        for (tone in gone) {
            tones.remove(tone)
            if (tone.strong < MIN_FRAMES) continue
            if (tone.told || (!tone.inData && !dataOn)) keep(row(tone, "end", at))
            ended.addLast(Ended(tone.start, tone.last, (tone.lowest + tone.highest) / 2))
        }
        while (ended.isNotEmpty() && at - ended.first().end > PATTERN_KEEP_S * 1000) ended.removeFirst()
        for (peak in free) {
            if (!fresh || peak[3] < STAND_OUT_DB) continue
            val tone = Tone(peak[0], at, at)
            tone.frames = 1
            tone.levelSum = peak[1]
            tone.overSum = peak[3]
            tone.riseSum = peak[2]
            tone.strong = 1
            if (moving && abs(peak[0] - MOTOR_HZ) <= MOTOR_SPREAD_HZ) tone.own = true
            tone.inData = dataOn
            tones += tone
        }
    }

    private fun shape(tone: Tone, ended: Boolean): Pair<String, DoubleArray?> {
        val length = (tone.last - tone.start) / 1000
        val moves = tone.ups + tone.downs
        if (tone.highest - tone.lowest >= SWEEP_HZ && moves >= 3 && max(tone.ups, tone.downs) >= SWEEP_SHARE * moves) return "sweeping" to null
        if (length >= STEADY_S && tone.highest - tone.lowest <= STEADY_SPREAD_HZ) return "steady" to null
        val same = this.ended.filter { abs(it.hz - (tone.lowest + tone.highest) / 2) <= SAME_PITCH_HZ }.map { it.start } + tone.start
        if (same.size >= PULSES) {
            val gaps = same.sorted().zipWithNext { a, b -> (b - a) / 1000 }.takeLast(PULSES - 1)
            val mean = gaps.average()
            val spread = sqrt(gaps.sumOf { (it - mean) * (it - mean) } / gaps.size)
            if (mean in PULSE_MIN_S..PULSE_MAX_S && spread <= PULSE_SPREAD * mean) return "pulsing" to doubleArrayOf(mean, 1 - spread / mean)
        }
        if (ended && length < BEACON_MAX_S && tone.lowest >= BEACON_LOW_HZ && tone.highest <= BEACON_HIGH_HZ) return "beacon" to null
        return "tone" to null
    }

    private fun row(tone: Tone, what: String, at: Double): JSONObject {
        val (kind, rhythm) = shape(tone, what == "end")
        return JSONObject()
            .put("t", Math.round(at * 10) / 10.0)
            .put("kind", "tone")
            .put("what", what)
            .put("hz", Math.round(if (what == "end") (tone.lowest + tone.highest) / 2 else tone.hz).toInt())
            .put("low_hz", Math.round(tone.lowest).toInt())
            .put("high_hz", Math.round(tone.highest).toInt())
            .put("start", Math.round(tone.start * 10) / 10.0)
            .put("end", if (what == "end") Math.round(tone.last * 10) / 10.0 else JSONObject.NULL)
            .put("level_db", Math.round(tone.levelSum / tone.frames * 10) / 10.0)
            .put("over_db", Math.round(tone.overSum / tone.frames * 10) / 10.0)
            .put("rise_db", Math.round(tone.riseSum / tone.frames * 10) / 10.0)
            .put("shape", kind)
            .put("period_s", rhythm?.let { Math.round(it[0] * 100) / 100.0 } ?: JSONObject.NULL)
            .put("regular", rhythm?.let { Math.round(it[1] * 100) / 100.0 } ?: JSONObject.NULL)
            .put("own", tone.own)
    }

    private fun data(peaks: List<DoubleArray>, at: Double) {
        val strong = peaks.filter { it[0] in LOW_HZ..DATA_HIGH_HZ && it[3] >= STAND_OUT_DB }
        if (strong.size >= DATA_TONES) {
            if (dataSince < 0) {
                dataSince = at
                dataOn = false
                dataBins.clear()
                dataHz.clear()
            }
            dataSeen = at
            for (p in strong) {
                dataBins += p[4].toInt()
                dataHz += p[0]
            }
            if (!dataOn && (at - dataSince) / 1000 >= DATA_MIN_S && dataBins.size >= DATA_BINS) {
                dataOn = true
                for (tone in tones) if (!tone.told) tone.inData = true
            }
            return
        }
        if (dataSince >= 0 && at - dataSeen > DATA_GAP_S * 1000) {
            if (dataOn) {
                val sorted = dataHz.sorted()
                keep(JSONObject()
                    .put("t", Math.round(at * 10) / 10.0)
                    .put("kind", "tone")
                    .put("what", "end")
                    .put("hz", Math.round(sorted[sorted.size / 2]).toInt())
                    .put("low_hz", Math.round(sorted.first()).toInt())
                    .put("high_hz", Math.round(sorted.last()).toInt())
                    .put("start", Math.round(dataSince * 10) / 10.0)
                    .put("end", Math.round(dataSeen * 10) / 10.0)
                    .put("level_db", JSONObject.NULL)
                    .put("over_db", JSONObject.NULL)
                    .put("rise_db", JSONObject.NULL)
                    .put("shape", "data")
                    .put("tones", dataBins.size)
                    .put("own", false))
                tones.removeAll { it.inData }
            }
            dataSince = -1.0
            dataOn = false
        }
    }

    private fun levels(at: Double) {
        if (bandSums.isEmpty()) return
        if (bandFrames == 0) bandStart = at
        for (b in bandSums.indices) {
            val from = Math.ceil((LOW_HZ + b * BAND_HZ) / BIN_HZ).toInt()
            val to = Math.floor((LOW_HZ + (b + 1) * BAND_HZ) / BIN_HZ).toInt() - 1
            var sum = 0.0
            for (k in from..to) sum += power[k]
            bandSums[b] += sum / max(1, to - from + 1)
        }
        bandFrames++
        if (at - bandStart >= LEVELS_EVERY_S * 1000) {
            val out = JSONArray()
            for (b in bandSums.indices) out.put(Math.round(db(bandSums[b] / bandFrames) * 10) / 10.0)
            keep(JSONObject().put("t", Math.round(at * 10) / 10.0).put("kind", "levels").put("from_hz", LOW_HZ.toInt()).put("step_hz", BAND_HZ.toInt()).put("db", out))
            java.util.Arrays.fill(bandSums, 0.0)
            bandFrames = 0
        }
    }

    private fun keep(row: JSONObject) {
        rows.addLast(row)
        while (rows.size > KEEP) rows.removeFirst()
        total++
    }

    @Synchronized
    fun read(from: Long): String {
        val oldest = total - rows.size
        val start = from.coerceIn(oldest, total)
        val out = JSONArray()
        for (i in (start - oldest).toInt() until rows.size) out.put(rows.elementAt(i))
        return JSONObject()
            .put("total", total)
            .put("from", start)
            .put("rows", out)
            .put("now_ms", now())
            .put("on", fft != null && problem.isEmpty())
            .put("rate", rate)
            .put("low_hz", LOW_HZ.toInt())
            .put("top_hz", if (fft != null) Math.round((last + 1) * BIN_HZ).toInt() else JSONObject.NULL)
            .put("open_tones", tones.count { it.told })
            .put("heard_s", Math.round(seconds * 10) / 10.0)
            .put("problem", problem)
            .toString()
    }

    @Synchronized
    fun top(hz: Double) {
        topHz = hz.coerceIn(LOW_HZ, MAX_TOP_HZ)
        rate = 0
    }

    @Synchronized
    fun reset() {
        rate = 0
        fft = null
        tones.clear()
        ended.clear()
        dataSince = -1.0
    }

    companion object {
        const val BIN_HZ = 46.875
        const val LOW_HZ = 15_000.0
        const val MAX_TOP_HZ = 24_000.0
        const val BAND_HZ = 1_000.0
        const val SILENT_DB = -160.0
        const val MIN_DB = -110.0
        const val PROMINENCE_DB = 6.0
        const val STAND_OUT_DB = 10.0
        const val NEIGHBOUR_NEAR = 3
        const val NEIGHBOUR_FAR = 6
        const val MAX_PEAKS = 8
        const val MATCH_HZ = 190.0
        const val PENDING_MATCH_HZ = 94.0
        const val DROP_DB = 20.0
        const val STEP_HZ = 12.0
        const val MIN_FRAMES = 3
        const val START_S = 0.25
        const val GAP_FRAMES = 5
        const val NOISE_FAR = 12
        const val SHARP_DB = 6.0
        const val WARM_FRAMES = 47
        const val WARM_RATE = 0.1
        const val MEAN_RATE = 0.02
        const val OUTLIER = 4.0
        const val CREEP = 0.002
        const val FAST_RATE = 0.3
        const val SETTLE_S = 0.5
        const val JUMP_FRAMES = 3
        const val STEADY_S = 10.0
        const val STEADY_SPREAD_HZ = 100.0
        const val SWEEP_HZ = 300.0
        const val SWEEP_SHARE = 0.7
        const val SAME_PITCH_HZ = 50.0
        const val PULSES = 4
        const val PULSE_MIN_S = 0.1
        const val PULSE_MAX_S = 10.0
        const val PULSE_SPREAD = 0.2
        const val PATTERN_KEEP_S = 60.0
        const val BEACON_LOW_HZ = 18_000.0
        const val BEACON_HIGH_HZ = 20_000.0
        const val BEACON_MAX_S = 1.0
        const val DATA_HIGH_HZ = 19_500.0
        const val DATA_TONES = 3
        const val DATA_BINS = 6
        const val DATA_GAP_S = 0.15
        const val DATA_MIN_S = 0.1
        const val MOTOR_HZ = 20_000.0
        const val MOTOR_SPREAD_HZ = 150.0
        const val LEVELS_EVERY_S = 1.0
        const val KEEP = 300
    }
}
