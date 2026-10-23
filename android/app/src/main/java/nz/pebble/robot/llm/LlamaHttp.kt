package nz.pebble.robot.llm

import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.net.HttpURLConnection
import java.net.URL

class LlamaHttp(private val port: Int) {
    class Answer(
        val firstMs: Double?,
        val fifthMs: Double?,
        val twentiethMs: Double?,
        val tokens: Int,
        val promptN: Int,
        val promptMs: Double,
        val promptTps: Double,
        val writeTps: Double,
        val totalMs: Double,
    ) {
        fun json(): JSONObject = JSONObject()
            .put("first_ms", firstMs?.let { round(it) } ?: JSONObject.NULL)
            .put("fifth_ms", fifthMs?.let { round(it) } ?: JSONObject.NULL)
            .put("twentieth_ms", twentiethMs?.let { round(it) } ?: JSONObject.NULL)
            .put("tokens", tokens)
            .put("prompt_n", promptN)
            .put("prompt_ms", round(promptMs))
            .put("prompt_tps", round(promptTps))
            .put("write_tps", round(writeTps))
            .put("total_ms", round(totalMs))
    }

    private fun open(path: String, timeoutMs: Int, connectMs: Int = 2_000): HttpURLConnection {
        val connection = URL("http://127.0.0.1:$port$path").openConnection() as HttpURLConnection
        connection.connectTimeout = connectMs
        connection.readTimeout = timeoutMs
        connection.useCaches = false
        connection.setRequestProperty("Connection", "close")
        return connection
    }

    fun complete(prompt: String, nPredict: Int, timeoutMs: Int, stream: Boolean = true, temperature: Double = 0.7): Answer {
        val body = JSONObject()
            .put("prompt", prompt)
            .put("n_predict", nPredict)
            .put("stream", stream)
            .put("cache_prompt", true)
            .put("ignore_eos", true)
            .put("temperature", temperature)
            .put("return_tokens", true)
            .toString()
            .toByteArray()
        val connection = open("/completion", timeoutMs)
        connection.requestMethod = "POST"
        connection.doOutput = true
        connection.setRequestProperty("Content-Type", "application/json")
        connection.setFixedLengthStreamingMode(body.size)
        val started = System.nanoTime()
        try {
            connection.outputStream.use { it.write(body) }
            val code = connection.responseCode
            if (code != 200) throw IllegalStateException("the model server answered $code")
            var tokens = 0
            var first: Double? = null
            var fifth: Double? = null
            var twentieth: Double? = null
            var timings: JSONObject? = null
            BufferedReader(InputStreamReader(connection.inputStream, Charsets.UTF_8)).use { reader ->
                if (!stream) {
                    val o = JSONObject(reader.readText())
                    tokens = o.optJSONArray("tokens")?.length() ?: o.optInt("tokens_predicted", 0)
                    timings = o.optJSONObject("timings")
                    return@use
                }
                while (true) {
                    val line = reader.readLine() ?: break
                    if (!line.startsWith("data:")) continue
                    val data = line.substring(5).trim()
                    if (data.isEmpty() || data == "[DONE]") continue
                    val o = try {
                        JSONObject(data)
                    } catch (e: Exception) {
                        continue
                    }
                    val got = o.optJSONArray("tokens")?.length() ?: if (o.optString("content").isNotEmpty()) 1 else 0
                    if (got > 0) {
                        val at = (System.nanoTime() - started) / 1e6
                        val before = tokens
                        tokens += got
                        if (before < 1) first = at
                        if (before < 5 && tokens >= 5) fifth = at
                        if (before < 20 && tokens >= 20) twentieth = at
                    }
                    o.optJSONObject("timings")?.let { timings = it }
                    if (o.optBoolean("stop")) break
                }
            }
            val t = timings ?: JSONObject()
            return Answer(first, fifth, twentieth, tokens, t.optInt("prompt_n", 0), t.optDouble("prompt_ms", 0.0), t.optDouble("prompt_per_second", 0.0), t.optDouble("predicted_per_second", 0.0), (System.nanoTime() - started) / 1e6)
        } finally {
            connection.disconnect()
        }
    }

    fun abandon(prompt: String, afterMs: Long, timeoutMs: Int): Long? {
        val body = JSONObject().put("prompt", prompt).put("n_predict", 1).put("stream", false).put("cache_prompt", true).toString().toByteArray()
        val connection = open("/completion", timeoutMs)
        connection.requestMethod = "POST"
        connection.doOutput = true
        connection.setRequestProperty("Content-Type", "application/json")
        connection.setFixedLengthStreamingMode(body.size)
        val finished = java.util.concurrent.atomic.AtomicBoolean(false)
        val reader = Thread({
            try {
                connection.outputStream.use { it.write(body) }
                connection.inputStream.use { it.readBytes() }
                finished.set(true)
            } catch (e: Exception) {
                finished.set(false)
            }
        }, "pebble-bench-abandon")
        reader.isDaemon = true
        reader.start()
        reader.join(afterMs)
        if (finished.get()) return null
        val closedAt = System.nanoTime()
        connection.disconnect()
        return closedAt
    }

    fun metrics(timeoutMs: Int = 2_000): Map<String, Double> {
        val connection = open("/metrics", timeoutMs)
        try {
            if (connection.responseCode != 200) return emptyMap()
            return parseMetrics(connection.inputStream.bufferedReader().readText())
        } catch (e: Exception) {
            return emptyMap()
        } finally {
            connection.disconnect()
        }
    }

    fun slots(timeoutMs: Int): String? {
        val connection = open("/slots", timeoutMs, timeoutMs)
        return try {
            if (connection.responseCode == 200) connection.inputStream.bufferedReader().use { it.readText() } else null
        } catch (e: Exception) {
            null
        } finally {
            connection.disconnect()
        }
    }

    companion object {
        fun round(value: Double): Double = Math.round(value * 10) / 10.0

        fun writing(slots: String): Boolean = try {
            val all = org.json.JSONArray(slots)
            (0 until all.length()).any { i ->
                val slot = all.optJSONObject(i)
                slot != null && slot.optBoolean("is_processing") && (slot.optJSONArray("next_token")?.optJSONObject(0)?.optInt("n_decoded", 0) ?: 0) > 0
            }
        } catch (e: Exception) {
            false
        }

        fun parseMetrics(text: String): Map<String, Double> {
            val out = HashMap<String, Double>()
            for (line in text.lineSequence()) {
                if (line.isBlank() || line.startsWith("#") || !line.startsWith("llamacpp:")) continue
                val name = line.substringBefore(' ').removePrefix("llamacpp:")
                if (name.contains('{')) continue
                line.substringAfterLast(' ').toDoubleOrNull()?.let { out[name] = it }
            }
            return out
        }
    }
}
