package nz.pebble.robot.brain

import android.annotation.SuppressLint
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.media.audiofx.AcousticEchoCanceler
import android.util.Log
import org.json.JSONObject
import java.util.concurrent.CopyOnWriteArrayList
import kotlin.math.abs
import kotlin.math.log10
import kotlin.math.max
import kotlin.math.sqrt

fun interface AudioSink {
    fun onAudio(pcm: ShortArray, count: Int, speaking: Boolean)
}

fun interface WideSink {
    fun onWide(pcm: ShortArray, frames: Int, channels: Int, rate: Int, speaking: Boolean)
}

data class MicPlan(val rate: Int = Microphone.RATE, val channels: Int = 1, val speechChannel: Int = 0) {
    val wide: Boolean get() = rate != Microphone.RATE || channels != 1
    val factor: Int get() = rate / Microphone.RATE

    fun valid(): Boolean = rate % Microphone.RATE == 0 && factor in FACTORS && channels in 1..2 && speechChannel in 0 until channels

    fun json(): JSONObject = JSONObject().put("rate", rate).put("channels", channels).put("speech_channel", speechChannel)

    companion object {
        val TODAY = MicPlan()
        val FACTORS = setOf(1, 2, 3, 6)

        fun parse(o: JSONObject, base: MicPlan): MicPlan {
            val next = MicPlan(o.optInt("mic_rate", base.rate), o.optInt("mic_channels", base.channels), o.optInt("mic_speech_channel", base.speechChannel))
            return if (next.valid()) next else base
        }
    }
}

class Narrow(val plan: MicPlan) {
    private val down = Decimate(plan.factor)
    var out = ShortArray(0)
        private set

    fun take(pcm: ShortArray, count: Int): Int {
        val frames = count / plan.channels
        if (out.size < frames / plan.factor + 1) out = ShortArray(frames / plan.factor + 1)
        return down.push(pcm, plan.speechChannel, frames, plan.channels, out)
    }
}

class Microphone(val rate: Int = RATE) {
    private val sinks = CopyOnWriteArrayList<AudioSink>()
    private val wides = CopyOnWriteArrayList<WideSink>()
    @Volatile private var thread: Thread? = null
    @Volatile private var stop = false
    @Volatile var speaking = false
    @Volatile var probing = false
    @Volatile var problem = ""
    @Volatile var chunks = 0L
    @Volatile var source = SOURCE_RECOGNITION
    @Volatile var echoCancel = true
    @Volatile var plan = MicPlan.TODAY
    @Volatile var using = MicPlan.TODAY
        private set
    @Volatile var stepDown = ""
        private set
    @Volatile var echo = "off"
        private set
    @Volatile private var testAudio: Sound? = null
    @Volatile var testSpeechEndedAt = 0.0
        private set
    @Volatile var testLoopStartedAt = 0.0
        private set

    val running: Boolean get() = thread != null

    fun add(sink: AudioSink) {
        if (sink !in sinks) sinks += sink
    }

    fun remove(sink: AudioSink) {
        sinks -= sink
    }

    fun addWide(sink: WideSink) {
        if (sink !in wides) wides += sink
    }

    fun removeWide(sink: WideSink) {
        wides -= sink
    }

    fun useTestAudio(samples: ShortArray?) {
        testAudio = samples?.let { Sound(it, RATE, 1) }
    }

    fun useTestSound(sound: Sound?) {
        testAudio = sound
    }

    @SuppressLint("MissingPermission")
    @Synchronized
    fun start(): Boolean {
        if (thread != null) return true
        stop = false
        problem = ""
        val test = testAudio
        if (test != null) {
            val tested = MicPlan(test.rate, test.channels, plan.speechChannel.coerceAtMost(test.channels - 1))
            if (!tested.valid()) {
                problem = "the test sound must be 16, 32, 48 or 96 kHz with one or two channels, not ${test.rate} Hz with ${test.channels}"
                return false
            }
            echo = "test audio"
            using = tested
            thread = Thread({ play(test, tested) }, "pebble-microphone").also { it.start() }
            return true
        }
        val wanted = plan
        var record = open(wanted)
        var chosen = wanted
        stepDown = ""
        if (record == null && wanted.wide) {
            stepDown = "the phone would not record ${wanted.rate / 1000} kHz with ${wanted.channels} channel${if (wanted.channels == 1) "" else "s"} (${problem.ifEmpty { "no reason given" }}), so Pebble listens at 16 kHz"
            Log.w(TAG, stepDown)
            problem = ""
            chosen = MicPlan.TODAY
            record = open(chosen)
        }
        if (record == null) return false
        using = chosen
        val canceller = attachEchoCanceller(record.audioSessionId)
        thread = Thread({ pump(record, canceller, chosen) }, "pebble-microphone").also { it.start() }
        return true
    }

