package nz.pebble.robot.brain

import android.annotation.SuppressLint
import android.content.Context
import android.media.AudioAttributes
import android.media.AudioDeviceInfo
import android.media.AudioFormat
import android.media.AudioManager
import android.media.AudioRecord
import android.media.AudioTrack
import android.media.MediaRecorder
import android.media.MicrophoneInfo
import android.media.audiofx.AcousticEchoCanceler
import android.util.Log
import nz.pebble.robot.Atomic
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.cos
import kotlin.math.log10
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sin
import kotlin.math.sqrt

object ProbeMath {
    const val SOUND_M_S = 343.0

    fun db(power: Double): Double = if (power > 0) 10 * log10(power) else -160.0

    fun bands(samples: FloatArray, rate: Int, size: Int = 2048, bandHz: Double = 1_000.0): DoubleArray {
        val fft = Fft(size)
        val window = DoubleArray(size) { 0.5 - 0.5 * cos(2 * PI * (it + 0.5) / size) }
        val norm = (window.sum() / 2).let { it * it }
        val re = DoubleArray(size)
        val im = DoubleArray(size)
        val power = DoubleArray(size / 2)
        val sums = DoubleArray(size / 2)
        val frame = FloatArray(size)
        var frames = 0
        var at = 0
        while (at + size <= samples.size) {
            System.arraycopy(samples, at, frame, 0, size)
            fft.power(frame, window, re, im, power)
            for (k in sums.indices) sums[k] += power[k]
            frames++
            at += size
        }
        val binHz = rate.toDouble() / size
        val count = Math.floor(rate / 2.0 / bandHz).toInt()
        return DoubleArray(count) { b ->
            val from = max(1, Math.ceil(b * bandHz / binHz).toInt())
            val to = min(size / 2 - 1, Math.floor((b + 1) * bandHz / binHz).toInt() - 1)
            var sum = 0.0
            for (k in from..to) sum += sums[k]
            val mean = if (frames > 0 && to >= from) sum / frames / (to - from + 1) else 0.0
            Math.round(db(mean / norm) * 10) / 10.0
        }
    }

    fun cliff(floors: DoubleArray): Boolean = floors.size > 10 && floors[6] - floors[9] >= 25.0

    fun correlation(a: FloatArray, b: FloatArray, lag: Int): Double {
        var ab = 0.0
        var aa = 0.0
        var bb = 0.0
        for (i in max(0, -lag) until min(a.size, b.size - lag)) {
            val x = a[i].toDouble()
            val y = b[i + lag].toDouble()
            ab += x * y
            aa += x * x
            bb += y * y
        }
        return if (aa > 0 && bb > 0) ab / sqrt(aa * bb) else 0.0
    }

    fun delay(a: FloatArray, b: FloatArray, reach: Int): Pair<Double, Double> {
        var bestLag = 0
        var best = -2.0
        val values = DoubleArray(2 * reach + 1)
        for (lag in -reach..reach) {
            val c = correlation(a, b, lag)
            values[lag + reach] = c
            if (c > best) {
                best = c
                bestLag = lag
            }
        }
        val i = bestLag + reach
        val shift = if (i in 1 until values.size - 1) {
            val l = values[i - 1]
            val r = values[i + 1]
            val bend = l - 2 * best + r
            if (bend < 0) (0.5 * (l - r) / bend).coerceIn(-0.5, 0.5) else 0.0
        } else {
            0.0
        }
        return (bestLag + shift) to best
    }

    fun click(rate: Int, amplitude: Double): FloatArray {
        val n = max(8, rate / 1000)
        return FloatArray(n) {
            val t = it.toDouble() / rate
            val sweep = 2 * PI * (2_000.0 * t + 0.5 * (10_000.0 / (n.toDouble() / rate)) * t * t)
            (amplitude * sin(sweep) * (0.5 - 0.5 * cos(2 * PI * (it + 0.5) / n))).toFloat()
        }
    }

