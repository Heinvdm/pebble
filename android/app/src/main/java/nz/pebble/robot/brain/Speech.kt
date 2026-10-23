package nz.pebble.robot.brain

import android.content.Context
import android.content.Intent
import android.media.AudioFormat
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.ParcelFileDescriptor
import android.os.SystemClock
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import android.util.Log
import com.chaquo.python.PyObject
import org.json.JSONObject
import java.io.IOException
import java.io.OutputStream
import java.util.Locale
import java.util.concurrent.ArrayBlockingQueue
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger

class Speech(private val context: Context) {
    private val main = Handler(Looper.getMainLooper())
    private val calls = Executors.newSingleThreadExecutor { Thread(it, "pebble-ears-calls") }
    val microphone = Microphone()
    val tap = SoundTap()
    val high = HighBand()
    private val probeFile = java.io.File(context.filesDir, PROBE_FILE)
    private val probeLock = Any()
    @Volatile private var probeRunning: MicProbe? = null
    private val scorer = SoundScorer {
        try {
            nz.pebble.robot.eyes.ModelFiles(context).path("yamnet.onnx")
        } catch (e: Exception) {
            null
        }
    }
    private val voice = Tts(context, { talking -> onTalking(talking) }, ::event)
    private val sherpa = EarsLink(context, SpeechModels(context).manifest() != null, ::event) { main.post { update() } }
    private val useSherpa: Boolean get() = sherpa.available
    private val engine: SpeechEngine = AndroidSpeechEngine(context, main, microphone, ::deliver)
    @Volatile private var ears: PyObject? = null
    @Volatile private var sink: PyObject? = null
    @Volatile var listener: ((JSONObject) -> Unit)? = null
    @Volatile private var speechWanted = false
    @Volatile private var tapWanted = false
    @Volatile var micAllowed = true
    @Volatile private var heard = 0
    @Volatile private var problem = ""

    fun start() {
        voice.start()
        sherpa.bind()
        lastProbe()?.optJSONObject("sweep")?.opt("hears_to_hz")?.let { if (it is Number) high.top(it.toDouble()) }
    }

    fun endEarsForTest() = sherpa.endProcessForTest()

    fun speak(text: String, whisper: Boolean): Boolean = voice.speak(text, whisper)

    fun sayPart(id: String, text: String, last: Boolean, whisper: Boolean): Boolean = voice.sayPart(id, text, last, whisper)

    fun stopSpeaking(): Double = voice.stop()

    fun setEars(target: PyObject?) {
        ears = target
    }

    fun setSink(target: PyObject?) {
        sink = target
    }

    fun configure(text: String) {
        val o = try {
            JSONObject(text)
        } catch (e: Exception) {
            return
        }
        sherpa.configure(text)
        val source = o.optString("mic_source", microphone.source)
        val echo = o.optBoolean("echo_cancel", microphone.echoCancel)
        val plan = MicPlan.parse(o, microphone.plan)
        if (source != microphone.source || echo != microphone.echoCancel || plan != microphone.plan) {
            microphone.source = if (source == Microphone.SOURCE_COMMUNICATION) Microphone.SOURCE_COMMUNICATION else Microphone.SOURCE_RECOGNITION
            microphone.echoCancel = echo
            microphone.plan = plan
            main.post {
                if (microphone.running) {
                    microphone.stop()
                    update()
                }
            }
        }
    }

    fun useTestSound(sound: Sound?) {
        microphone.useTestSound(sound)
    }

    fun listen(on: Boolean) {
        speechWanted = on
        main.post { update() }
    }

    fun soundTap(on: Boolean) {
        tapWanted = on
        main.post { update() }
    }

    fun soundRead(from: Long, maxSamples: Int): ByteArray = tap.read(from, maxSamples.coerceIn(0, Microphone.RATE * 10))

    fun soundInfo(): String = tap.info(microphone.running).put("wanted", tapWanted).put("problem", problem).toString()

