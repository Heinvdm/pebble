package nz.pebble.robot.recall

import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.nio.FloatBuffer
import kotlin.math.sqrt

interface Encoder : AutoCloseable {
    class Stopped : RuntimeException("stopped to give way")

    fun encode(rows: List<IntArray>, token: Any? = null): Array<FloatArray>

    fun stop(token: Any) = Unit
}

object Pooling {
    const val DIM = 384

    class Padded(val ids: LongArray, val mask: LongArray, val types: LongArray, val count: Int, val width: Int)

    fun pad(rows: List<IntArray>): Padded {
        val width = rows.maxOfOrNull { it.size } ?: 0
        val ids = LongArray(rows.size * width)
        val mask = LongArray(rows.size * width)
        for ((r, row) in rows.withIndex()) {
            for ((c, id) in row.withIndex()) {
                ids[r * width + c] = id.toLong()
                mask[r * width + c] = 1L
            }
        }
        return Padded(ids, mask, LongArray(rows.size * width), rows.size, width)
    }

    fun first(hidden: FloatBuffer, shape: LongArray): Array<FloatArray> {
        val count = shape[0].toInt()
        val dim = shape[shape.size - 1].toInt()
        val stride = if (shape.size == 3) shape[1].toInt() * dim else dim
        val base = hidden.position()
        return Array(count) { r ->
            val row = FloatArray(dim)
            for (k in 0 until dim) row[k] = hidden.get(base + r * stride + k)
            normalize(row)
        }
    }

    fun normalize(row: FloatArray): FloatArray {
        var sum = 0.0
        for (v in row) sum += v.toDouble() * v
        val size = sqrt(sum)
        if (size == 0.0 || size.isNaN()) return row
        for (k in row.indices) row[k] = (row[k] / size).toFloat()
        return row
    }

    fun pack(rows: Array<FloatArray>): ByteArray {
        val buffer = ByteBuffer.allocate(rows.sumOf { it.size } * 4).order(ByteOrder.LITTLE_ENDIAN)
        for (row in rows) for (v in row) buffer.putFloat(v)
        return buffer.array()
    }

    fun unpack(bytes: ByteArray, dim: Int = DIM): Array<FloatArray> {
        val buffer = ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN).asFloatBuffer()
        return Array(buffer.remaining() / dim) { r -> FloatArray(dim) { buffer.get(r * dim + it) } }
    }

    fun cosine(a: FloatArray, b: FloatArray): Double {
        var dot = 0.0
        var aa = 0.0
        var bb = 0.0
        for (k in a.indices) {
            dot += a[k].toDouble() * b[k]
            aa += a[k].toDouble() * a[k]
            bb += b[k].toDouble() * b[k]
        }
        return if (aa == 0.0 || bb == 0.0) 0.0 else dot / sqrt(aa * bb)
    }
}