    fun onset(channel: FloatArray, template: FloatArray, from: Int, to: Int): Pair<Int, Double> {
        var best = 0
        var bestValue = 0.0
        val end = min(to, channel.size - template.size)
        for (i in max(0, from) until end) {
            var sum = 0.0
            for (j in template.indices) sum += channel[i + j] * template[j]
            if (abs(sum) > bestValue) {
                bestValue = abs(sum)
                best = i
            }
        }
        return best to bestValue
    }

    fun spacing(delaysSamples: List<Double>, rate: Int): Double? {
        val ahead = delaysSamples.filter { it >= 2 }
        val behind = delaysSamples.filter { it <= -2 }
        if (ahead.isEmpty() || behind.isEmpty()) return null
        val mean = (ahead.average() - behind.average()) / 2
        return mean / rate * SOUND_M_S
    }

    fun top(rise: DoubleArray, fromBand: Int, needDb: Double = 10.0): Int {
        var top = -1
        for (b in fromBand until rise.size) if (rise[b] >= needDb) top = b else if (top >= 0) break
        return top
    }

    fun sweep(rate: Int, seconds: Double, lowHz: Double, highHz: Double, amplitude: Double): FloatArray {
        val n = (rate * seconds).toInt()
        val k = Math.log(highHz / lowHz)
        val fade = rate / 50
        return FloatArray(n) {
            val t = it.toDouble() / rate
            val phase = 2 * PI * lowHz * seconds / k * (Math.exp(t / seconds * k) - 1)
            val edge = min(1.0, min(it.toDouble() / fade, (n - 1 - it).toDouble() / fade))
            (amplitude * edge * sin(phase)).toFloat()
        }
    }
}

class MicProbe(private val context: Context, private val microphone: Microphone, private val file: File) {
    data class Config(val source: Int, val sourceName: String, val rate: Int, val layout: String) {
        val channels: Int get() = when (layout) {
            "stereo", "index2" -> 2
            "index3" -> 3
            else -> 1
        }

        fun json(): JSONObject = JSONObject().put("source", sourceName).put("rate", rate).put("layout", layout)
    }

    private class Heard(val config: Config, val record: AudioRecord, val channels: Array<FloatArray>)

    @Volatile var phase = ""
        private set

    fun run(options: JSONObject): JSONObject {
        val started = System.currentTimeMillis()
        val out = JSONObject().put("at", started).put("properties", properties())
        val seconds = options.optDouble("seconds", SECONDS).coerceIn(0.5, 10.0)
        val configs = configs(options)
        val results = JSONArray()
        var best: Config? = null
        var bestScore = -1
        for (config in configs) {
            phase = "listening with ${config.sourceName} at ${config.rate / 1000} kHz, ${config.layout}"
            val result = listen(config, seconds)
            results.put(result)
            val score = score(config, result)
            if (score > bestScore) {
                bestScore = score
                best = config
            }
        }
        out.put("configs", results)
        val chosen = best
        if (chosen != null && options.optBoolean("clicks", true)) {
            phase = "clicking from each speaker"
            out.put("clicks", clicks(chosen, options.optDouble("click_level", CLICK_LEVEL)))
        }
        val wide = configs.firstOrNull { it.rate == 48_000 && it.layout == "mono" && results.find(it)?.optBoolean("opened") == true } ?: chosen
        if (wide != null && options.optBoolean("sweep", true)) {
            phase = "playing a quiet high sweep"
            out.put("sweep", sweep(wide, results.find(wide)?.optJSONArray("floors")?.optJSONArray(0), options.optDouble("sweep_level", SWEEP_LEVEL)))
        }
        out.put("suggested", suggest(out))
        out.put("took_s", Math.round((System.currentTimeMillis() - started) / 100.0) / 10.0)
        phase = ""
        try {
            Atomic.write(file, out.toString().toByteArray())
        } catch (e: Exception) {
            Log.w(TAG, "the probe's numbers could not be kept", e)
        }
        return out
    }