    fun soundScores(from: Long): String = scorer.read(from)

    fun soundVectors(from: Long): String = scorer.readVectors(from)

    fun highBand(from: Long): String = high.read(from)

    fun highBandMoving(on: Boolean) {
        high.moving = on
    }

    private fun lastProbe(): JSONObject? = try {
        if (probeFile.exists()) JSONObject(probeFile.readText()) else null
    } catch (e: Exception) {
        null
    }

    fun micPlan(): String = JSONObject()
        .put("wanted", microphone.plan.json())
        .put("using", microphone.using.json())
        .put("step_down", microphone.stepDown)
        .put("probing", probeRunning?.phase ?: JSONObject.NULL)
        .put("probe", lastProbe()?.let { p -> JSONObject().put("at", p.opt("at")).put("suggested", p.opt("suggested")).put("clicks", p.optJSONObject("clicks")?.let { c -> JSONObject().put("verdict", c.opt("verdict")).put("spacing_m", c.opt("spacing_m")) }).put("sweep", p.optJSONObject("sweep")?.let { s -> JSONObject().put("verdict", s.opt("verdict")).put("hears_to_hz", s.opt("hears_to_hz")) }) } ?: JSONObject.NULL)
        .toString()

    fun micProbe(options: String): String = synchronized(probeLock) {
        val probe = MicProbe(context, microphone, probeFile)
        probeRunning = probe
        microphone.stop()
        try {
            val result = probe.run(try {
                JSONObject(options)
            } catch (e: Exception) {
                JSONObject()
            })
            result.optJSONObject("sweep")?.opt("hears_to_hz")?.let { if (it is Number) high.top(it.toDouble()) }
            result.toString()
        } catch (e: Exception) {
            Log.w(TAG, "the microphone probe failed", e)
            JSONObject().put("problem", e.message ?: e.javaClass.simpleName).toString()
        } finally {
            probeRunning = null
            main.post { update() }
        }
    }

    private fun update() {
        if (probeRunning != null) return
        if (!micAllowed) {
            problem = "the microphone could not be claimed because Pebble was started while its face was not on screen; it listens again after the next restart on screen"
            engine.stop()
            sherpa.stop()
            microphone.stop()
            return
        }
        if (useSherpa) {
            engine.stop()
            val micOn = tapWanted || speechWanted
            if (micOn) {
                if (!microphone.running) scorer.restart()
                microphone.add(tap)
                microphone.add(scorer)
                microphone.add(sherpa)
                microphone.addWide(high)
                if (!microphone.start()) problem = microphone.problem
            } else {
                microphone.stop()
            }
            scorer.enable(tapWanted && micOn)
            if (speechWanted) sherpa.start() else sherpa.stop()
            problem = sherpa.problem.ifEmpty { sherpa.info().optString("problem") }.ifEmpty { microphone.problem }
            return
        }
        sherpa.stop()
        microphone.remove(sherpa)
        val shares = engine.sharesMicrophone()
        val speechOn = speechWanted && engine.available() && (shares || !tapWanted)
        val micOn = tapWanted || (speechOn && shares)
        if (micOn) {
            if (!microphone.running) scorer.restart()
            microphone.add(tap)
            microphone.add(scorer)
            microphone.addWide(high)
            microphone.start()
        } else {
            microphone.stop()
        }
        scorer.enable(tapWanted && micOn)
        problem = when {
            speechWanted && !shares && tapWanted -> "this phone's speech recognizer will only use the microphone by itself, so Pebble does not listen for words while the alarm listener is on"
            speechWanted && !engine.available() -> engine.problem()
            else -> microphone.problem
        }
        if (speechOn) engine.start() else engine.stop()
    }

    private fun onTalking(talking: Boolean) {
        microphone.speaking = talking
        if (useSherpa) return
        main.post {
            if (talking) engine.pause() else main.postDelayed({ engine.resume() }, AFTER_SPEECH_MS)
        }
    }

