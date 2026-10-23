package nz.pebble.robot.brain

import android.content.Context
import android.os.Process
import android.util.Log
import com.k2fsa.sherpa.onnx.EndpointConfig
import com.k2fsa.sherpa.onnx.EndpointRule
import com.k2fsa.sherpa.onnx.FeatureConfig
import com.k2fsa.sherpa.onnx.KeywordSpotter
import com.k2fsa.sherpa.onnx.KeywordSpotterConfig
import com.k2fsa.sherpa.onnx.OnlineModelConfig
import com.k2fsa.sherpa.onnx.OnlineNeMoCtcModelConfig
import com.k2fsa.sherpa.onnx.OnlineParaformerModelConfig
import com.k2fsa.sherpa.onnx.OnlineRecognizer
import com.k2fsa.sherpa.onnx.OnlineRecognizerConfig
import com.k2fsa.sherpa.onnx.OnlineStream
import com.k2fsa.sherpa.onnx.OnlineToneCtcModelConfig
import com.k2fsa.sherpa.onnx.OnlineTransducerModelConfig
import com.k2fsa.sherpa.onnx.OnlineZipformer2CtcModelConfig
import com.k2fsa.sherpa.onnx.QnnConfig
import com.k2fsa.sherpa.onnx.SileroVadModelConfig
import com.k2fsa.sherpa.onnx.SpeakerEmbeddingExtractor
import com.k2fsa.sherpa.onnx.SpeakerEmbeddingExtractorConfig
import com.k2fsa.sherpa.onnx.TenVadModelConfig
import com.k2fsa.sherpa.onnx.Vad
import com.k2fsa.sherpa.onnx.VadModelConfig
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.util.concurrent.ArrayBlockingQueue
import java.util.concurrent.TimeUnit
import kotlin.math.abs
import kotlin.math.log10
import kotlin.math.max
import kotlin.math.pow
import kotlin.math.sqrt

class SpeechModels(private val context: Context) {
    private val folder = File(context.noBackupFilesDir, "speech")
    private val loading = File(folder, "loading")
    private val crashed = File(folder, "crashed")
    private val choice = File(context.noBackupFilesDir, CHOICE)

    private fun phoneKey(): String = "${build()}/${android.os.Build.MODEL}"

    fun probes(): Int? = try {
        if (choice.exists()) org.json.JSONObject(choice.readText()).takeIf { it.optString("key") == phoneKey() && it.has("probes") }?.optInt("probes") else null
    } catch (e: Exception) {
        null
    }

    fun keepProbes(count: Int, why: String) {
        try {
            nz.pebble.robot.Atomic.write(choice, org.json.JSONObject().put("key", phoneKey()).put("probes", count).put("why", why).put("at", System.currentTimeMillis()).toString().toByteArray())
        } catch (e: Exception) {
            Log.w(SherpaEars.TAG, "could not keep the name probes' count", e)
        }
    }

    fun path(name: String): String {
        val target = File(folder, name)
        target.parentFile?.mkdirs()
        val size = try {
            context.assets.openFd("speech/$name").use { it.length }
        } catch (e: Exception) {
            -1L
        }
        val stale = when {
            !target.exists() -> true
            size >= 0 -> target.length() != size
            else -> !context.assets.open("speech/$name").use { it.readBytes() }.contentEquals(target.readBytes())
        }
        if (stale) {
            val part = File(target.path + ".part")
            context.assets.open("speech/$name").use { input -> part.outputStream().use { input.copyTo(it) } }
            target.delete()
            part.renameTo(target)
        }
        return target.path
    }

    fun prune(keep: Set<String>) {
        val wanted = keep.map { File(folder, it).canonicalPath }.toSet() + setOf(loading.canonicalPath, crashed.canonicalPath, File(folder, "keywords.txt").canonicalPath)
        folder.walkBottomUp().forEach { f ->
            if (f == folder) return@forEach
            if (f.isFile && f.canonicalPath !in wanted) f.delete()
            if (f.isDirectory && f.list().isNullOrEmpty()) f.delete()
        }
    }

    private fun build(): String = try {
        val info = context.packageManager.getPackageInfo(context.packageName, 0)
        "${info.lastUpdateTime}"
    } catch (e: Exception) {
        "unknown"
    }

    private fun strikes(): Pair<Int, Long> {
        if (!crashed.exists()) return 0 to 0L
        val parts = try {
            crashed.readText().trim().split(" ")
        } catch (e: Exception) {
            return 0 to 0L
        }
        if (parts.getOrNull(0) != build()) {
            crashed.delete()
            return 0 to 0L
        }
        return (parts.getOrNull(1)?.toIntOrNull() ?: 0) to (parts.getOrNull(2)?.toLongOrNull() ?: 0L)
    }

    fun noteCrashes() {
        folder.mkdirs()
        if (!loading.exists()) return
        val strikes = strikes().first + 1
        crashed.writeText("${build()} $strikes ${System.currentTimeMillis()}")
        loading.delete()
    }

    fun restingUntil(): Long {
        val (strikes, at) = strikes()
        if (strikes < STRIKES) return 0L
        val until = at + Rest.ms(strikes)
        return if (System.currentTimeMillis() < until) until else 0L
    }

    fun loadingStarts() {
        folder.mkdirs()
        loading.writeText(build())
    }

    fun loadingEnded(ok: Boolean) {
        loading.delete()
        if (ok) crashed.delete()
    }