    private fun JSONArray.find(config: Config): JSONObject? {
        for (i in 0 until length()) {
            val o = getJSONObject(i)
            val c = o.optJSONObject("config") ?: continue
            if (c.optString("source") == config.sourceName && c.optInt("rate") == config.rate && c.optString("layout") == config.layout) return o
        }
        return null
    }

    private fun score(config: Config, result: JSONObject): Int {
        if (!result.optBoolean("opened") || config.rate != 48_000 || config.channels < 2) return -1
        val separate = !result.optBoolean("copied", true)
        val rank = SOURCES.indexOfFirst { it.first == config.source }.let { if (it < 0) 0 else SOURCES.size - it }
        return (if (separate) 100 else 0) + (if (!result.optBoolean("cliff_at_8k", true)) 50 else 0) + rank
    }

    private fun configs(options: JSONObject): List<Config> {
        val rates = options.optJSONArray("rates")?.let { a -> (0 until a.length()).map { a.getInt(it) } } ?: RATES
        val layouts = options.optJSONArray("layouts")?.let { a -> (0 until a.length()).map { a.getString(it) } } ?: LAYOUTS
        val sources = options.optJSONArray("sources")?.let { a -> (0 until a.length()).map { a.getString(it) } }
        return SOURCES.filter { sources == null || it.second in sources }.flatMap { (source, name) -> rates.flatMap { rate -> layouts.map { Config(source, name, rate, it) } } }
    }

    private fun format(config: Config): AudioFormat {
        val builder = AudioFormat.Builder().setEncoding(AudioFormat.ENCODING_PCM_16BIT).setSampleRate(config.rate)
        when (config.layout) {
            "stereo" -> builder.setChannelMask(AudioFormat.CHANNEL_IN_STEREO)
            "index2" -> builder.setChannelIndexMask(0b11)
            "index3" -> builder.setChannelIndexMask(0b111)
            else -> builder.setChannelMask(AudioFormat.CHANNEL_IN_MONO)
        }
        return builder.build()
    }

    @SuppressLint("MissingPermission")
    private fun open(config: Config): Pair<AudioRecord?, String> = try {
        val made = AudioRecord.Builder()
            .setAudioSource(config.source)
            .setAudioFormat(format(config))
            .setBufferSizeInBytes(config.rate / 2 * 2 * config.channels)
            .build()
        if (made.state != AudioRecord.STATE_INITIALIZED) {
            made.release()
            null to "it would not start"
        } else {
            made to ""
        }
    } catch (e: Exception) {
        null to (e.message ?: e.javaClass.simpleName)
    }

    private fun record(record: AudioRecord, config: Config, seconds: Double, during: (() -> Unit)? = null): Array<FloatArray> {
        val channels = record.channelCount
        val rate = record.sampleRate
        val total = (rate * seconds).toInt()
        val skip = (rate * SKIP_S).toInt()
        val out = Array(channels) { FloatArray(total) }
        val chunk = ShortArray(rate / 50 * channels)
        val forwardPlan = if (rate % Microphone.RATE == 0 && rate / Microphone.RATE in MicPlan.FACTORS) MicPlan(rate, 1, 0) else null
        val narrow = forwardPlan?.takeIf { it.wide }?.let { Narrow(it) }
        val mono = ShortArray(rate / 50)
        record.startRecording()
        var seen = 0
        var player: Thread? = null
        try {
            while (seen < skip + total) {
                val count = record.read(chunk, 0, chunk.size)
                if (count <= 0) break
                val frames = count / channels
                for (i in 0 until frames) mono[i] = chunk[i * channels]
                if (forwardPlan != null) microphone.pass(mono, frames, forwardPlan, narrow)
                for (i in 0 until frames) {
                    val at = seen + i - skip
                    if (at in 0 until total) for (c in 0 until channels) out[c][at] = chunk[i * channels + c] / 32768f
                }
                seen += frames
                if (during != null && player == null && seen >= skip) player = Thread(during, "pebble-probe-sound").also { it.start() }
            }
        } finally {
            player?.join(10_000)
            try {
                record.stop()
            } catch (e: Exception) {
                Log.d(TAG, "the probe's recording was already stopped")
            }
        }
        return out
    }