    private fun event(data: JSONObject) {
        listener?.invoke(data)
        val target = sink
        if (target == null) {
            if (data.optString("kind") == "final") deliver(data.optString("text"), -1f)
            return
        }
        val text = data.toString()
        calls.execute {
            try {
                target.callAttr("event", text)
            } catch (e: Exception) {
                Log.w(TAG, "the brain did not take a speech event", e)
            }
        }
    }

    private fun deliver(words: String, confidence: Float) {
        heard++
        val target = ears ?: return
        calls.execute {
            try {
                target.callAttr("heard", words, confidence.toDouble())
            } catch (e: Exception) {
                Log.w(TAG, "the brain did not take what was heard", e)
            }
        }
    }

    fun state(): JSONObject = JSONObject()
        .put("listening", speechWanted && microphone.running && (if (useSherpa) sherpa.ready else engine.available()))
        .put("wanted", speechWanted)
        .put("mode", if (useSherpa) sherpa.mode else if (speechWanted) "words" else "off")
        .put("aec", microphone.echo == "on")
        .put("engine", if (useSherpa) "sherpa-onnx" else engine.name)
        .put("ears", if (useSherpa) sherpa.phase() else "android")
        .put("microphone", microphone.info())
        .put("pebble_speaking", microphone.speaking)
        .put("test_speech_ended_at", microphone.testSpeechEndedAt)
        .put("test_loop_started_at", microphone.testLoopStartedAt)

    fun info(): String = JSONObject()
        .put("speech_engine", if (useSherpa) "sherpa-onnx" else engine.name)
        .put("speech_models", if (useSherpa) "in use" else sherpa.unavailableBecause())
        .put("available", if (useSherpa) true else engine.available())
        .put("shares_microphone", if (useSherpa) true else engine.sharesMicrophone())
        .put("on_device_only", true)
        .put("wanted", speechWanted)
        .put("heard", heard)
        .put("engine", if (useSherpa) sherpa.info() else engine.info())
        .put("microphone", microphone.info())
        .put("sound_tap", tap.info(microphone.running).put("wanted", tapWanted))
        .put("high_band", JSONObject(high.read(Long.MAX_VALUE)).apply { remove("rows") })
        .put("problem", problem)
        .put("voice", voice.info())
        .toString()

    fun shutdown() {
        speechWanted = false
        tapWanted = false
        main.post {
            engine.stop()
            sherpa.shutdown()
            microphone.stop()
            scorer.enable(false)
            voice.shutdown()
        }
        calls.shutdown()
    }

    companion object {
        const val TAG = "PebbleSpeech"
        const val AFTER_SPEECH_MS = 500L
        const val PROBE_FILE = "mic-probe.json"
    }
}

object Parts {
    private val BREAKS = listOf(", ", "; ", ": ", " - ", "... ")

    fun firstWords(text: String, minWords: Int = 2, maxChars: Int = 60): List<String> {
        val clean = text.trim()
        if (clean.length <= 40) return listOf(clean)
        var best = -1
        for (mark in BREAKS) {
            var at = clean.indexOf(mark)
            while (at >= 0 && at < maxChars) {
                val words = clean.substring(0, at).trim().split(Regex("\\s+")).size
                if (words >= minWords && (best < 0 || at < best)) {
                    best = at + mark.trimEnd().length
                    break
                }
                at = clean.indexOf(mark, at + 1)
            }
        }
        if (best <= 0 || best >= clean.length - 1) return listOf(clean)
        return listOf(clean.substring(0, best).trim(), clean.substring(best).trim()).filter { it.isNotEmpty() }
    }
}

class Tts(private val context: Context, private val talking: (Boolean) -> Unit, private val report: (JSONObject) -> Unit) {
    private class Piece(val id: String, val index: Int, val lastPiece: Boolean, val offset: Int)