    companion object {
        const val STRIKES = Rest.STRIKES
        const val CHOICE = "ears-choice.json"

        fun forgetMeasurements(context: Context) {
            File(context.noBackupFilesDir, CHOICE).delete()
            File(File(context.noBackupFilesDir, "speech"), "crashed").delete()
        }
    }

    fun keywordsFile(lines: List<String>): String {
        folder.mkdirs()
        val file = File(folder, "keywords.txt")
        file.writeText(lines.joinToString("\n", postfix = "\n") { it.trim() })
        return file.path
    }

    fun manifest(): JSONObject? = try {
        JSONObject(context.assets.open("speech/speech.json").bufferedReader().readText())
    } catch (e: Exception) {
        null
    }
}

object Rest {
    const val STRIKES = 2
    const val FIRST_MS = 60 * 60_000L
    const val LONGEST_MS = 24 * 60 * 60_000L

    fun ms(strikes: Int): Long = if (strikes < STRIKES) 0L else minOf(LONGEST_MS, FIRST_MS shl minOf(5, strikes - STRIKES))
}

data class KeywordSpec(val word: String, val tokens: String, val boost: Float = 1.5f, val threshold: Float = 0.25f)

data class HearingSettings(
    val mode: String = MODE_WORDS,
    val keywords: List<KeywordSpec> = emptyList(),
    val vadThreshold: Float = 0.5f,
    val minSilenceS: Float = 0.25f,
    val minSpeechS: Float = 0.1f,
    val maxSpeechS: Float = 20f,
    val preRollS: Float = 0.4f,
    val printMinS: Float = 1.0f,
    val printAfterFinal: Boolean = false,
    val threads: Int = 2,
    val normalise: Boolean = true,
    val targetDbfs: Float = -23f,
    val maxGain: Float = 30f,
    val kwsFlushS: Float = 0.64f,
    val kwsFlushAfterS: Float = 0.09f,
    val asrTailS: Float = 0f,
    val kwsProbes: Int = 2,
    val turnModel: Boolean = false,
    val kwsGain: Boolean = false,
) {
    fun needsReload(other: HearingSettings): Boolean =
        mode != other.mode || keywords != other.keywords || vadThreshold != other.vadThreshold || minSilenceS != other.minSilenceS ||
            minSpeechS != other.minSpeechS || maxSpeechS != other.maxSpeechS || threads != other.threads || kwsProbes != other.kwsProbes

    fun probeLags(): IntArray = lags(kwsProbes)

    companion object {
        const val MODE_WORDS = "words"
        const val MODE_KEYWORDS = "keywords"
        const val MODE_OFF = "off"
        const val PROBE_GRID = 5_120

        fun lags(count: Int): IntArray = IntArray(count.coerceAtLeast(0)) { it * PROBE_GRID / count }

        fun parse(text: String, base: HearingSettings = HearingSettings()): HearingSettings {
            val o = JSONObject(text)
            val words = o.optJSONArray("keywords")?.let { a ->
                (0 until a.length()).mapNotNull { i ->
                    val k = a.optJSONObject(i) ?: return@mapNotNull null
                    val word = k.optString("word").trim()
                    val tokens = k.optString("tokens").trim()
                    if (word.isEmpty() || tokens.isEmpty()) null else KeywordSpec(word, tokens, k.optDouble("boost", 1.5).toFloat(), k.optDouble("threshold", 0.25).toFloat())
                }
            } ?: base.keywords
            val mode = o.optString("mode", base.mode).takeIf { it in listOf(MODE_WORDS, MODE_KEYWORDS, MODE_OFF) } ?: base.mode
            return HearingSettings(
                mode = mode,
                keywords = words,
                vadThreshold = o.optDouble("vad_threshold", base.vadThreshold.toDouble()).toFloat().coerceIn(0.05f, 0.95f),
                minSilenceS = o.optDouble("min_silence_s", base.minSilenceS.toDouble()).toFloat().coerceIn(0.05f, 3f),
                minSpeechS = o.optDouble("min_speech_s", base.minSpeechS.toDouble()).toFloat().coerceIn(0.03f, 1f),
                maxSpeechS = o.optDouble("max_speech_s", base.maxSpeechS.toDouble()).toFloat().coerceIn(2f, 60f),
                preRollS = o.optDouble("pre_roll_s", base.preRollS.toDouble()).toFloat().coerceIn(0f, 2f),
                printMinS = o.optDouble("print_min_s", base.printMinS.toDouble()).toFloat().coerceIn(0.3f, 10f),
                printAfterFinal = o.optBoolean("print_after_final", base.printAfterFinal),
                threads = o.optInt("threads", base.threads).coerceIn(1, 4),
                normalise = o.optBoolean("normalise", base.normalise),
                targetDbfs = o.optDouble("target_dbfs", base.targetDbfs.toDouble()).toFloat().coerceIn(-50f, -3f),
                maxGain = o.optDouble("max_gain", base.maxGain.toDouble()).toFloat().coerceIn(1f, 100f),
                kwsFlushS = o.optDouble("kws_flush_s", base.kwsFlushS.toDouble()).toFloat().coerceIn(0f, 2f),
                kwsFlushAfterS = o.optDouble("kws_flush_after_s", base.kwsFlushAfterS.toDouble()).toFloat().coerceIn(0f, 1f),
                asrTailS = o.optDouble("asr_tail_s", base.asrTailS.toDouble()).toFloat().coerceIn(0f, 3f),
                kwsProbes = o.optInt("kws_probes", base.kwsProbes).coerceIn(0, 4),
                turnModel = o.optBoolean("turn_model", base.turnModel),
                kwsGain = o.optBoolean("kws_gain", base.kwsGain),
            )
        }
    }
}

