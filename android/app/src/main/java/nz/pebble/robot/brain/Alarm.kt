package nz.pebble.robot.brain

import android.content.Context
import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioManager
import android.media.AudioTrack
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.speech.tts.TextToSpeech
import android.util.Log
import java.util.Locale
import kotlin.math.PI
import kotlin.math.sin

class Alarm(private val context: Context) {
    private val audio = context.getSystemService(AudioManager::class.java)
    private val main = Handler(Looper.getMainLooper())
    private var track: AudioTrack? = null
    private var savedVolume = -1
    private var speaker: TextToSpeech? = null
    @Volatile private var speakerReady = false
    private val attributes = AudioAttributes.Builder()
        .setUsage(AudioAttributes.USAGE_ALARM)
        .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
        .build()

    fun start() {
        main.post {
            speaker = TextToSpeech(context) { status ->
                val engine = speaker
                if (status == TextToSpeech.SUCCESS && engine != null) {
                    engine.setAudioAttributes(attributes)
                    val result = engine.setLanguage(Locale.getDefault())
                    if (result == TextToSpeech.LANG_MISSING_DATA || result == TextToSpeech.LANG_NOT_SUPPORTED) engine.setLanguage(Locale.US)
                    speakerReady = true
                }
            }
        }
    }

    @Synchronized
    fun sound(on: Boolean): Boolean {
        if (!on) {
            track?.let {
                try {
                    it.stop()
                } catch (e: IllegalStateException) {
                    Log.d(TAG, "the siren was already stopped")
                }
                it.release()
            }
            track = null
            restoreVolume()
            return true
        }
        if (track != null) return true
        return try {
            loud()
            val samples = siren()
            val made = AudioTrack.Builder()
                .setAudioAttributes(attributes)
                .setAudioFormat(AudioFormat.Builder().setEncoding(AudioFormat.ENCODING_PCM_16BIT).setSampleRate(RATE).setChannelMask(AudioFormat.CHANNEL_OUT_MONO).build())
                .setTransferMode(AudioTrack.MODE_STATIC)
                .setBufferSizeInBytes(samples.size * 2)
                .build()
            made.write(samples, 0, samples.size)
            made.setLoopPoints(0, samples.size, -1)
            made.setVolume(AudioTrack.getMaxVolume())
            made.play()
            track = made
            true
        } catch (e: Exception) {
            Log.e(TAG, "the siren would not play", e)
            restoreVolume()
            false
        }
    }

    fun say(text: String): Boolean {
        val engine = speaker
        if (!speakerReady || engine == null) return false
        loud()
        val params = Bundle()
        params.putFloat(TextToSpeech.Engine.KEY_PARAM_VOLUME, 1.0f)
        params.putInt(TextToSpeech.Engine.KEY_PARAM_STREAM, AudioManager.STREAM_ALARM)
        return engine.speak(text.take(TextToSpeech.getMaxSpeechInputLength()), TextToSpeech.QUEUE_FLUSH, params, "pebble-alarm") == TextToSpeech.SUCCESS
    }

    @Synchronized
    private fun loud() {
        try {
            if (savedVolume < 0) savedVolume = audio.getStreamVolume(AudioManager.STREAM_ALARM)
            audio.setStreamVolume(AudioManager.STREAM_ALARM, audio.getStreamMaxVolume(AudioManager.STREAM_ALARM), 0)
        } catch (e: Exception) {
            Log.w(TAG, "could not raise the alarm volume", e)
        }
    }

    @Synchronized
    private fun restoreVolume() {
        if (savedVolume < 0) return
        try {
            audio.setStreamVolume(AudioManager.STREAM_ALARM, savedVolume, 0)
        } catch (e: Exception) {
            Log.w(TAG, "could not put the alarm volume back", e)
        }
        savedVolume = -1
    }

    fun shutdown() {
        sound(false)
        main.post {
            speaker?.shutdown()
            speaker = null
            speakerReady = false
        }
    }

    companion object {
        const val TAG = "PebbleAlarm"
        const val RATE = 22_050
        const val LOW_HZ = 650.0
        const val HIGH_HZ = 950.0

        fun siren(): ShortArray {
            val half = RATE / 2
            val out = ShortArray(RATE)
            for (i in 0 until RATE) {
                val hz = if (i < half) LOW_HZ else HIGH_HZ
                val local = if (i < half) i else i - half
                val edge = minOf(1.0, minOf(local, half - local) / 220.0)
                out[i] = (sin(2 * PI * hz * local / RATE) * 0.9 * edge * Short.MAX_VALUE).toInt().toShort()
            }
            return out
        }
    }
}