    @SuppressLint("MissingPermission")
    private fun open(p: MicPlan): AudioRecord? {
        val mask = if (p.channels == 2) AudioFormat.CHANNEL_IN_STEREO else AudioFormat.CHANNEL_IN_MONO
        val minimum = AudioRecord.getMinBufferSize(p.rate, mask, AudioFormat.ENCODING_PCM_16BIT)
        if (minimum <= 0) {
            problem = "the phone cannot record ${p.rate / 1000} kHz sound with ${p.channels} channel${if (p.channels == 1) "" else "s"}"
            return null
        }
        val record = try {
            AudioRecord(if (source == SOURCE_COMMUNICATION) MediaRecorder.AudioSource.VOICE_COMMUNICATION else MediaRecorder.AudioSource.VOICE_RECOGNITION, p.rate, mask, AudioFormat.ENCODING_PCM_16BIT, max(minimum, p.rate / 2 * 2 * p.channels))
        } catch (e: Exception) {
            problem = "the microphone would not open: ${e.message}"
            return null
        }
        if (record.state != AudioRecord.STATE_INITIALIZED) {
            record.release()
            problem = "the microphone would not open (is another app using it, or is the permission missing?)"
            return null
        }
        return record
    }

    private fun attachEchoCanceller(session: Int): AcousticEchoCanceler? {
        if (!echoCancel) {
            echo = "off"
            return null
        }
        if (!AcousticEchoCanceler.isAvailable()) {
            echo = "not offered by this phone"
            return null
        }
        return try {
            val made = AcousticEchoCanceler.create(session)
            if (made == null) {
                echo = "could not be made"
                null
            } else {
                made.enabled = true
                echo = if (made.enabled) "on" else "would not switch on"
                made
            }
        } catch (e: Exception) {
            echo = "failed: ${e.message}"
            null
        }
    }

    @Synchronized
    fun stop() {
        stop = true
        thread?.join(2_000)
        thread = null
    }

    private fun deliver(chunk: ShortArray, count: Int) {
        chunks++
        val talking = speaking || probing
        for (sink in sinks) {
            try {
                sink.onAudio(chunk, count, talking)
            } catch (e: Exception) {
                Log.w(TAG, "a listener of the microphone failed", e)
            }
        }
    }

    fun pass(chunk: ShortArray, count: Int, p: MicPlan, narrow: Narrow?) {
        if (narrow == null) {
            deliver(chunk, count)
            return
        }
        val talking = speaking || probing
        for (sink in wides) {
            try {
                sink.onWide(chunk, count / p.channels, p.channels, p.rate, talking)
            } catch (e: Exception) {
                Log.w(TAG, "a listener of the wide sound failed", e)
            }
        }
        val n = narrow.take(chunk, count)
        if (n > 0) deliver(narrow.out, n)
    }

    private fun pump(record: AudioRecord, canceller: AcousticEchoCanceler?, p: MicPlan) {
        android.os.Process.setThreadPriority(android.os.Process.THREAD_PRIORITY_URGENT_AUDIO)
        val chunk = ShortArray(p.rate / 50 * p.channels)
        val narrow = if (p.wide) Narrow(p) else null
        try {
            record.startRecording()
            while (!stop) {
                val count = record.read(chunk, 0, chunk.size)
                if (count < 0) {
                    problem = "the microphone stopped (error $count)"
                    Log.w(TAG, problem)
                    break
                }
                if (count > 0) pass(chunk, count - count % p.channels, p, narrow)
            }
        } catch (e: Exception) {
            problem = "the microphone failed: ${e.message}"
            Log.w(TAG, problem, e)
        } finally {
            try {
                record.stop()
            } catch (e: Exception) {
                Log.d(TAG, "the microphone was already stopped")
            }
            canceller?.release()
            record.release()
            synchronized(this) {
                if (thread == Thread.currentThread()) thread = null
            }
        }
    }