    private fun listen(config: Config, seconds: Double): JSONObject {
        val result = JSONObject().put("config", config.json())
        val (record, why) = open(config)
        if (record == null) return result.put("opened", false).put("why", why)
        try {
            val channels = record(record, config, seconds)
            val rate = record.sampleRate
            result.put("opened", true).put("rate", rate).put("channels", record.channelCount)
            val floors = JSONArray()
            val levels = JSONArray()
            for (c in channels) {
                val bands = ProbeMath.bands(c, rate)
                floors.put(JSONArray(bands.toList()))
                var sum = 0.0
                for (x in c) sum += x.toDouble() * x
                levels.put(Math.round(ProbeMath.db(sum / max(1, c.size)) * 10) / 10.0)
            }
            result.put("floors", floors).put("level_db", levels)
            val first = floors.optJSONArray(0)?.let { a -> DoubleArray(a.length()) { a.getDouble(it) } }
            if (first != null && rate >= 32_000) result.put("cliff_at_8k", ProbeMath.cliff(first))
            if (channels.size >= 2) {
                val same = ProbeMath.correlation(channels[0], channels[1], 0)
                val (lag, peak) = ProbeMath.delay(channels[0], channels[1], rate / 1000)
                result.put("correlation", Math.round(same * 10000) / 10000.0).put("best_lag", Math.round(lag * 100) / 100.0).put("best_correlation", Math.round(peak * 10000) / 10000.0)
                result.put("copied", same > COPIED)
            }
            result.put("microphones", active(record))
            result.put("echo_canceller", echo(record.audioSessionId))
        } catch (e: Exception) {
            result.put("opened", true).put("why", "listening failed: ${e.message}")
        } finally {
            record.release()
        }
        return result
    }

    private fun echo(session: Int): String = try {
        if (!AcousticEchoCanceler.isAvailable()) "not offered" else AcousticEchoCanceler.create(session)?.let { aec ->
            val on = try {
                aec.enabled = true
                aec.enabled
            } catch (e: Exception) {
                false
            }
            aec.release()
            if (on) "attaches" else "would not switch on"
        } ?: "could not be made"
    } catch (e: Exception) {
        "failed: ${e.message}"
    }

    private fun active(record: AudioRecord): JSONArray {
        val out = JSONArray()
        try {
            for (m in record.activeMicrophones) out.put(describe(m))
        } catch (e: Exception) {
            out.put(JSONObject().put("problem", e.message ?: "unknown"))
        }
        return out
    }

    private fun describe(m: MicrophoneInfo): JSONObject {
        val o = JSONObject()
            .put("id", m.id)
            .put("description", m.description)
            .put("type", m.type)
            .put("location", m.location)
            .put("group", m.group)
            .put("index_in_group", m.indexInTheGroup)
            .put("directionality", m.directionality)
            .put("sensitivity", m.sensitivity.toDouble())
            .put("max_spl", m.maxSpl.toDouble())
            .put("min_spl", m.minSpl.toDouble())
        val p = m.position
        if (p != MicrophoneInfo.POSITION_UNKNOWN) o.put("position_m", JSONArray().put(p.x.toDouble()).put(p.y.toDouble()).put(p.z.toDouble()))
        val mapping = JSONArray()
        for (pair in m.channelMapping) mapping.put(JSONArray().put(pair.first).put(if (pair.second == MicrophoneInfo.CHANNEL_MAPPING_DIRECT) "direct" else "processed"))
        o.put("channels", mapping)
        val response = JSONArray()
        for (pair in m.frequencyResponse.take(64)) response.put(JSONArray().put(pair.first.toDouble()).put(pair.second.toDouble()))
        o.put("frequency_response", response)
        return o
    }