class SpotLevel(private val slowest: Double = SLOW) {
    private var power = 0.0
    private var windows = 0L

    fun heard(window: FloatArray) {
        var e = 0.0
        for (x in window) e += x.toDouble() * x
        val p = e / window.size
        windows++
        val rate = maxOf(1.0 / windows, slowest)
        power += rate * (p - power)
    }

    fun gain(targetDbfs: Float, maxGain: Float): Float = if (windows == 0L) 1f else Gain.of(power, 1, targetDbfs, maxGain)

    companion object {
        const val SLOW = 0.0064
    }
}

object Gain {
    const val MIN = 0.25f

    fun of(energy: Double, samples: Long, targetDbfs: Float, maxGain: Float): Float {
        if (samples <= 0 || energy <= 0.0) return maxGain
        val rms = sqrt(energy / samples)
        val target = 10.0.pow(targetDbfs / 20.0)
        return (target / rms).toFloat().coerceIn(MIN, maxGain)
    }
}

object Keywords {
    fun line(keywords: List<KeywordSpec>): String = keywords
        .filter { it.tokens.isNotBlank() && it.word.isNotBlank() }
        .joinToString("/") { "${it.tokens.trim()} :${it.boost} #${it.threshold} @${it.word.trim().replace(' ', '_')}" }
}

class Segmenter(
    private val threshold: Float,
    private val minSpeechS: Float,
    private val minSilenceS: Float,
    private val maxSpeechS: Float,
    private val window: Int = 512,
    private val rate: Int = 16_000,
) {
    sealed class Step {
        object Quiet : Step()
        data class Start(val firstSpeechWindow: Long) : Step()
        object Speech : Step()
        data class Pause(val silenceWindow: Long) : Step()
        object Resume : Step()
        data class End(val silenceWindow: Long) : Step()
    }

    private var speechRun = 0
    private var silenceRun = 0
    private var inSpeech = false
    private var windows = 0L
    private var firstSpeech = 0L
    private var silenceStart = 0L
    private var segmentWindows = 0
    private val windowS = window.toDouble() / rate
    val low = max(0.01f, threshold - 0.15f)

    val speaking: Boolean get() = inSpeech

    fun reset() {
        speechRun = 0
        silenceRun = 0
        inSpeech = false
        segmentWindows = 0
    }

    fun step(probability: Float): Step {
        val index = windows++
        if (!inSpeech) {
            if (probability >= threshold) {
                if (speechRun == 0) firstSpeech = index
                speechRun++
                if (speechRun * windowS >= minSpeechS) {
                    inSpeech = true
                    silenceRun = 0
                    segmentWindows = speechRun
                    speechRun = 0
                    return Step.Start(firstSpeech)
                }
            } else {
                speechRun = 0
            }
            return Step.Quiet
        }
        segmentWindows++
        if (probability < low) {
            if (silenceRun == 0) silenceStart = index
            silenceRun++
            if (silenceRun * windowS >= minSilenceS) {
                inSpeech = false
                silenceRun = 0
                return Step.End(silenceStart)
            }
            return if (silenceRun == 1) Step.Pause(silenceStart) else Step.Speech
        }
        val resumed = silenceRun > 0
        silenceRun = 0
        if (segmentWindows * windowS >= maxSpeechS) {
            inSpeech = false
            return Step.End(index)
        }
        return if (resumed) Step.Resume else Step.Speech
    }
}

class SherpaEars(private val models: SpeechModels, private val turn: TurnModel? = null, private val emit: (JSONObject) -> Unit) : AudioSink {
    private class Chunk(val samples: FloatArray, val at: Double, val speaking: Boolean)

    private val queue = ArrayBlockingQueue<Chunk>(QUEUE)
    @Volatile private var settings = HearingSettings()
    @Volatile private var wanted = false
    @Volatile private var thread: Thread? = null
    @Volatile private var reload = true
    @Volatile private var inLoad = false
    @Volatile private var lastWorkAt = System.nanoTime()
    @Volatile var problem = ""
    @Volatile var ready = false
    @Volatile var dropped = 0
    @Volatile var segments = 0
    @Volatile var lastFinalMs = 0.0
    @Volatile var loadMs = 0.0
    @Volatile var loaded = ""
    @Volatile var onChange: (() -> Unit)? = null
    private var recognizer: OnlineRecognizer? = null
    private var vad: Vad? = null
    private var spotter: KeywordSpotter? = null
    private var printer: SpeakerEmbeddingExtractor? = null
    private var asr: OnlineStream? = null
    private var kws: OnlineStream? = null
    private val probes = ArrayList<OnlineStream>()
    private val turnRing = FloatArray(TurnFeatures.SAMPLES)
    private val turnWorker = java.util.concurrent.ThreadPoolExecutor(1, 1, 0L, TimeUnit.MILLISECONDS, java.util.concurrent.LinkedBlockingQueue<Runnable>(), java.util.concurrent.ThreadFactory { r -> Thread(r, "pebble-turn").also { it.isDaemon = true } })
    private var turnAt = 0
    private var turnFilled = 0
    private var probeLags = IntArray(0)
    private var workNs = 0L
    private var workSamples = 0L
    @Volatile var lastLoad = 0.0
    private var kwsFed = 0L
    private var lastWord = ""
    private var lastWordAt = Long.MIN_VALUE / 2
    private var segmenter = Segmenter(0.5f, 0.1f, 0.25f, 20f)
    private val pending = FloatArray(WINDOW)
    private var pendingCount = 0
    private var samplesSeen = 0L
    private var windowBase = 0L
    private var lastChunkAt = 0.0
    private var lastChunkEnd = 0L
    private val history = ArrayDeque<FloatArray>()
    private var historySamples = 0
    private var historyStart = 0L
    private val segment = ArrayList<FloatArray>()
    private var segmentSamples = 0
    private var segmentNo = 0
    private var segmentStart = 0.0
    private var segmentSpeaking = false
    private var segmentKeyword = false
    private var lastPartial = ""
    private var voicedDb = 0.0
    private var voicedFrames = 0
    private var peak = 0f
    private var frameSum = 0.0
    private var frameCount = 0
    private var frameVoiced = false
    private var speechEnergy = 0.0
    private var speechCount = 0L
    private var gain = 1f
    private val spotLevel = SpotLevel()
    @Volatile private var spotGain = 1f
    private var tail = (TAIL_S * RATE).toInt()
    private var pausedAt: Double? = null
    private var quietSamples = 0
    @Volatile var flushes = 0
    @Volatile var flushFinds = 0

