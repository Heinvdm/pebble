package nz.pebble.robot.llm

import java.io.BufferedInputStream
import java.io.EOFException
import java.io.File
import java.io.InputStream

object Gguf {
    private const val MAGIC = 0x46554747L
    private const val MAX_KEYS = 100_000L
    private const val MAX_STRING = 1L shl 20
    private const val MAX_ARRAY = 4096L
    private const val MAX_SKIP = 1L shl 32
    const val MAX_LAYERS = 1024

    fun meta(file: File): Map<String, Any> = BufferedInputStream(file.inputStream(), 1 shl 16).use { read(it) }

    fun read(input: InputStream): Map<String, Any> {
        val reader = Reader(input)
        if (reader.u32() != MAGIC) throw IllegalArgumentException("not a GGUF file")
        val version = reader.u32()
        if (version < 2) throw IllegalArgumentException("GGUF version $version is too old")
        reader.u64()
        val count = reader.u64()
        if (count < 0 || count > MAX_KEYS) throw IllegalArgumentException("bad GGUF key count $count")
        val out = HashMap<String, Any>()
        for (index in 0L until count) {
            val key = reader.string()
            val value = reader.value(reader.u32().toInt())
            if (value != null) out[key] = value
        }
        return out
    }

    private class Reader(private val input: InputStream) {
        private val buffer = ByteArray(8)

        private fun fill(bytes: ByteArray, count: Int) {
            var at = 0
            while (at < count) {
                val got = input.read(bytes, at, count - at)
                if (got < 0) throw EOFException("the GGUF header ends early")
                at += got
            }
        }

        private fun little(count: Int): Long {
            fill(buffer, count)
            var value = 0L
            for (index in count - 1 downTo 0) value = (value shl 8) or (buffer[index].toLong() and 0xFF)
            return value
        }

        fun u32(): Long = little(4)

        fun u64(): Long = little(8)

        private fun skip(count: Long) {
            var left = count
            while (left > 0) {
                val done = input.skip(left)
                if (done > 0) {
                    left -= done
                } else {
                    if (input.read() < 0) throw EOFException("the GGUF header ends early")
                    left--
                }
            }
        }

        fun string(): String {
            val length = u64()
            if (length < 0 || length > MAX_STRING) throw IllegalArgumentException("bad GGUF string length $length")
            val bytes = ByteArray(length.toInt())
            fill(bytes, bytes.size)
            return String(bytes, Charsets.UTF_8)
        }

        private fun width(type: Int): Int = when (type) {
            0, 1, 7 -> 1
            2, 3 -> 2
            4, 5, 6 -> 4
            10, 11, 12 -> 8
            else -> throw IllegalArgumentException("unknown GGUF value type $type")
        }

        private fun scalar(type: Int): Any = when (type) {
            0 -> little(1)
            1 -> little(1).toByte().toLong()
            2 -> little(2)
            3 -> little(2).toShort().toLong()
            4 -> little(4)
            5 -> little(4).toInt().toLong()
            6 -> java.lang.Float.intBitsToFloat(little(4).toInt()).toDouble()
            7 -> little(1) != 0L
            10, 11 -> little(8)
            12 -> java.lang.Double.longBitsToDouble(little(8))
            else -> throw IllegalArgumentException("unknown GGUF value type $type")
        }

        fun value(type: Int): Any? = when (type) {
            8 -> string()
            9 -> array()
            else -> scalar(type)
        }

        private fun array(): Any? {
            val type = u32().toInt()
            val count = u64()
            if (count < 0 || count > MAX_SKIP) throw IllegalArgumentException("bad GGUF array length $count")
            if (type == 8) {
                for (index in 0L until count) {
                    val length = u64()
                    if (length < 0 || length > MAX_STRING) throw IllegalArgumentException("bad GGUF string length $length")
                    skip(length)
                }
                return null
            }
            if (type == 9) throw IllegalArgumentException("nested GGUF arrays are not read")
            val each = width(type)
            if (count > MAX_ARRAY) {
                skip(count * each)
                return null
            }
            return (0L until count).map { scalar(type) }
        }
    }
}

data class KvCost(val fullPerToken: Long, val swaPerToken: Long, val window: Int) {
    fun cache(context: Int, swaFull: Boolean, type: String, ubatch: Int = UBATCH): Long {
        val swaCells = if (window <= 0 || swaFull) context.toLong() else swaCells(context, ubatch)
        return ((fullPerToken * context + swaPerToken * swaCells) * bytes(type)).toLong()
    }

    fun checkpoints(context: Int, swaFull: Boolean, type: String, count: Int, ubatch: Int = UBATCH): Long {
        if (swaFull || window <= 0 || swaPerToken == 0L) return 0L
        return (swaPerToken * swaCells(context, ubatch) * bytes(type) * count).toLong()
    }

    private fun swaCells(context: Int, ubatch: Int): Long {
        val cells = minOf(context.toLong(), window.toLong() + ubatch)
        return (cells + 255) / 256 * 256
    }

    companion object {
        const val F16 = "f16"
        const val Q8 = "q8_0"
        const val UBATCH = LlamaPlan.BATCH

        fun bytes(type: String): Double = when (type) {
            Q8 -> 34.0 / 32.0
            "f32" -> 4.0
            else -> 2.0
        }

        fun of(meta: Map<String, Any>): KvCost? {
            val arch = meta["general.architecture"] as? String ?: return null
            fun number(key: String): Long? = (meta["$arch.$key"] as? Number)?.toLong()
            fun perLayer(key: String, layers: Int): List<Long>? = when (val value = meta["$arch.$key"]) {
                is Number -> List(layers) { value.toLong() }
                is List<*> -> value.map { (it as? Number)?.toLong() ?: 0L }.takeIf { it.size >= layers }
                else -> null
            }
            val layers = number("block_count")?.takeIf { it in 1..Gguf.MAX_LAYERS.toLong() }?.toInt() ?: return null
            val heads = perLayer("attention.head_count", layers) ?: return null
            val kvHeads = perLayer("attention.head_count_kv", layers) ?: heads
            val embedding = number("embedding_length") ?: return null
            val firstHeads = heads.firstOrNull { it > 0 } ?: return null
            val key = number("attention.key_length") ?: (embedding / firstHeads)
            val value = number("attention.value_length") ?: key
            val keySwa = number("attention.key_length_swa") ?: key
            val valueSwa = number("attention.value_length_swa") ?: value
            val window = number("attention.sliding_window")?.toInt() ?: 0
            val shared = number("attention.shared_kv_layers")?.toInt() ?: 0
            val pattern = meta["$arch.attention.sliding_window_pattern"]
            fun sliding(layer: Int): Boolean = window > 0 && when (pattern) {
                is List<*> -> pattern.getOrNull(layer) == true
                is Number -> pattern.toInt().let { every -> every <= 0 || layer % every < every - 1 }
                else -> true
            }
            var full = 0L
            var swa = 0L
            for (layer in 0 until (layers - shared).coerceIn(0, layers)) {
                if (sliding(layer)) swa += kvHeads[layer] * (keySwa + valueSwa) else full += kvHeads[layer] * (key + value)
            }
            return KvCost(full, swa, window)
        }

        fun read(file: File): KvCost? = try {
            of(Gguf.meta(file))
        } catch (e: Throwable) {
            null
        }
    }
}