    private val main = Handler(Looper.getMainLooper())
    private val ids = AtomicInteger()
    private val speaking = AtomicInteger()
    private val pieces = ConcurrentHashMap<String, Piece>()
    private val begun = ConcurrentHashMap<String, Int>()
    private var tts: TextToSpeech? = null
    @Volatile private var ready = false
    @Volatile private var problem = "starting"
    @Volatile private var stopAsked = 0L
    @Volatile var lastStopMs = 0.0
    @Volatile var lastFirstSoundMs = 0.0
    private val queuedAt = ConcurrentHashMap<String, Long>()

    fun start() {
        main.post {
            tts = TextToSpeech(context) { status ->
                if (status == TextToSpeech.SUCCESS) setUp() else problem = "the phone has no text-to-speech engine"
            }
        }
    }

    private fun now(): Double = System.nanoTime() / 1e9

    private fun setUp() {
        val engine = tts ?: return
        val result = engine.setLanguage(Locale.getDefault())
        if (result == TextToSpeech.LANG_MISSING_DATA || result == TextToSpeech.LANG_NOT_SUPPORTED) engine.setLanguage(Locale.US)
        val language = engine.voice?.locale?.language
        val local = engine.voices?.filter { !it.isNetworkConnectionRequired && it.locale.language == language }?.maxByOrNull { it.quality }
        if (local != null) engine.voice = local
        engine.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
            override fun onStart(utteranceId: String?) {
                if (speaking.incrementAndGet() == 1) talking(true)
                val piece = pieces[utteranceId ?: return] ?: return
                if (piece.index == 0) {
                    begun[piece.id] = 0
                    val queued = queuedAt.remove(piece.id)
                    if (queued != null) lastFirstSoundMs = (System.nanoTime() - queued) / 1e6
                    report(JSONObject().put("kind", "spoken").put("id", piece.id).put("state", "start").put("t", now()).put("queued_ms", Math.round(lastFirstSoundMs * 10) / 10.0))
                }
            }

            override fun onRangeStart(utteranceId: String?, start: Int, end: Int, frame: Int) {
                val piece = pieces[utteranceId ?: return] ?: return
                begun[piece.id] = piece.offset + end
                report(JSONObject().put("kind", "spoken").put("id", piece.id).put("state", "word").put("t", now()).put("start", piece.offset + start).put("end", piece.offset + end))
            }

            override fun onDone(utteranceId: String?) {
                val piece = utteranceId?.let { pieces.remove(it) }
                if (piece != null && piece.lastPiece) {
                    begun.remove(piece.id)
                    report(JSONObject().put("kind", "spoken").put("id", piece.id).put("state", "done").put("t", now()))
                }
                done()
            }

            override fun onStop(utteranceId: String?, interrupted: Boolean) {
                val piece = utteranceId?.let { pieces.remove(it) }
                if (piece != null) {
                    queuedAt.remove(piece.id)
                    val spoken = begun.remove(piece.id)
                    if (spoken != null) {
                        val asked = stopAsked
                        val took = if (asked > 0) (System.nanoTime() - asked) / 1e6 else 0.0
                        lastStopMs = took
                        report(JSONObject().put("kind", "spoken").put("id", piece.id).put("state", "stopped").put("t", now()).put("chars", spoken).put("stop_ms", Math.round(took * 10) / 10.0))
                    }
                }
                if (interrupted) done()
            }

            @Deprecated("Deprecated in Java")
            override fun onError(utteranceId: String?) {
                utteranceId?.let { pieces.remove(it) }
                done()
            }

            override fun onError(utteranceId: String?, errorCode: Int) {
                utteranceId?.let { pieces.remove(it) }
                done()
            }
        })
        ready = true
        problem = if (engine.voice?.isNetworkConnectionRequired == true) "the only voice needs the internet, so Pebble may stay silent offline" else ""
    }

    private fun done() {
        if (speaking.decrementAndGet() <= 0) {
            speaking.set(0)
            talking(false)
        }
    }

    fun speak(text: String, whisper: Boolean): Boolean = sayPart("say-${ids.incrementAndGet()}", text, true, whisper)

    fun sayPart(id: String, text: String, last: Boolean, whisper: Boolean): Boolean {
        val engine = tts
        if (!ready || engine == null) return false
        val clean = text.trim()
        if (clean.isEmpty()) {
            report(JSONObject().put("kind", "spoken").put("id", id).put("state", "done").put("t", now()))
            return true
        }
        val split = Parts.firstWords(clean)
        queuedAt[id] = System.nanoTime()
        var offset = 0
        var ok = true
        split.forEachIndexed { i, piece ->
            val params = Bundle()
            params.putFloat(TextToSpeech.Engine.KEY_PARAM_VOLUME, if (whisper) 0.35f else 1.0f)
            val key = "$id#$i#${ids.incrementAndGet()}"
            pieces[key] = Piece(id, i, i == split.lastIndex, offset)
            if (engine.speak(piece.take(TextToSpeech.getMaxSpeechInputLength()), TextToSpeech.QUEUE_ADD, params, key) != TextToSpeech.SUCCESS) {
                pieces.remove(key)
                ok = false
            }
            offset = clean.indexOf(split.getOrElse(i + 1) { "" }, offset + piece.length).coerceAtLeast(offset + piece.length)
        }
        return ok
    }

    fun stop(): Double {
        val engine = tts ?: return 0.0
        val asked = System.nanoTime()
        stopAsked = asked
        engine.stop()
        return (System.nanoTime() - asked) / 1e6
    }

    fun info(): JSONObject = JSONObject()
        .put("ready", ready)
        .put("problem", problem)
        .put("voice", tts?.voice?.name ?: JSONObject.NULL)
        .put("offline", tts?.voice?.isNetworkConnectionRequired == false)
        .put("last_stop_ms", Math.round(lastStopMs * 10) / 10.0)
        .put("last_first_sound_ms", Math.round(lastFirstSoundMs * 10) / 10.0)

    fun shutdown() {
        tts?.stop()
        tts?.shutdown()
        tts = null
        ready = false
    }
}