    val mode: String get() = if (wanted) settings.mode else HearingSettings.MODE_OFF

    init {
        models.noteCrashes()
    }

    fun available(): Boolean = models.manifest() != null && models.restingUntil() == 0L

    fun unavailableBecause(): String = when {
        models.manifest() == null -> "this build has no speech models"
        models.restingUntil() > 0L -> "the speech models stopped their process twice while loading, so Pebble listens with Android's own recognizer until ${java.text.SimpleDateFormat("HH:mm", java.util.Locale.ROOT).format(java.util.Date(models.restingUntil()))} and then tries them again"
        else -> ""
    }

    fun configure(text: String) {
        val next = HearingSettings.parse(text, settings)
        if (next != settings) {
            val heavy = next.needsReload(settings)
            settings = next
            if (heavy) reload = true
        }
    }

    fun start() {
        if (!available()) {
            problem = unavailableBecause()
            return
        }
        wanted = true
        if (thread == null) thread = Thread({ run() }, "pebble-hear").also { it.start() }
    }

    fun stop() {
        wanted = false
        queue.clear()
        turnFilled = 0
    }

    override fun onAudio(pcm: ShortArray, count: Int, speaking: Boolean) = hear(pcm, count, speaking, System.nanoTime() / 1e9)

    fun hear(pcm: ShortArray, count: Int, speaking: Boolean, at: Double) {
        if (!wanted || settings.mode == HearingSettings.MODE_OFF || !(ready || reload || inLoad)) return
        val samples = FloatArray(count) { pcm[it] / 32768f }
        if (!queue.offer(Chunk(samples, at, speaking))) dropped++
    }

    private fun run() {
        Process.setThreadPriority(Process.THREAD_PRIORITY_URGENT_AUDIO)
        try {
            while (true) {
                if (!wanted) {
                    if (queue.poll(1, TimeUnit.SECONDS) == null && !wanted) {
                        closeOpenSegment()
                        release()
                        reload = true
                        synchronized(this) { thread = null }
                        return
                    }
                    continue
                }
                if (reload) load()
                val chunk = queue.poll(500, TimeUnit.MILLISECONDS)
                if (chunk == null) {
                    lastWorkAt = System.nanoTime()
                    continue
                }
                val began = System.nanoTime()
                if (ready) {
                    hearInSteps(chunk)
                    measure(System.nanoTime() - began, chunk.samples.size)
                }
                lastWorkAt = System.nanoTime()
            }
        } catch (e: Throwable) {
            problem = "listening stopped: ${e.message}"
            Log.e(TAG, problem, e)
            release()
            synchronized(this) { thread = null }
            onChange?.invoke()
        }
    }

    private fun model(part: JSONObject, threads: Int): OnlineModelConfig = OnlineModelConfig(
        OnlineTransducerModelConfig(models.path(part.getString("encoder")), models.path(part.getString("decoder")), models.path(part.getString("joiner")), QnnConfig()),
        OnlineParaformerModelConfig(),
        OnlineZipformer2CtcModelConfig(),
        OnlineNeMoCtcModelConfig(),
        OnlineToneCtcModelConfig(),
        models.path(part.getString("tokens")),
        threads,
        false,
        "cpu",
        part.optString("model_type", ""),
        part.optString("modeling_unit", ""),
        part.optString("bpe_vocab", "").let { if (it.isEmpty()) "" else models.path(it) },
    )

    private fun load() {
        inLoad = true
        try {
            reload = false
            loadModels()
        } finally {
            inLoad = false
            lastWorkAt = System.nanoTime()
        }
    }

