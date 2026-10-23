package nz.pebble.robot.brain

import java.nio.ByteBuffer
import java.nio.ByteOrder

class Sound(val samples: ShortArray, val rate: Int, val channels: Int) {
    val frames: Int get() = samples.size / channels

    fun channel(index: Int): ShortArray = ShortArray(frames) { samples[it * channels + index] }
}

object Wav {
    fun pcm16(bytes: ByteArray, rate: Int = Microphone.RATE): ShortArray {
        val sound = read(bytes)
        require(sound.rate == rate) { "the WAV must be $rate Hz, not ${sound.rate}" }
        return if (sound.channels == 1) sound.samples else sound.channel(0)
    }

    fun read(bytes: ByteArray): Sound {
        val buffer = ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN)
        require(bytes.size >= 12 && String(bytes, 0, 4) == "RIFF" && String(bytes, 8, 4) == "WAVE") { "not a WAV file" }
        var position = 12
        var channels = 0
        var sampleRate = 0
        var bits = 0
        var format = 0
        while (position + 8 <= bytes.size) {
            val id = String(bytes, position, 4)
            val size = buffer.getInt(position + 4)
            val body = position + 8
            if (id == "fmt ") {
                format = buffer.getShort(body).toInt()
                channels = buffer.getShort(body + 2).toInt()
                sampleRate = buffer.getInt(body + 4)
                bits = buffer.getShort(body + 14).toInt()
            } else if (id == "data") {
                require(format == 1 && bits == 16) { "the WAV must be 16-bit PCM" }
                require(channels in 1..8) { "the WAV has $channels channels" }
                val count = minOf(size, bytes.size - body) / (2 * channels) * channels
                return Sound(ShortArray(count) { buffer.getShort(body + it * 2) }, sampleRate, channels)
            }
            position = body + size + (size and 1)
        }
        throw IllegalArgumentException("the WAV has no sound in it")
    }
}
