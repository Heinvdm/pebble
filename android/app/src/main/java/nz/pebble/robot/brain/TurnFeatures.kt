package nz.pebble.robot.brain

import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.ln
import kotlin.math.log10
import kotlin.math.max
import kotlin.math.sin
import kotlin.math.sqrt

object TurnFeatures {
    const val RATE = 16_000
    const val SECONDS = 8
    const val SAMPLES = RATE * SECONDS
    const val N_FFT = 400
    const val HOP = 160
    const val MELS = 80
    const val FRAMES = SAMPLES / HOP
    const val BINS = N_FFT / 2 + 1

    private val window = DoubleArray(N_FFT) { 0.5 - 0.5 * cos(2 * PI * it / N_FFT) }
    private val filters: Array<DoubleArray> = melFilters()
    private val cosTable = DoubleArray(N_FFT) { cos(-2 * PI * it / N_FFT) }
    private val sinTable = DoubleArray(N_FFT) { sin(-2 * PI * it / N_FFT) }

    fun lastSeconds(audio: FloatArray, count: Int = audio.size): FloatArray {
        val out = FloatArray(SAMPLES)
        val n = minOf(count, SAMPLES)
        System.arraycopy(audio, count - n, out, SAMPLES - n, n)
        return out
    }

    fun features(audio: FloatArray): FloatArray {
        require(audio.size == SAMPLES) { "the end-of-turn model needs exactly $SAMPLES samples" }
        var mean = 0.0
        for (x in audio) mean += x
        mean /= SAMPLES
        var variance = 0.0
        for (x in audio) {
            val d = x - mean
            variance += d * d
        }
        variance /= SAMPLES
        val scale = 1.0 / sqrt(variance + 1e-7)
        val pad = N_FFT / 2
        val padded = DoubleArray(SAMPLES + 2 * pad)
        for (i in 0 until SAMPLES) padded[pad + i] = (audio[i] - mean) * scale
        for (i in 0 until pad) {
            padded[pad - 1 - i] = padded[pad + 1 + i]
            padded[pad + SAMPLES + i] = padded[pad + SAMPLES - 2 - i]
        }
        val logMel = DoubleArray(MELS * FRAMES)
        val re = DoubleArray(N_FFT)
        val im = DoubleArray(N_FFT)
        val power = DoubleArray(BINS)
        var top = Double.NEGATIVE_INFINITY
        for (frame in 0 until FRAMES) {
            val start = frame * HOP
            for (i in 0 until N_FFT) {
                re[i] = padded[start + i] * window[i]
                im[i] = 0.0
            }
            fft(re, im)
            for (k in 0 until BINS) power[k] = re[k] * re[k] + im[k] * im[k]
            for (m in 0 until MELS) {
                val f = filters[m]
                var sum = 0.0
                for (k in 0 until BINS) sum += f[k] * power[k]
                val value = log10(max(sum, 1e-10))
                logMel[m * FRAMES + frame] = value
                if (value > top) top = value
            }
        }
        val floor = top - 8.0
        return FloatArray(MELS * FRAMES) { ((max(logMel[it], floor) + 4.0) / 4.0).toFloat() }
    }

    private fun fft(re: DoubleArray, im: DoubleArray) {
        val n = re.size
        val outRe = DoubleArray(n)
        val outIm = DoubleArray(n)
        transform(re, im, 0, 1, n, outRe, outIm, 0)
        System.arraycopy(outRe, 0, re, 0, n)
        System.arraycopy(outIm, 0, im, 0, n)
    }

    private fun smallestFactor(n: Int): Int {
        var p = 2
        while (p * p <= n) {
            if (n % p == 0) return p
            p++
        }
        return n
    }

    private fun transform(re: DoubleArray, im: DoubleArray, offset: Int, stride: Int, n: Int, outRe: DoubleArray, outIm: DoubleArray, outOffset: Int) {
        if (n == 1) {
            outRe[outOffset] = re[offset]
            outIm[outOffset] = im[offset]
            return
        }
        val p = smallestFactor(n)
        val m = n / p
        for (r in 0 until p) transform(re, im, offset + r * stride, stride * p, m, outRe, outIm, outOffset + r * m)
        val partRe = DoubleArray(p)
        val partIm = DoubleArray(p)
        val step = N_FFT / n
        for (k in 0 until m) {
            for (r in 0 until p) {
                partRe[r] = outRe[outOffset + r * m + k]
                partIm[r] = outIm[outOffset + r * m + k]
            }
            for (q in 0 until p) {
                val kk = k + q * m
                var sumRe = 0.0
                var sumIm = 0.0
                for (r in 0 until p) {
                    val t = (r * kk % n) * step
                    val c = cosTable[t]
                    val s = sinTable[t]
                    sumRe += partRe[r] * c - partIm[r] * s
                    sumIm += partRe[r] * s + partIm[r] * c
                }
                outRe[outOffset + kk] = sumRe
                outIm[outOffset + kk] = sumIm
            }
        }
    }

    private fun hzToMel(hz: Double): Double {
        val minLogHz = 1000.0
        val minLogMel = 15.0
        val logStep = 27.0 / ln(6.4)
        return if (hz >= minLogHz) minLogMel + ln(hz / minLogHz) * logStep else 3.0 * hz / 200.0
    }

    private fun melToHz(mel: Double): Double {
        val minLogHz = 1000.0
        val minLogMel = 15.0
        val logStep = ln(6.4) / 27.0
        return if (mel >= minLogMel) minLogHz * kotlin.math.exp(logStep * (mel - minLogMel)) else 200.0 * mel / 3.0
    }

    private fun melFilters(): Array<DoubleArray> {
        val low = hzToMel(0.0)
        val high = hzToMel(RATE / 2.0)
        val points = DoubleArray(MELS + 2) { melToHz(low + (high - low) * it / (MELS + 1)) }
        val fft = DoubleArray(BINS) { (RATE / 2.0) * it / (BINS - 1) }
        return Array(MELS) { m ->
            val left = points[m]
            val centre = points[m + 1]
            val right = points[m + 2]
            val norm = 2.0 / (right - left)
            DoubleArray(BINS) { k ->
                val down = (fft[k] - left) / (centre - left)
                val up = (right - fft[k]) / (right - centre)
                max(0.0, minOf(down, up)) * norm
            }
        }
    }
}