    private fun loadModels() {
        val manifest = models.manifest()
        if (manifest == null) {
            problem = "this build has no speech models"
            ready = false
            return
        }
        closeOpenSegment()
        release()
        val s = settings
        segmenter = Segmenter(s.vadThreshold, s.minSpeechS, s.minSilenceS, s.maxSpeechS)
        windowBase = samplesSeen
        if (s.mode == HearingSettings.MODE_OFF) {
            ready = false
            loaded = HearingSettings.MODE_OFF
            return
        }
        val started = System.nanoTime()
        val parts = ArrayList<String>()
        models.loadingStarts()
        try {
            val feature = FeatureConfig(RATE, 80, 0f)
            vad = Vad(null, VadModelConfig(SileroVadModelConfig(models.path(manifest.getString("vad")), s.vadThreshold, s.minSilenceS, s.minSpeechS, WINDOW, s.maxSpeechS), TenVadModelConfig(), RATE, 1, "cpu", false))
            parts += "vad"
            if (s.mode == HearingSettings.MODE_WORDS) {
                val config = OnlineRecognizerConfig()
                config.featConfig = feature
                val asrPart = manifest.getJSONObject("asr")
                config.modelConfig = model(asrPart, s.threads)
                tail = (asrPart.optDouble("tail_s", max(TAIL_S, 2 * asrPart.optDouble("chunk_s", 0.0))) * RATE).toInt().coerceIn(RATE / 10, RATE * 3)
                config.endpointConfig = EndpointConfig(EndpointRule(false, 2.4f, 0f), EndpointRule(true, 1.2f, 0f), EndpointRule(false, 0f, 20f))
                config.enableEndpoint = false
                config.decodingMethod = "greedy_search"
                recognizer = OnlineRecognizer(null, config)
                parts += "asr"
                manifest.optString("speaker", "").takeIf { it.isNotEmpty() }?.let {
                    printer = SpeakerEmbeddingExtractor(null, SpeakerEmbeddingExtractorConfig(models.path(it), 1, false, "cpu"))
                    parts += "prints"
                }
            }
            val kwsPart = manifest.optJSONObject("kws")
            val line = Keywords.line(s.keywords)
            if (kwsPart != null && line.isNotEmpty()) {
                val config = KeywordSpotterConfig()
                config.featConfig = feature
                config.modelConfig = model(kwsPart, 1)
                config.keywordsFile = models.keywordsFile(line.split("/"))
                config.numTrailingBlanks = kwsPart.optInt("num_trailing_blanks", 1)
                spotter = KeywordSpotter(null, config)
                kws = spotter!!.createStream("")
                kwsFed = 0L
                probeLags = HearingSettings.lags(minOf(s.kwsProbes, models.probes() ?: s.kwsProbes))
                for (lag in probeLags) probes += renewProbe(spotter!!, lag)
                lastWord = ""
                lastWordAt = Long.MIN_VALUE / 2
                parts += "keywords"
            }
            ready = s.mode == HearingSettings.MODE_WORDS || spotter != null
            problem = if (ready) "" else "no keywords to listen for"
        } catch (e: Throwable) {
            problem = "the speech models would not load: ${e.message}"
            Log.e(TAG, problem, e)
            release()
            ready = false
        } finally {
            models.loadingEnded(ready)
        }
        loaded = parts.joinToString("+")
        if (ready) models.prune(needed(manifest))
        loadMs = (System.nanoTime() - started) / 1e6
        Log.i(TAG, "speech ready in ${loadMs.toInt()} ms: mode ${s.mode}, $loaded ${problem}")
        onChange?.invoke()
    }

    private fun closeOpenSegment() {
        if (vad == null || !segmenter.speaking) return
        segmenter.reset()
        emit(JSONObject().put("kind", "voice_end").put("t", System.nanoTime() / 1e9).put("segment", segmentNo).put("end", lastChunkAt).put("pebble_speaking", segmentSpeaking).put("lost", true))
    }

    private fun needed(manifest: JSONObject): Set<String> {
        val out = HashSet<String>()
        manifest.optString("vad", "").takeIf { it.isNotEmpty() }?.let { out += it }
        manifest.optString("speaker", "").takeIf { it.isNotEmpty() }?.let { out += it }
        for (part in listOf("asr", "kws")) {
            val o = manifest.optJSONObject(part) ?: continue
            for (key in listOf("encoder", "decoder", "joiner", "tokens", "bpe_vocab")) o.optString(key, "").takeIf { it.isNotEmpty() }?.let { out += it }
        }
        return out
    }

    private fun release() {
        asr?.release()
        kws?.release()
        for (p in probes) p.release()
        probes.clear()
        recognizer?.release()
        spotter?.release()
        vad?.release()
        printer?.release()
        asr = null
        kws = null
        recognizer = null
        spotter = null
        vad = null
        printer = null
        ready = false
        segment.clear()
        segmentSamples = 0
        history.clear()
        historySamples = 0
        pendingCount = 0
    }

    private fun measure(ns: Long, samples: Int) {
        workNs += ns
        workSamples += samples
        if (workSamples < LOAD_WINDOW_S * RATE) return
        val load = workNs / 1e9 / (workSamples.toDouble() / RATE)
        lastLoad = load
        workNs = 0L
        workSamples = 0L
        if (load <= LOAD_HIGH || probes.isEmpty()) return
        probes.removeAt(probes.lastIndex).release()
        probeLags = probeLags.copyOf(probes.size)
        val why = "hearing took ${Math.round(load * 100)} % of the sound's own time"
        models.keepProbes(probes.size, why)
        Log.w(TAG, "$why; the name spotter now uses ${probes.size} probes")
    }

    private fun hearInSteps(chunk: Chunk) {
        val n = chunk.samples.size
        if (n <= STEP) {
            hear(chunk)
            return
        }
        var offset = 0
        while (offset < n) {
            val end = minOf(n, offset + STEP)
            hear(Chunk(chunk.samples.copyOfRange(offset, end), chunk.at - (n - end).toDouble() / RATE, chunk.speaking))
            offset = end
        }
    }

    private fun timeOf(sample: Long): Double = lastChunkAt - (lastChunkEnd - sample).toDouble() / RATE

    private fun turnOn(): Boolean = turn != null && settings.turnModel && settings.mode == HearingSettings.MODE_WORDS