interface SpeechEngine {
    val name: String
    fun available(): Boolean
    fun sharesMicrophone(): Boolean
    fun problem(): String
    fun start()
    fun stop()
    fun pause()
    fun resume()
    fun info(): JSONObject
}

class AndroidSpeechEngine(
    private val context: Context,
    private val main: Handler,
    private val microphone: Microphone,
    private val deliver: (String, Float) -> Unit,
) : SpeechEngine {
    override val name = "android-on-device"
    private var recognizer: SpeechRecognizer? = null
    private var shared = Build.VERSION.SDK_INT >= 33
    private var wanted = false
    private var active = false
    private var paused = false
    private var startedAt = 0L
    private var sharedFailures = 0
    private var lastError = 0
    private var problem = ""
    private var pipe: PipeFeed? = null

    override fun available(): Boolean = Build.VERSION.SDK_INT >= 31 && SpeechRecognizer.isOnDeviceRecognitionAvailable(context)

    override fun sharesMicrophone(): Boolean = shared

    override fun problem(): String = if (available()) problem else "this phone has no on-device speech recognition, so Pebble does not listen for words (nothing is ever sent off the phone)"

    override fun start() {
        wanted = true
        begin()
    }

    override fun stop() {
        wanted = false
        main.removeCallbacksAndMessages(TOKEN)
        end()
        recognizer?.destroy()
        recognizer = null
    }

    override fun pause() {
        if (shared) return
        paused = true
        if (active) {
            recognizer?.cancel()
            active = false
        }
    }

    override fun resume() {
        if (shared) return
        paused = false
        begin()
    }

    private fun recognizer(): SpeechRecognizer? {
        recognizer?.let { return it }
        if (!available()) return null
        val made = SpeechRecognizer.createOnDeviceSpeechRecognizer(context)
        made.setRecognitionListener(listener)
        recognizer = made
        return made
    }

    private fun intent(): Intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
        putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
        putExtra(RecognizerIntent.EXTRA_LANGUAGE, Locale.getDefault().toLanguageTag())
        putExtra(RecognizerIntent.EXTRA_PREFER_OFFLINE, true)
        putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1)
        putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, false)
    }

    private fun begin() {
        if (!wanted || active || (paused && !shared)) return
        val r = recognizer() ?: return
        val intent = intent()
        try {
            if (shared && Build.VERSION.SDK_INT >= 33) {
                val feed = PipeFeed(microphone)
                pipe = feed
                intent.putExtra(RecognizerIntent.EXTRA_AUDIO_SOURCE, feed.readEnd)
                intent.putExtra(RecognizerIntent.EXTRA_AUDIO_SOURCE_CHANNEL_COUNT, 1)
                intent.putExtra(RecognizerIntent.EXTRA_AUDIO_SOURCE_ENCODING, AudioFormat.ENCODING_PCM_16BIT)
                intent.putExtra(RecognizerIntent.EXTRA_AUDIO_SOURCE_SAMPLING_RATE, microphone.rate)
                intent.putExtra(RecognizerIntent.EXTRA_SEGMENTED_SESSION, RecognizerIntent.EXTRA_AUDIO_SOURCE)
                r.startListening(intent)
                feed.started()
            } else {
                r.startListening(intent)
            }
            active = true
            startedAt = SystemClock.elapsedRealtime()
        } catch (e: Exception) {
            problem = "listening failed to start: ${e.message}"
            Log.w(TAG, problem, e)
            end()
            later(RETRY_MS)
        }
    }

    private fun end() {
        pipe?.close()
        pipe = null
        if (active) recognizer?.cancel()
        active = false
    }

    private fun later(delay: Long) {
        main.removeCallbacksAndMessages(TOKEN)
        main.postAtTime({ begin() }, TOKEN, SystemClock.uptimeMillis() + delay)
    }

    private fun sharedFailed(error: Int) {
        if (!shared || SystemClock.elapsedRealtime() - startedAt > 3_000) return
        sharedFailures++
        if (sharedFailures >= 3) {
            shared = false
            problem = "this phone's speech recognizer would not take Pebble's own microphone feed (error $error), so it now uses the microphone itself"
            Log.w(TAG, problem)
        }
    }

    private val listener = object : RecognitionListener {
        override fun onReadyForSpeech(params: Bundle?) {
            pipe?.releaseReadEnd()
            problem = if (shared || !problem.startsWith("this phone's")) "" else problem
        }

        override fun onBeginningOfSpeech() = Unit
        override fun onRmsChanged(rmsdB: Float) = Unit
        override fun onBufferReceived(buffer: ByteArray?) = Unit
        override fun onEndOfSpeech() = Unit
        override fun onPartialResults(partialResults: Bundle?) = Unit
        override fun onEvent(eventType: Int, params: Bundle?) = Unit

        override fun onSegmentResults(segmentResults: Bundle) {
            sharedFailures = 0
            take(segmentResults)
        }

        override fun onEndOfSegmentedSession() {
            end()
            later(0)
        }

        override fun onResults(results: Bundle?) {
            sharedFailures = 0
            take(results)
            end()
            later(0)
        }

        override fun onError(error: Int) {
            lastError = error
            end()
            when (error) {
                SpeechRecognizer.ERROR_NO_MATCH, SpeechRecognizer.ERROR_SPEECH_TIMEOUT -> later(0)
                SpeechRecognizer.ERROR_RECOGNIZER_BUSY -> later(RETRY_MS)
                SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS -> problem = "Pebble may not use the microphone"
                SpeechRecognizer.ERROR_LANGUAGE_NOT_SUPPORTED, SpeechRecognizer.ERROR_LANGUAGE_UNAVAILABLE -> {
                    problem = "the phone has no offline speech pack for ${Locale.getDefault().displayName}; download it once in the phone's speech settings"
                    if (Build.VERSION.SDK_INT >= 33) {
                        try {
                            recognizer?.triggerModelDownload(intent())
                        } catch (e: Exception) {
                            Log.w(TAG, "could not ask for the offline speech pack", e)
                        }
                    }
                    later(LONG_RETRY_MS)
                }
                SpeechRecognizer.ERROR_AUDIO, SpeechRecognizer.ERROR_CLIENT, SpeechRecognizer.ERROR_SERVER -> {
                    sharedFailed(error)
                    problem = if (problem.isEmpty()) "listening stopped with error $error" else problem
                    later(RETRY_MS)
                }
                else -> {
                    problem = "listening stopped with error $error"
                    recognizer?.destroy()
                    recognizer = null
                    later(RETRY_MS)
                }
            }
        }
    }

    private fun take(bundle: Bundle?) {
        val words = bundle?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull()?.trim().orEmpty()
        val confidence = bundle?.getFloatArray(SpeechRecognizer.CONFIDENCE_SCORES)?.firstOrNull() ?: -1f
        if (words.isNotEmpty()) deliver(words, confidence)
    }

    override fun info(): JSONObject = JSONObject()
        .put("mode", if (shared) "fed from Pebble's own microphone feed" else "the recognizer uses the microphone itself")
        .put("active", active)
        .put("last_error", lastError)
        .put("problem", problem())

    companion object {
        const val TAG = "PebbleListen"
        const val RETRY_MS = 1_500L
        const val LONG_RETRY_MS = 60_000L
        private val TOKEN = Any()
    }
}

