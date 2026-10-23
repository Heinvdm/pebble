package nz.pebble.robot.eyes

import java.util.Base64

object Glow {
    const val WIDTH = 80
    const val HEIGHT = 60
    const val CELLS = WIDTH * HEIGHT
    const val RED_LOW = 22
    const val RED_HIGH = 170
    const val SATURATION = 110
    const val VALUE = 190

    fun warm(hsv: ByteArray): Double {
        val cells = hsv.size / 3
        if (cells == 0) return 0.0
        var count = 0
        for (i in 0 until cells) {
            val h = hsv[i * 3].toInt() and 0xFF
            val s = hsv[i * 3 + 1].toInt() and 0xFF
            val v = hsv[i * 3 + 2].toInt() and 0xFF
            if ((h <= RED_LOW || h >= RED_HIGH) && s >= SATURATION && v >= VALUE) count++
        }
        return count.toDouble() / cells
    }

    fun brightest(bgr: ByteArray): ByteArray = ByteArray(bgr.size / 3) { i ->
        maxOf(bgr[i * 3].toInt() and 0xFF, bgr[i * 3 + 1].toInt() and 0xFF, bgr[i * 3 + 2].toInt() and 0xFF).toByte()
    }

    fun encode(levels: ByteArray): String = Base64.getEncoder().encodeToString(levels)
}