    private fun keepForTurn(samples: FloatArray) {
        if (!turnOn()) {
            turnFilled = 0
            return
        }
        for (x in samples) {
            turnRing[turnAt] = x
            turnAt = (turnAt + 1) % turnRing.size
        }
        turnFilled = minOf(turnRing.size, turnFilled + samples.size)
    }

    private fun askTurn(after: String, segment: Int) {
        val model = turn
        if (model == null || !turnOn() || turnFilled < TURN_LEAST) return
        val audio = FloatArray(turnFilled)
        val start = (turnAt - turnFilled + turnRing.size) % turnRing.size
        val first = minOf(turnFilled, turnRing.size - start)
        System.arraycopy(turnRing, start, audio, 0, first)
        if (first < turnFilled) System.arraycopy(turnRing, 0, audio, first, turnFilled - first)
        TurnJob.prune(turnWorker.queue, after, segment)
        turnWorker.execute(TurnJob(after, segment) {
            val chance = model.chance(audio) ?: return@TurnJob
            emit(JSONObject()
                .put("kind", "turn_end")
                .put("t", System.nanoTime() / 1e9)
                .put("segment", segment)
                .put("after", after)
                .put("turn_end", Math.round(chance * 1000) / 1000.0)
                .put("turn_end_ms", Math.round(model.lastMs * 10) / 10.0))
        })
    }

    private fun hear(chunk: Chunk) {
        samplesSeen += chunk.samples.size
        keepForTurn(chunk.samples)
        lastChunkAt = chunk.at
        lastChunkEnd = samplesSeen
        spot(chunk)
        val v = vad ?: return
        remember(chunk.samples)
        if (segmenter.speaking) take(chunk)
        var offset = 0
        while (offset < chunk.samples.size) {
            val n = minOf(WINDOW - pendingCount, chunk.samples.size - offset)
            System.arraycopy(chunk.samples, offset, pending, pendingCount, n)
            pendingCount += n
            offset += n
            if (pendingCount == WINDOW) {
                pendingCount = 0
                val probability = v.compute(pending.copyOf())
                frame(probability)
                val step = segmenter.step(probability)
                when (step) {
                    is Segmenter.Step.Start -> begin(chunk, windowBase + step.firstSpeechWindow * WINDOW)
                    is Segmenter.Step.Pause -> {
                        val at = timeOf(windowBase + step.silenceWindow * WINDOW)
                        emit(JSONObject().put("kind", "pause").put("t", at).put("segment", segmentNo).put("pebble_speaking", chunk.speaking))
                        askTurn("pause", segmentNo)
                        pausedAt = at
                        quietSamples = 0
                    }
                    is Segmenter.Step.End -> finish(chunk, timeOf(windowBase + step.silenceWindow * WINDOW))
                    else -> Unit
                }
                val paused = pausedAt
                if (paused != null) {
                    if (probability >= segmenter.low && step !is Segmenter.Step.Pause) {
                        pausedAt = null
                    } else {
                        quietSamples += WINDOW
                        if (quietSamples >= settings.kwsFlushAfterS * RATE) {
                            pausedAt = null
                            flush(chunk, paused)
                        }
                    }
                }
                if (probability >= settings.vadThreshold) {
                    spotLevel.heard(pending)
                    spotGain = if (settings.kwsGain) spotLevel.gain(settings.targetDbfs, settings.maxGain) else 1f
                }
                if (segmenter.speaking && step !is Segmenter.Step.Start && probability >= settings.vadThreshold) {
                    var e = 0.0
                    for (x in pending) e += x.toDouble() * x
                    speechEnergy += e
                    speechCount += WINDOW
                    gain = level()
                }
            }
        }
    }

    private fun frame(probability: Float) {
        if (probability >= settings.vadThreshold) frameVoiced = true
    }

    private fun remember(samples: FloatArray) {
        history.addLast(samples)
        historySamples += samples.size
        val keep = maxOf((settings.preRollS * RATE).toInt() + WINDOW * 8 + RATE / 2, ALIGN * 2 + WINDOW)
        while (history.size > 1 && historySamples - history.first().size >= keep) {
            historySamples -= history.removeFirst().size
        }
        historyStart = samplesSeen - historySamples
    }

    private fun level(): Float = if (settings.normalise) Gain.of(speechEnergy, speechCount, settings.targetDbfs, settings.maxGain) else 1f

    private fun flush(chunk: Chunk, pausedAt: Double) {
        val n = (settings.kwsFlushS * RATE).toInt()
        val s = spotter ?: return
        if (kws == null || probes.isEmpty() || n <= 0) return
        flushes++
        var hit = false
        for (i in probes.indices) {
            val p = probes[i]
            p.acceptWaveform(FloatArray(n), RATE)
            if (found(s, p, chunk, pausedAt)) hit = true
            p.release()
            probes[i] = renewProbe(s, probeLags[i])
        }
        if (hit) flushFinds++
    }

    private fun renewProbe(s: KeywordSpotter, lag: Int): OnlineStream {
        val fresh = s.createStream("")
        var want = ((kwsFed + lag) % ALIGN).toInt()
        while (want + ALIGN <= historySamples) want += ALIGN
        if (want > 0) {
            fresh.acceptWaveform(louder(recent(want)), RATE)
            while (s.isReady(fresh)) {
                s.decode(fresh)
                if (s.getResult(fresh).keyword.isNotEmpty()) s.reset(fresh)
            }
            s.reset(fresh)
        }
        return fresh
    }

