package nz.pebble.robot.brain

import kotlin.math.PI
import kotlin.math.max
import kotlin.math.roundToInt
import kotlin.math.sin
import kotlin.math.sqrt

object Kaiser {
    fun bessel0(x: Double): Double {
        var sum = 1.0
        var term = 1.0
        val half = x / 2
        var k = 1
        while (term > sum * 1e-17) {
            term *= (half / k) * (half / k)
            sum += term
            k++
        }
        return sum
    }

    fun lowPass(taps: Int, cutoffHz: Double, rateHz: Double, beta: Double): FloatArray {
        val middle = (taps - 1) / 2.0
        val fc = cutoffHz / rateHz
        val scale = bessel0(beta)
        val h = DoubleArray(taps) { n ->
            val x = n - middle
            val ideal = if (x == 0.0) 2 * fc else sin(2 * PI * fc * x) / (PI * x)
            val r = x / middle
            ideal * bessel0(beta * sqrt(max(0.0, 1 - r * r))) / scale
        }
        val sum = h.sum()
        return FloatArray(taps) { (h[it] / sum).toFloat() }
    }
}

class Decimate(val factor: Int, val taps: FloatArray = design(factor)) {
    private val n = taps.size
    private val half = n / 2
    private var buffer = FloatArray(n - 1 + 4096)
    private var phase = 0

    init {
        require(factor >= 1 && n % 2 == 1) { "a decimator needs a whole factor and an odd number of taps" }
    }

    val delay: Int get() = (n - 1) / 2

    fun push(input: ShortArray, start: Int, frames: Int, stride: Int, out: ShortArray, at: Int = 0): Int {
        val needed = n - 1 + frames
        if (buffer.size < needed) buffer = buffer.copyOf(needed)
        val b = buffer
        for (i in 0 until frames) b[n - 1 + i] = input[start + i * stride].toFloat()
        var made = 0
        var j = n - 1
        val end = n - 1 + frames
        while (j < end) {
            phase++
            if (phase == factor) {
                phase = 0
                var acc = taps[half] * b[j - half]
                var k = 0
                while (k < half) {
                    acc += taps[k] * (b[j - k] + b[j - (n - 1) + k])
                    k++
                }
                val v = acc.roundToInt()
                out[at + made] = (if (v > 32767) 32767 else if (v < -32768) -32768 else v).toShort()
                made++
            }
            j++
        }
        System.arraycopy(b, frames, b, 0, n - 1)
        return made
    }

    fun reset() {
        java.util.Arrays.fill(buffer, 0f)
        phase = 0
    }

    companion object {
        const val CUTOFF_HZ = 8_000.0
        const val BETA = 7.0
        const val TAPS_PER_STEP = 80

        fun taps(factor: Int): Int = TAPS_PER_STEP * factor + 1

        fun design(factor: Int): FloatArray = if (factor <= 1) floatArrayOf(1f) else Kaiser.lowPass(taps(factor), CUTOFF_HZ, Microphone.RATE.toDouble() * factor, BETA)
    }
}
