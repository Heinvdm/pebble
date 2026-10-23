package nz.pebble.robot.recall

import nz.pebble.robot.Atomic
import org.json.JSONObject
import java.io.File
import java.util.Locale

class RecallChoice(private val file: File) {
    class Saved(val rung: String, val why: String, val bench: JSONObject?)

    fun read(key: String): Saved? = try {
        if (!file.exists()) {
            null
        } else {
            val o = JSONObject(file.readText())
            val rung = o.optString("rung")
            if (o.optString("key") == key && rung in KEPT) Saved(rung, o.optString("why"), o.optJSONObject("bench")) else null
        }
    } catch (e: Exception) {
        null
    }

    fun keep(key: String, rung: String, why: String, bench: JSONObject?): Boolean = try {
        val o = JSONObject().put("key", key).put("rung", rung).put("why", why).put("at", System.currentTimeMillis())
        if (bench != null) o.put("bench", bench)
        Atomic.write(file, o.toString(2).toByteArray())
        true
    } catch (e: Exception) {
        false
    }

    fun raw(): JSONObject? = try {
        if (file.exists()) JSONObject(file.readText()) else null
    } catch (e: Exception) {
        null
    }

    fun forget() {
        file.delete()
    }

    companion object {
        const val NAME = "recall-choice.json"
        const val ONNX = "onnx"
        const val UNMEASURED = "unmeasured"
        const val STAND_IN = "stand-in"
        const val FAILED = "failed"
        const val MISSING = "missing"
        val KEPT = setOf(ONNX, STAND_IN, FAILED)
        const val QUERY_SLOW_MS = 500.0
        const val NOTE_SLOW_MS = 250.0

        fun decide(bench: JSONObject): Pair<String, String> {
            val query = bench.optDouble("query_ms", Double.NaN)
            val note = bench.optDouble("per_note_ms", Double.NaN)
            return when {
                query.isNaN() || note.isNaN() -> STAND_IN to "the sentence model could not be timed"
                query > QUERY_SLOW_MS -> STAND_IN to "a question took ${ms(query)} ms (more than ${ms(QUERY_SLOW_MS)})"
                note > NOTE_SLOW_MS -> STAND_IN to "a memory took ${ms(note)} ms in a batch (more than ${ms(NOTE_SLOW_MS)})"
                else -> ONNX to "a question takes ${ms(query)} ms and a memory ${ms(note)} ms in a batch"
            }
        }

        fun describe(saved: JSONObject?): String {
            if (saved == null) return "not measured yet; it measures itself once the eyes and ears are running"
            val bench = saved.optJSONObject("bench")
            return when (saved.optString("rung")) {
                ONNX -> {
                    val core = bench?.opt("core")?.takeIf { it != JSONObject.NULL }?.let { " on core $it" } ?: ""
                    "the sentence model$core: a question about ${ms(bench?.optDouble("query_ms") ?: Double.NaN)} ms, a memory about ${ms(bench?.optDouble("per_note_ms") ?: Double.NaN)} ms in a batch of ${bench?.optInt("batch", 32) ?: 32}"
                }
                STAND_IN -> "the simple stand-in, because ${saved.optString("why")}"
                FAILED -> "the simple stand-in, because ${saved.optString("why")}"
                else -> "not measured yet"
            }
        }

        private fun ms(value: Double): String = if (value.isNaN()) "?" else String.format(Locale.ROOT, "%.0f", value)
    }
}