    private fun recent(n: Int): FloatArray {
        val out = FloatArray(n)
        var at = n
        for (part in history.reversed()) {
            if (at == 0) break
            val take = minOf(at, part.size)
            System.arraycopy(part, part.size - take, out, at - take, take)
            at -= take
        }
        return out
    }

    private fun louder(samples: FloatArray): FloatArray {
        val g = if (settings.kwsGain) spotGain else 1f
        return if (g == 1f) samples else FloatArray(samples.size) { (samples[it] * g).coerceIn(-1f, 1f) }
    }

    private fun spot(chunk: Chunk): Boolean {
        val s = spotter ?: return false
        val main = kws ?: return false
        val samples = louder(chunk.samples)
        main.acceptWaveform(samples, RATE)
        kwsFed += chunk.samples.size
        var any = found(s, main, chunk, null)
        for (p in probes) {
            p.acceptWaveform(samples, RATE)
            if (found(s, p, chunk, null)) any = true
        }
        return any
    }

    private fun found(s: KeywordSpotter, stream: OnlineStream, chunk: Chunk, flushedEnd: Double?): Boolean {
        var found = false
        while (s.isReady(stream)) {
            s.decode(stream)
            val result = s.getResult(stream)
            val word = result.keyword
            if (word.isNotEmpty()) {
                s.reset(stream)
                if (word == lastWord && kwsFed - lastWordAt < SAME_WORD_S * RATE) continue
                lastWord = word
                lastWordAt = kwsFed
                found = true
                if (segmenter.speaking) segmentKeyword = true
                val t = if (flushedEnd != null) System.nanoTime() / 1e9 else chunk.at
                val event = JSONObject().put("kind", "keyword").put("t", t).put("segment", if (segmenter.speaking) segmentNo else segmentNo + 1).put("word", word.replace('_', ' ')).put("pebble_speaking", chunk.speaking).put("flushed", flushedEnd != null)
                val stamps = result.timestamps
                if (stamps.isNotEmpty()) {
                    val end = flushedEnd ?: (chunk.at - KWS_TRAIL_S)
                    event.put("start", end - (stamps.last() - stamps.first()) - FRAME_S).put("end", end)
                }
                emit(event)
            }
        }
        return found
    }

    private fun begin(chunk: Chunk, firstSample: Long) {
        val r = recognizer
        segmentNo++
        segments++
        segmentSpeaking = chunk.speaking
        segmentKeyword = false
        lastPartial = ""
        voicedDb = 0.0
        voicedFrames = 0
        peak = 0f
        frameSum = 0.0
        frameCount = 0
        val lead = (settings.preRollS * RATE).toLong()
        val from = max(historyStart, firstSample - lead)
        segmentStart = timeOf(firstSample)
        speechEnergy = 0.0
        speechCount = 0L
        var spot = historyStart
        for (part in history) {
            for (i in part.indices) {
                if (spot + i >= firstSample) {
                    speechEnergy += part[i].toDouble() * part[i]
                    speechCount++
                }
            }
            spot += part.size
        }
        gain = level()
        emit(JSONObject().put("kind", "voice_start").put("t", chunk.at).put("segment", segmentNo).put("start", segmentStart).put("pebble_speaking", chunk.speaking))
        asr?.release()
        asr = r?.createStream("")
        segment.clear()
        segmentSamples = 0
        var position = historyStart
        for (part in history) {
            val partEnd = position + part.size
            if (partEnd > from) {
                val skip = max(0L, from - position).toInt()
                val piece = if (skip == 0) part else part.copyOfRange(skip, part.size)
                feed(piece, chunk.speaking)
            }
            position = partEnd
        }
    }

    private fun take(chunk: Chunk) {
        feed(chunk.samples, chunk.speaking)
        if (chunk.speaking) segmentSpeaking = true
        val r = recognizer ?: return
        val stream = asr ?: return
        while (r.isReady(stream)) r.decode(stream)
        val text = r.getResult(stream).text.trim()
        if (text.isNotEmpty() && text != lastPartial) {
            lastPartial = text
            emit(JSONObject().put("kind", "partial").put("t", chunk.at).put("segment", segmentNo).put("text", text).put("pebble_speaking", chunk.speaking))
        }
    }

    private fun feed(samples: FloatArray, speaking: Boolean) {
        segment += samples
        segmentSamples += samples.size
        val g = gain
        asr?.acceptWaveform(if (g == 1f) samples else FloatArray(samples.size) { samples[it] * g }, RATE)
        for (x in samples) {
            val a = abs(x)
            if (a > peak) peak = a
            frameSum += x.toDouble() * x
            frameCount++
            if (frameCount == FRAME) {
                if (frameVoiced) {
                    val rms = sqrt(frameSum / FRAME)
                    voicedDb += if (rms > 0) 20 * log10(rms) else -120.0
                    voicedFrames++
                }
                frameSum = 0.0
                frameCount = 0
                frameVoiced = false
            }
        }
    }