    private fun properties(): JSONObject {
        val am = context.getSystemService(AudioManager::class.java)
        val o = JSONObject()
            .put("unprocessed", am.getProperty(AudioManager.PROPERTY_SUPPORT_AUDIO_SOURCE_UNPROCESSED) ?: JSONObject.NULL)
            .put("mic_near_ultrasound", am.getProperty(AudioManager.PROPERTY_SUPPORT_MIC_NEAR_ULTRASOUND) ?: JSONObject.NULL)
            .put("speaker_near_ultrasound", am.getProperty(AudioManager.PROPERTY_SUPPORT_SPEAKER_NEAR_ULTRASOUND) ?: JSONObject.NULL)
            .put("output_rate", am.getProperty(AudioManager.PROPERTY_OUTPUT_SAMPLE_RATE) ?: JSONObject.NULL)
            .put("output_frames", am.getProperty(AudioManager.PROPERTY_OUTPUT_FRAMES_PER_BUFFER) ?: JSONObject.NULL)
        val mics = JSONArray()
        try {
            for (m in am.microphones) mics.put(describe(m))
        } catch (e: Exception) {
            mics.put(JSONObject().put("problem", e.message ?: "unknown"))
        }
        o.put("microphones", mics)
        val outputs = JSONArray()
        for (d in am.getDevices(AudioManager.GET_DEVICES_OUTPUTS)) outputs.put(JSONObject().put("id", d.id).put("type", d.type).put("name", d.productName?.toString() ?: ""))
        o.put("outputs", outputs)
        return o
    }

