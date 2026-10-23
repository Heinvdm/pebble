package nz.pebble.robot.keeper

import android.content.Context
import android.os.Build
import android.os.PowerManager
import nz.pebble.robot.Atomic
import org.json.JSONObject
import java.io.File

class HeatLevel(private val coolDownMs: Long = COOL_DOWN_MS) {
    var level = COOL
        private set
    private var lowerSince = 0L

    fun update(now: Long, headroom: Double, status: Int): String {
        val reading = raw(headroom, status)
        if (rank(reading) >= rank(level)) {
            level = reading
            lowerSince = 0L
            return level
        }
        if (lowerSince == 0L) lowerSince = now
        if (now - lowerSince >= coolDownMs) {
            level = reading
            lowerSince = 0L
        }
        return level
    }

    companion object {
        const val COOL = "cool"
        const val WARM = "warm"
        const val HOT = "hot"
        const val COOL_DOWN_MS = 120_000L
        const val WARM_AT = 0.6
        const val HOT_AT = 0.8
        const val STATUS_MODERATE = 2
        const val STATUS_SEVERE = 3

        fun raw(headroom: Double, status: Int): String = when {
            status >= STATUS_SEVERE || (!headroom.isNaN() && headroom >= HOT_AT) -> HOT
            status >= STATUS_MODERATE || (!headroom.isNaN() && headroom >= WARM_AT) -> WARM
            else -> COOL
        }

        fun rank(level: String): Int = when (level) {
            HOT -> 2
            WARM -> 1
            else -> 0
        }

        fun eyesFactor(level: String, slow: Boolean): Double = when {
            level == HOT -> 0.35
            level == WARM || slow -> 0.6
            else -> 1.0
        }
    }
}

object Thermal {
    fun read(context: Context): Pair<Double, Int> = try {
        val power = context.getSystemService(PowerManager::class.java)
        val status = power.currentThermalStatus
        val headroom = if (Build.VERSION.SDK_INT >= 30) power.getThermalHeadroom(FORECAST_S).toDouble() else Double.NaN
        headroom to status
    } catch (e: Exception) {
        Double.NaN to 0
    }

    const val FORECAST_S = 10
}

class SpeedWatch(private val windowMs: Long = WINDOW_MS) {
    private val samples = ArrayDeque<Pair<Long, Map<String, Double>>>()

    fun add(now: Long, metrics: Map<String, Double>) {
        if (metrics.isEmpty()) return
        val last = samples.lastOrNull()
        if (last != null && (metrics["tokens_predicted_total"] ?: 0.0) < (last.second["tokens_predicted_total"] ?: 0.0)) samples.clear()
        samples.addLast(now to metrics)
        while (samples.size > 2 && now - samples.first().first > windowMs) samples.removeFirst()
    }

    fun clear() = samples.clear()

    private fun rate(count: String, seconds: String, least: Double): Double? {
        val first = samples.firstOrNull()?.second ?: return null
        val last = samples.lastOrNull()?.second ?: return null
        val tokens = (last[count] ?: return null) - (first[count] ?: return null)
        val time = (last[seconds] ?: return null) - (first[seconds] ?: return null)
        if (tokens < least || time <= 0) return null
        return tokens / time
    }

    fun writeTps(): Double? = rate("tokens_predicted_total", "tokens_predicted_seconds_total", LEAST_TOKENS)

    fun readTps(): Double? = rate("prompt_tokens_total", "prompt_seconds_total", LEAST_TOKENS)

    fun accepted(): Double? {
        val first = samples.firstOrNull()?.second ?: return null
        val last = samples.lastOrNull()?.second ?: return null
        val drafted = (last["spec_decode_num_draft_tokens_total"] ?: return null) - (first["spec_decode_num_draft_tokens_total"] ?: return null)
        val taken = (last["spec_decode_num_accepted_tokens_total"] ?: return null) - (first["spec_decode_num_accepted_tokens_total"] ?: return null)
        return if (drafted >= LEAST_TOKENS) taken / drafted else null
    }

    fun slow(benchWriteTps: Double?): Boolean {
        val now = writeTps() ?: return false
        if (benchWriteTps == null || benchWriteTps <= 0) return false
        return now < benchWriteTps * SLOW_SHARE
    }

    fun json(benchWriteTps: Double?): JSONObject = JSONObject()
        .put("write_tps", writeTps()?.let { Math.round(it * 10) / 10.0 } ?: JSONObject.NULL)
        .put("read_tps", readTps()?.let { Math.round(it * 10) / 10.0 } ?: JSONObject.NULL)
        .put("drafts_accepted", accepted()?.let { Math.round(it * 100) / 100.0 } ?: JSONObject.NULL)
        .put("bench_write_tps", benchWriteTps ?: JSONObject.NULL)
        .put("slow", slow(benchWriteTps))

    companion object {
        const val WINDOW_MS = 10 * 60_000L
        const val LEAST_TOKENS = 100.0
        const val SLOW_SHARE = 1.0 / 1.3
    }
}

object PaceFile {
    const val NAME = "pace.json"
    const val STALE_MS = 30_000L

    fun write(file: File, heat: JSONObject, slow: Boolean) {
        val o = JSONObject(heat.toString())
            .put("slow", slow)
            .put("eyes", HeatLevel.eyesFactor(heat.optString("level", HeatLevel.COOL), slow))
            .put("at", System.currentTimeMillis())
        Atomic.write(file, o.toString().toByteArray())
    }

    fun read(file: File): JSONObject? = try {
        if (file.exists()) JSONObject(file.readText()).takeIf { System.currentTimeMillis() - it.optLong("at", 0L) < STALE_MS } else null
    } catch (e: Exception) {
        null
    }

    fun forBrain(context: Context, file: File): JSONObject {
        read(file)?.let { return it }
        val (headroom, status) = Thermal.read(context)
        val level = HeatLevel.raw(headroom, status)
        return JSONObject()
            .put("headroom", if (headroom.isNaN()) -1.0 else Math.round(headroom * 100) / 100.0)
            .put("status", status)
            .put("level", level)
            .put("slow", false)
            .put("eyes", HeatLevel.eyesFactor(level, false))
            .put("at", System.currentTimeMillis())
    }
}

class PaceReader(private val file: File, private val everyMs: Long = 5_000L) {
    @Volatile private var cached: JSONObject? = null
    @Volatile private var readAt = 0L

    fun now(): JSONObject? {
        val at = System.currentTimeMillis()
        if (at - readAt >= everyMs) {
            cached = PaceFile.read(file)
            readAt = at
        }
        return cached
    }

    fun eyesFactor(): Double = now()?.optDouble("eyes", 1.0)?.takeIf { !it.isNaN() }?.coerceIn(0.1, 1.0) ?: 1.0
}