class PipeFeed(private val microphone: Microphone) : AudioSink {
    private val ends = ParcelFileDescriptor.createPipe()
    val readEnd: ParcelFileDescriptor = ends[0]
    private val output: OutputStream = ParcelFileDescriptor.AutoCloseOutputStream(ends[1])
    private val queue = ArrayBlockingQueue<ByteArray>(QUEUE)
    @Volatile private var open = true
    private var writer: Thread? = null

    fun started() {
        writer = Thread({ drain() }, "pebble-listen-feed").also { it.start() }
        microphone.add(this)
    }

    override fun onAudio(pcm: ShortArray, count: Int, speaking: Boolean) {
        if (!open) return
        val bytes = ByteArray(count * 2)
        if (!speaking) {
            for (i in 0 until count) {
                val v = pcm[i].toInt()
                bytes[2 * i] = (v and 0xFF).toByte()
                bytes[2 * i + 1] = ((v shr 8) and 0xFF).toByte()
            }
        }
        queue.offer(bytes)
    }

    private fun drain() {
        try {
            while (open) {
                val next = queue.poll(200, TimeUnit.MILLISECONDS) ?: continue
                output.write(next)
            }
        } catch (e: IOException) {
            Log.d(TAG, "the recognizer closed its end of the feed")
        } catch (e: InterruptedException) {
            Log.d(TAG, "the feed was stopped")
        } finally {
            open = false
            microphone.remove(this)
            try {
                output.close()
            } catch (e: IOException) {
                Log.d(TAG, "the feed was already closed")
            }
        }
    }

    fun releaseReadEnd() {
        try {
            readEnd.close()
        } catch (e: IOException) {
            Log.d(TAG, "the read end was already closed")
        }
    }

    fun close() {
        open = false
        microphone.remove(this)
        writer?.interrupt()
        writer = null
        releaseReadEnd()
        try {
            output.close()
        } catch (e: IOException) {
            Log.d(TAG, "the feed was already closed")
        }
    }

    companion object {
        const val TAG = "PebbleListenFeed"
        const val QUEUE = 100
    }
}