    private fun track(rate: Int, stereo: Boolean, usage: Int, values: Int): AudioTrack = AudioTrack.Builder()
        .setAudioAttributes(AudioAttributes.Builder().setUsage(usage).setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION).build())
        .setAudioFormat(AudioFormat.Builder().setEncoding(AudioFormat.ENCODING_PCM_FLOAT).setSampleRate(rate).setChannelMask(if (stereo) AudioFormat.CHANNEL_OUT_STEREO else AudioFormat.CHANNEL_OUT_MONO).build())
        .setTransferMode(AudioTrack.MODE_STATIC)
        .setBufferSizeInBytes(max(4, values * 4))
        .build()

    private fun clicks(config: Config, level: Double): JSONObject {
        val out = JSONObject().put("config", config.json())
        val (record, why) = open(config)
        if (record == null) return out.put("problem", "the two-channel recording would not open: $why")
        val rate = record.sampleRate
        val click = ProbeMath.click(rate, level)
        val groups = listOf("left speaker channel", "right speaker channel", "earpiece")
        val results = JSONArray()
        try {
            for (group in groups) {
                val gap = (rate * CLICK_GAP_S).toInt()
                val lead = (rate * CLICK_LEAD_S).toInt()
                val stereo = group != "earpiece"
                val frames = lead + CLICKS * gap
                val sound = FloatArray(frames * (if (stereo) 2 else 1))
                for (n in 0 until CLICKS) for (j in click.indices) {
                    val at = lead + n * gap + j
                    if (stereo) sound[at * 2 + (if (group.startsWith("left")) 0 else 1)] = click[j] else sound[at] = click[j]
                }
                val usage = if (stereo) AudioAttributes.USAGE_MEDIA else AudioAttributes.USAGE_VOICE_COMMUNICATION
                val player = try {
                    track(rate, stereo, usage, sound.size).also { t ->
                        t.write(sound, 0, sound.size, AudioTrack.WRITE_BLOCKING)
                        if (!stereo) {
                            val ear = context.getSystemService(AudioManager::class.java).getDevices(AudioManager.GET_DEVICES_OUTPUTS).firstOrNull { it.type == AudioDeviceInfo.TYPE_BUILTIN_EARPIECE }
                            if (ear == null || !t.setPreferredDevice(ear)) {
                                t.release()
                                results.put(JSONObject().put("group", group).put("problem", "no earpiece to click from"))
                                continue
                            }
                        }
                    }
                } catch (e: Exception) {
                    results.put(JSONObject().put("group", group).put("problem", "the click would not play: ${e.message}"))
                    continue
                }
                microphone.probing = true
                val heard = try {
                    record(record, config, (frames + gap).toDouble() / rate + SKIP_S) { player.play() }
                } finally {
                    microphone.probing = false
                    player.release()
                }
                results.put(analyse(group, heard, click, rate, lead, gap))
            }
        } finally {
            record.release()
        }
        out.put("groups", results)
        val delays = (0 until results.length()).mapNotNull { results.getJSONObject(it).takeIf { g -> g.optDouble("snr_db", 0.0) >= HEARD_DB && g.has("delay_samples") }?.getDouble("delay_samples") }
        val spacing = ProbeMath.spacing(delays, rate)
        out.put("heard", delays.isNotEmpty())
        out.put("two_separate_microphones", spacing != null)
        out.put("spacing_m", spacing?.let { Math.round(it * 1000) / 1000.0 } ?: JSONObject.NULL)
        out.put("verdict", when {
            delays.isEmpty() -> "no click was heard clearly, so this says nothing about the microphones"
            spacing != null -> "two separate microphones about ${Math.round(spacing * 1000) / 10.0} cm apart"
            delays.all { abs(it) < 0.5 } -> "both channels hear every click at the same moment: one microphone copied twice, or a mix"
            else -> "the channels differ, but the clicks did not swap sides; read the numbers"
        })
        return out
    }

    private fun analyse(group: String, heard: Array<FloatArray>, click: FloatArray, rate: Int, lead: Int, gap: Int): JSONObject {
        val o = JSONObject().put("group", group)
        if (heard.size < 2) return o.put("problem", "only one channel came back")
        val delays = ArrayList<Double>()
        val snrs = ArrayList<Double>()
        val window = rate / 200
        for (n in 0 until CLICKS) {
            val expected = lead + n * gap
            val (start, _) = ProbeMath.onset(heard[0], click, expected - rate / 20, expected + rate / 5)
            val from = max(0, start - window / 4)
            val to = min(heard[0].size, start + window)
            if (to - from < 16) continue
            val a = heard[0].copyOfRange(from, to)
            val b = heard[1].copyOfRange(from, to)
            val (lag, _) = ProbeMath.delay(a, b, rate / 1000)
            val quietFrom = max(0, start - rate / 10)
            val quiet = heard[0].copyOfRange(quietFrom, max(quietFrom + 1, start - rate / 50))
            val signal = a.sumOf { it.toDouble() * it } / a.size
            val noise = quiet.sumOf { it.toDouble() * it } / quiet.size
            delays += lag
            snrs += ProbeMath.db(signal / max(noise, 1e-12))
        }
        if (delays.isEmpty()) return o.put("problem", "no clicks found")
        val median = delays.sorted()[delays.size / 2]
        return o.put("delay_samples", Math.round(median * 100) / 100.0)
            .put("delay_us", Math.round(median / rate * 1e6))
            .put("spread_samples", Math.round((delays.maxOrNull()!! - delays.minOrNull()!!) * 100) / 100.0)
            .put("snr_db", Math.round(snrs.sorted()[snrs.size / 2] * 10) / 10.0)
            .put("first", if (median > 0.5) "channel 0" else if (median < -0.5) "channel 1" else "both at once")
    }

    private fun sweep(config: Config, floor: JSONArray?, level: Double): JSONObject {
        val out = JSONObject().put("config", config.json())
        val (record, why) = open(config)
        if (record == null) return out.put("problem", "the recording would not open: $why")
        val rate = record.sampleRate
        val sound = ProbeMath.sweep(rate, SWEEP_S, SWEEP_LOW_HZ, min(SWEEP_HIGH_HZ, rate / 2.0 - 500), level)
        try {
            val player = try {
                track(rate, false, AudioAttributes.USAGE_MEDIA, sound.size).also { it.write(sound, 0, sound.size, AudioTrack.WRITE_BLOCKING) }
            } catch (e: Exception) {
                return out.put("problem", "the sweep would not play: ${e.message}")
            }
            microphone.probing = true
            val heard = try {
                record(record, config, SWEEP_S + 0.5) { player.play() }
            } finally {
                microphone.probing = false
                player.release()
            }
            val during = ProbeMath.bands(heard[0], rate)
            val quiet = if (floor != null) DoubleArray(floor.length()) { floor.getDouble(it) } else DoubleArray(during.size) { -160.0 }
            val rise = DoubleArray(min(during.size, quiet.size)) { during[it] - quiet[it] }
            val from = (SWEEP_LOW_HZ / 1000).toInt()
            val top = ProbeMath.top(rise, from)
            out.put("rise_db", JSONArray(rise.map { Math.round(it * 10) / 10.0 }))
            out.put("hears_to_hz", if (top >= 0) (top + 1) * 1000 else JSONObject.NULL)
            out.put("verdict", if (top < 0) "the sweep was not heard over the room, so this says nothing about the path" else "the path carries the sweep up to about ${top + 1} kHz")
        } finally {
            record.release()
        }
        return out
    }

    private fun suggest(probe: JSONObject): JSONObject {
        val configs = probe.optJSONArray("configs") ?: JSONArray()
        var wide: JSONObject? = null
        for (i in 0 until configs.length()) {
            val c = configs.getJSONObject(i)
            val config = c.optJSONObject("config") ?: continue
            if (c.optBoolean("opened") && config.optInt("rate") == 48_000 && !c.optBoolean("cliff_at_8k", true) && config.optString("source") == "voice_recognition") {
                wide = c
                if (config.optString("layout") == "mono") break
            }
        }
        val hears = probe.optJSONObject("sweep")?.opt("hears_to_hz")
        val two = probe.optJSONObject("clicks")?.optBoolean("two_separate_microphones") == true
        val reasons = JSONArray()
        if (wide == null) reasons.put("no 48 kHz voice-recognition feed that keeps the sound above 8 kHz")
        if (hears !is Number || hears.toInt() < 16_000) reasons.put("the sweep did not show the path carrying sound above 15 kHz")
        val ok = reasons.length() == 0
        return JSONObject()
            .put("rate", if (ok) 48_000 else Microphone.RATE)
            .put("channels", if (ok && two) 2 else 1)
            .put("speech_channel", 0)
            .put("high_band_top_hz", if (ok) hears else JSONObject.NULL)
            .put("why_not", reasons)
            .put("note", "a suggestion only; switch it on with mic_rate after checking that speech, the alarm tests and the echo canceller are no worse")
    }

    companion object {
        const val TAG = "PebbleMicProbe"
        const val SECONDS = 3.0
        const val SKIP_S = 0.3
        const val COPIED = 0.999
        const val CLICKS = 5
        const val CLICK_GAP_S = 0.4
        const val CLICK_LEAD_S = 0.3
        const val CLICK_LEVEL = 0.25
        const val HEARD_DB = 10.0
        const val SWEEP_S = 4.0
        const val SWEEP_LOW_HZ = 10_000.0
        const val SWEEP_HIGH_HZ = 22_000.0
        const val SWEEP_LEVEL = 0.05
        val RATES = listOf(16_000, 48_000, 96_000)
        val LAYOUTS = listOf("mono", "stereo", "index2", "index3")
        val SOURCES = listOf(
            MediaRecorder.AudioSource.UNPROCESSED to "unprocessed",
            MediaRecorder.AudioSource.VOICE_RECOGNITION to "voice_recognition",
            MediaRecorder.AudioSource.MIC to "mic",
            MediaRecorder.AudioSource.CAMCORDER to "camcorder",
            MediaRecorder.AudioSource.VOICE_COMMUNICATION to "voice_communication",
        )
    }
}