    private fun finish(chunk: Chunk, end: Double) {
        val started = System.nanoTime()
        emit(JSONObject().put("kind", "voice_end").put("t", chunk.at).put("segment", segmentNo).put("end", end).put("pebble_speaking", segmentSpeaking))
        askTurn("voice_end", segmentNo)
        val r = recognizer
        val stream = asr
        var text = ""
        if (r != null && stream != null) {
            stream.acceptWaveform(FloatArray(if (settings.asrTailS > 0f) (settings.asrTailS * RATE).toInt() else tail), RATE)
            stream.inputFinished()
            while (r.isReady(stream)) r.decode(stream)
            text = r.getResult(stream).text.trim()
            stream.release()
            asr = null
        }
        val asrMs = (System.nanoTime() - started) / 1e6
        val audio = FloatArray(segmentSamples)
        var at = 0
        for (part in segment) {
            System.arraycopy(part, 0, audio, at, part.size)
            at += part.size
        }
        segment.clear()
        segmentSamples = 0
        lastFinalMs = (System.nanoTime() - started) / 1e6
        val separate = settings.printAfterFinal
        var printed: FloatArray? = null
        var printMs = 0.0
        val printSeconds = Math.round(audio.size * 100.0 / RATE) / 100.0
        if (!separate) {
            val printStarted = System.nanoTime()
            printed = if (audio.size >= settings.printMinS * RATE) voicePrint(audio) else null
            printMs = (System.nanoTime() - printStarted) / 1e6
            lastFinalMs = (System.nanoTime() - started) / 1e6
        }
        if (text.isNotEmpty()) {
            val level = if (voicedFrames > 0) voicedDb / voicedFrames else -120.0
            val peakDb = if (peak > 0) 20 * log10(peak.toDouble()) else -120.0
            emit(JSONObject()
                .put("kind", "final")
                .put("t", System.nanoTime() / 1e9)
                .put("segment", segmentNo)
                .put("text", text)
                .put("start", segmentStart)
                .put("end", end)
                .put("print", printed?.let { p -> JSONArray(p.map { Math.round(it * 1e5) / 1e5 }) } ?: JSONObject.NULL)
                .put("print_s", if (printed != null) printSeconds else 0.0)
                .put("print_follows", separate && audio.size >= settings.printMinS * RATE && printer != null)
                .put("level_db", Math.round(level * 10) / 10.0)
                .put("peak_db", Math.round(peakDb * 10) / 10.0)
                .put("keyword", segmentKeyword)
                .put("gain", Math.round(gain * 100) / 100.0)
                .put("pebble_speaking", segmentSpeaking)
                .put("decode_ms", Math.round(lastFinalMs * 10) / 10.0)
                .put("asr_ms", Math.round(asrMs * 10) / 10.0)
                .put("print_ms", Math.round(printMs * 10) / 10.0))
        }
        if (separate && audio.size >= settings.printMinS * RATE && printer != null) {
            val printStarted = System.nanoTime()
            val late = voicePrint(audio)
            emit(JSONObject()
                .put("kind", "print")
                .put("t", System.nanoTime() / 1e9)
                .put("segment", segmentNo)
                .put("print", late?.let { p -> JSONArray(p.map { Math.round(it * 1e5) / 1e5 }) } ?: JSONObject.NULL)
                .put("print_s", if (late != null) printSeconds else 0.0)
                .put("print_ms", Math.round((System.nanoTime() - printStarted) / 1e5) / 10.0))
        }
    }

    private fun voicePrint(audio: FloatArray): FloatArray? {
        val p = printer ?: return null
        return try {
            val stream = p.createStream()
            stream.acceptWaveform(audio, RATE)
            stream.inputFinished()
            val out = if (p.isReady(stream)) p.compute(stream) else null
            stream.release()
            out
        } catch (e: Throwable) {
            Log.w(TAG, "no voice print", e)
            null
        }
    }

    fun info(): JSONObject = JSONObject()
        .put("engine", "sherpa-onnx")
        .put("mode", mode)
        .put("loaded", loaded)
        .put("ready", ready)
        .put("keywords", JSONArray(settings.keywords.map { it.word }))
        .put("segments", segments)
        .put("dropped", dropped)
        .put("load_ms", Math.round(loadMs))
        .put("last_final_ms", Math.round(lastFinalMs * 10) / 10.0)
        .put("asr_tail_s", tail.toDouble() / RATE)
        .put("kws_flushes", flushes)
        .put("kws_found_by_flush", flushFinds)
        .put("kws_probes", probes.size)
        .put("kws_gain", if (settings.kwsGain) Math.round(spotGain * 100) / 100.0 else JSONObject.NULL)
        .put("load", Math.round(lastLoad * 1000) / 1000.0)
        .put("turn_model", if (turn == null) "none" else if (!settings.turnModel) (if (turn.present) "off" else "missing") else turn.state)
        .put("turn_last", turn?.lastChance?.takeIf { !it.isNaN() } ?: JSONObject.NULL)
        .put("turn_ms", turn?.let { Math.round(it.lastMs * 10) / 10.0 } ?: JSONObject.NULL)
        .put("turn_runs", turn?.runs ?: 0)
        .put("queued", queue.size)
        .put("stalled_s", stalledS())
        .put("problem", problem)

    private fun stalledS(): Double {
        if (!wanted || inLoad || queue.isEmpty()) return 0.0
        return Math.round((System.nanoTime() - lastWorkAt) / 1e8) / 10.0
    }

    companion object {
        const val TAG = "PebbleHear"
        const val RATE = 16_000
        const val WINDOW = 512
        const val FRAME = 1_600
        const val TAIL_S = 0.3
        const val KWS_TRAIL_S = 0.08
        const val FRAME_S = 0.04
        const val QUEUE = 500
        const val STEP = RATE / 50
        const val ALIGN = 10_240
        const val SAME_WORD_S = 1.5
        const val TURN_LEAST = RATE / 4
        const val LOAD_WINDOW_S = 30
        const val LOAD_HIGH = 0.5
    }
}