    private fun play(sound: Sound, p: MicPlan) {
        val frames = p.rate / 50
        val chunk = ShortArray(frames * p.channels)
        val narrow = if (p.wide) Narrow(p) else null
        val step = 1_000_000_000L / 50
        var next = System.nanoTime()
        var position = 0
        val total = sound.frames
        val last = lastLoud(sound.samples, sound.channels, p.speechChannel)
        try {
            while (!stop) {
                java.util.Arrays.fill(chunk, 0)
                if (position == 0) testLoopStartedAt = System.nanoTime() / 1e9
                if (position < total) {
                    val n = minOf(frames, total - position)
                    System.arraycopy(sound.samples, position * p.channels, chunk, 0, n * p.channels)
                    if (last in position until position + frames) testSpeechEndedAt = (System.nanoTime() + (last - position) * 1_000_000_000L / p.rate) / 1e9
                }
                position += frames
                if (position >= maxOf(total + p.rate * 4, p.rate * TEST_PERIOD_S)) position = 0
                pass(chunk, chunk.size, p, narrow)
                next += step
                val wait = next - System.nanoTime()
                if (wait > 0) Thread.sleep(wait / 1_000_000, (wait % 1_000_000).toInt())
            }
        } catch (e: InterruptedException) {
            Log.d(TAG, "test audio stopped")
        } finally {
            synchronized(this) {
                if (thread == Thread.currentThread()) thread = null
            }
        }
    }

    fun info(): JSONObject = JSONObject()
        .put("running", running)
        .put("source", if (testAudio != null) "test audio" else if (source == SOURCE_COMMUNICATION) "voice communication" else "voice recognition")
        .put("echo_canceller", echo)
        .put("rate", using.rate)
        .put("channels", using.channels)
        .put("plan", plan.json())
        .put("step_down", stepDown)
        .put("probing", probing)
        .put("problem", problem)

    companion object {
        const val TAG = "PebbleMic"
        const val RATE = 16_000
        const val SOURCE_RECOGNITION = "recognition"
        const val SOURCE_COMMUNICATION = "communication"
        const val LOUD = 1_000
        const val TEST_PERIOD_S = 15

        fun lastLoud(samples: ShortArray): Int = lastLoud(samples, 1, 0)

        fun lastLoud(samples: ShortArray, channels: Int, channel: Int): Int {
            for (i in samples.size / channels - 1 downTo 0) if (abs(samples[i * channels + channel].toInt()) > LOUD) return i
            return -1
        }
    }
}

class SoundTap(seconds: Int = 10, val rate: Int = Microphone.RATE) : AudioSink {
    private val ring = ShortArray(seconds * rate)
    private var total = 0L
    @Volatile private var level = -120.0
    @Volatile private var speakingNow = false

    override fun onAudio(pcm: ShortArray, count: Int, speaking: Boolean) {
        var sum = 0.0
        synchronized(ring) {
            for (i in 0 until count) {
                val v = pcm[i]
                ring[((total + i) % ring.size).toInt()] = v
                sum += v.toDouble() * v
            }
            total += count
        }
        val rms = sqrt(sum / max(1, count)) / 32768.0
        val db = if (rms > 0) 20 * log10(rms) else -120.0
        level = level * 0.8 + db * 0.2
        speakingNow = speaking
    }

    fun read(from: Long, maxSamples: Int): ByteArray = synchronized(ring) {
        val oldest = max(0L, total - ring.size)
        val start = from.coerceIn(oldest, total)
        val count = minOf(maxSamples.toLong(), total - start).toInt()
        val out = ByteArray(count * 2)
        for (i in 0 until count) {
            val v = ring[((start + i) % ring.size).toInt()].toInt()
            out[2 * i] = (v and 0xFF).toByte()
            out[2 * i + 1] = ((v shr 8) and 0xFF).toByte()
        }
        out
    }

    fun info(running: Boolean): JSONObject = synchronized(ring) {
        JSONObject()
            .put("running", running)
            .put("rate", rate)
            .put("total", total)
            .put("kept", minOf(total, ring.size.toLong()))
            .put("level_db", Math.round(level * 10) / 10.0)
            .put("speaking", speakingNow)
            .put("format", "pcm_s16le mono")
    }
}
