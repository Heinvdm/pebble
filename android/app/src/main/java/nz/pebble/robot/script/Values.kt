package nz.pebble.robot.script

import java.math.BigDecimal
import java.math.BigInteger
import java.math.MathContext
import java.math.RoundingMode

class Tup(val items: List<Any?>)

class PyRange(val start: Long, val stop: Long, val step: Long) {
    val size: Long = when {
        step > 0 && start < stop -> (stop - start - 1) / step + 1
        step < 0 && start > stop -> (start - stop - 1) / (-step) + 1
        else -> 0L
    }

    fun at(index: Long): Long = start + index * step

    fun values(): Iterator<Any?> = object : Iterator<Any?> {
        var index = 0L
        override fun hasNext(): Boolean = index < size
        override fun next(): Any? = at(index++)
    }

    fun has(value: Long): Boolean {
        if (size == 0L) return false
        if (step > 0 && (value < start || value >= stop)) return false
        if (step < 0 && (value > start || value <= stop)) return false
        return (value - start) % step == 0L
    }

    fun sameAs(other: PyRange): Boolean {
        if (size != other.size) return false
        if (size == 0L) return true
        if (start != other.start) return false
        return size == 1L || step == other.step
    }

    fun repr(): String = if (step == 1L) "range($start, $stop)" else "range($start, $stop, $step)"

    fun dataRepr(): String = "Range(start=$start, stop=$stop, step=$step)"
}

class Incomparable : RuntimeException() {
    override fun fillInStackTrace(): Throwable = this
}

object Py {
    const val MAX_INT = 9007199254740991L
    private val TWO_63 = 9.223372036854775807E18

    fun isNum(v: Any?): Boolean = v is Boolean || v is Long || v is Double

    fun isWhole(v: Any?): Boolean = v is Boolean || v is Long

    fun isList(v: Any?): Boolean = v is ArrayList<*>

    fun long(v: Any?): Long = when (v) {
        is Boolean -> if (v) 1L else 0L
        is Long -> v
        else -> throw IllegalArgumentException("not a whole number")
    }

    fun double(v: Any?): Double = when (v) {
        is Boolean -> if (v) 1.0 else 0.0
        is Long -> v.toDouble()
        is Double -> v
        else -> throw IllegalArgumentException("not a number")
    }

    fun truth(v: Any?): Boolean = when (v) {
        null -> false
        is Boolean -> v
        is Long -> v != 0L
        is Double -> v != 0.0
        is String -> v.isNotEmpty()
        is List<*> -> v.isNotEmpty()
        is Tup -> v.items.isNotEmpty()
        is Map<*, *> -> v.isNotEmpty()
        is PyRange -> v.size > 0
        else -> true
    }

    fun kindWords(v: Any?): String = when (v) {
        is PyRange -> "a range"
        is Boolean -> "True or False"
        is Long, is Double -> "a number"
        is String -> "text"
        is ArrayList<*> -> "a list"
        is Tup -> "a tuple"
        is Map<*, *> -> "a dict"
        null -> "None"
        else -> "a value"
    }

    fun length(v: Any?): Long = when (v) {
        is String -> textLength(v).toLong()
        is List<*> -> v.size.toLong()
        is Tup -> v.items.size.toLong()
        is Map<*, *> -> v.size.toLong()
        is PyRange -> v.size
        else -> throw IllegalArgumentException("no length")
    }

    fun textLength(s: String): Int {
        for (c in s) if (Character.isSurrogate(c)) return s.codePointCount(0, s.length)
        return s.length
    }

    fun points(s: String): IntArray = s.codePoints().toArray()

    fun fromPoints(points: IntArray, from: Int = 0, count: Int = points.size - from): String = String(points, from, count)

    fun chars(s: String): List<String> {
        val out = ArrayList<String>(s.length)
        var i = 0
        while (i < s.length) {
            val cp = s.codePointAt(i)
            val n = Character.charCount(cp)
            out.add(s.substring(i, i + n))
            i += n
        }
        return out
    }

    fun cmpNum(a: Any?, b: Any?): Int {
        if (isWhole(a) && isWhole(b)) return long(a).compareTo(long(b))
        if (isWhole(a)) return -cmpDoubleLong(double(b), long(a))
        if (isWhole(b)) return cmpDoubleLong(double(a), long(b))
        val x = double(a)
        val y = double(b)
        return if (x < y) -1 else if (x > y) 1 else 0
    }

    private fun cmpDoubleLong(d: Double, l: Long): Int {
        if (d >= TWO_63) return 1
        if (d < -TWO_63) return -1
        val floor = Math.floor(d)
        val whole = floor.toLong()
        if (whole != l) return whole.compareTo(l)
        return if (d > floor) 1 else 0
    }

    fun cmpText(a: String, b: String): Int {
        var i = 0
        var j = 0
        while (i < a.length && j < b.length) {
            val x = a.codePointAt(i)
            val y = b.codePointAt(j)
            if (x != y) return x.compareTo(y)
            i += Character.charCount(x)
            j += Character.charCount(y)
        }
        if (i >= a.length && j >= b.length) return 0
        return if (i >= a.length) -1 else 1
    }

    fun eq(a: Any?, b: Any?): Boolean {
        if (a === b) return true
        if (isNum(a) && isNum(b)) return cmpNum(a, b) == 0
        if (a == null || b == null) return false
        return when (a) {
            is String -> b is String && a == b
            is ArrayList<*> -> b is ArrayList<*> && sameItems(a, b)
            is Tup -> b is Tup && sameItems(a.items, b.items)
            is Map<*, *> -> {
                if (b !is Map<*, *> || a.size != b.size) return false
                for ((key, value) in a) {
                    if (!b.containsKey(key)) return false
                    if (!eq(value, b[key])) return false
                }
                true
            }
            is PyRange -> b is PyRange && a.sameAs(b)
            else -> a == b
        }
    }

    private fun sameItems(a: List<*>, b: List<*>): Boolean {
        if (a.size != b.size) return false
        for (i in a.indices) if (!eq(a[i], b[i])) return false
        return true
    }

    fun order(a: Any?, b: Any?): Int {
        if (isNum(a) && isNum(b)) return cmpNum(a, b)
        if (a is String && b is String) return cmpText(a, b)
        if (a is ArrayList<*> && b is ArrayList<*>) return orderItems(a, b)
        if (a is Tup && b is Tup) return orderItems(a.items, b.items)
        throw Incomparable()
    }

    private fun orderItems(a: List<*>, b: List<*>): Int {
        val n = minOf(a.size, b.size)
        for (i in 0 until n) {
            if (!eq(a[i], b[i])) return order(a[i], b[i])
        }
        return a.size.compareTo(b.size)
    }

    fun key(v: Any?): Any? = if (v is Boolean) long(v) else v

    fun isSpace(cp: Int): Boolean = when (cp) {
        9, 10, 11, 12, 13, 28, 29, 30, 31, 32, 0x85, 0xA0, 0x1680, 0x2028, 0x2029, 0x202F, 0x205F, 0x3000 -> true
        else -> cp in 0x2000..0x200A
    }

    fun strip(s: String, chars: String?): String {
        val points = points(s)
        val set = chars?.let { points(it).toHashSet() }
        var lo = 0
        var hi = points.size
        val drop = { cp: Int -> if (set == null) isSpace(cp) else cp in set }
        while (lo < hi && drop(points[lo])) lo++
        while (hi > lo && drop(points[hi - 1])) hi--
        return fromPoints(points, lo, hi - lo)
    }

    fun splitSpace(s: String, most: Long): ArrayList<Any?> {
        val points = points(s)
        val out = ArrayList<Any?>()
        var left = if (most < 0) Long.MAX_VALUE else most
        var i = 0
        val n = points.size
        while (left-- > 0) {
            while (i < n && isSpace(points[i])) i++
            if (i == n) break
            val j = i
            i++
            while (i < n && !isSpace(points[i])) i++
            out.add(fromPoints(points, j, i - j))
        }
        if (i < n) {
            while (i < n && isSpace(points[i])) i++
            if (i != n) out.add(fromPoints(points, i, n - i))
        }
        return out
    }

    fun splitOn(s: String, sep: String, most: Long): ArrayList<Any?> {
        val out = ArrayList<Any?>()
        var left = if (most < 0) Long.MAX_VALUE else most
        var i = 0
        while (left-- > 0) {
            val at = s.indexOf(sep, i)
            if (at < 0) break
            out.add(s.substring(i, at))
            i = at + sep.length
        }
        out.add(s.substring(i))
        return out
    }

    fun countText(s: String, sub: String): Long {
        if (sub.isEmpty()) return textLength(s) + 1L
        var count = 0L
        var i = 0
        while (true) {
            val at = s.indexOf(sub, i)
            if (at < 0) return count
            count++
            i = at + sub.length
        }
    }

    fun replace(s: String, old: String, new: String, most: Long): String {
        var left = if (most < 0) Long.MAX_VALUE else most
        if (old.isEmpty()) {
            val out = StringBuilder()
            for (c in chars(s)) {
                if (left > 0) {
                    out.append(new)
                    left--
                }
                out.append(c)
            }
            if (left > 0) out.append(new)
            return out.toString()
        }
        val out = StringBuilder()
        var i = 0
        while (left > 0) {
            val at = s.indexOf(old, i)
            if (at < 0) break
            out.append(s, i, at).append(new)
            i = at + old.length
            left--
        }
        out.append(s, i, s.length)
        return out.toString()
    }

    fun sliceIndices(length: Long, lo: Long?, hi: Long?, step: Long): LongArray {
        var start = lo ?: if (step < 0) Long.MAX_VALUE else 0L
        var stop = hi ?: if (step < 0) Long.MIN_VALUE else Long.MAX_VALUE
        if (start < 0) {
            start += length
            if (start < 0) start = if (step < 0) -1 else 0
        } else if (start >= length) {
            start = if (step < 0) length - 1 else length
        }
        if (stop < 0) {
            stop += length
            if (stop < 0) stop = if (step < 0) -1 else 0
        } else if (stop >= length) {
            stop = if (step < 0) length - 1 else length
        }
        val count = if (step < 0) {
            if (stop < start) (start - stop - 1) / (-step) + 1 else 0
        } else {
            if (start < stop) (stop - start - 1) / step + 1 else 0
        }
        return longArrayOf(start, count)
    }

    fun floatRepr(x: Double): String {
        if (x.isNaN()) return "nan"
        if (x.isInfinite()) return if (x > 0) "inf" else "-inf"
        if (x == 0.0) return if (1.0 / x < 0) "-0.0" else "0.0"
        val sign = if (x < 0) "-" else ""
        val (digits, point) = shortest(Math.abs(x))
        val body = if (point > -4 && point <= 16) {
            when {
                point <= 0 -> "0." + "0".repeat(-point) + digits
                point >= digits.length -> digits + "0".repeat(point - digits.length) + ".0"
                else -> digits.substring(0, point) + "." + digits.substring(point)
            }
        } else {
            val e = point - 1
            val mantissa = if (digits.length > 1) digits[0] + "." + digits.substring(1) else digits
            mantissa + "e" + (if (e < 0) "-" else "+") + String.format("%02d", Math.abs(e))
        }
        return sign + body
    }

    private fun shortest(x: Double): Pair<String, Int> {
        val exact = BigDecimal(x)
        for (precision in 1..17) {
            val context = MathContext(precision, RoundingMode.HALF_EVEN)
            val near = exact.round(context)
            var best: BigDecimal? = if (fits(near, x)) near else null
            if (best == null) {
                for (mode in arrayOf(RoundingMode.DOWN, RoundingMode.UP)) {
                    val other = exact.round(MathContext(precision, mode))
                    if (fits(other, x) && (best == null || other.subtract(exact).abs() < best.subtract(exact).abs())) best = other
                }
            }
            if (best != null) return parts(best)
        }
        return parts(exact.round(MathContext(17, RoundingMode.HALF_EVEN)))
    }

    private fun fits(candidate: BigDecimal, x: Double): Boolean = java.lang.Double.parseDouble(candidate.toString()) == x

    private fun parts(value: BigDecimal): Pair<String, Int> {
        val stripped = value.stripTrailingZeros()
        val digits = stripped.unscaledValue().abs().toString()
        return digits to (digits.length - stripped.scale())
    }

    fun gFormat(v: Any?): String {
        if (v is Long) return v.toString()
        val x = double(v)
        if (x == 0.0) return if (1.0 / x < 0) "-0" else "0"
        val rounded = BigDecimal(Math.abs(x)).round(MathContext(6, RoundingMode.HALF_EVEN))
        val stripped = rounded.stripTrailingZeros()
        val digits = stripped.unscaledValue().toString()
        val point = digits.length - stripped.scale()
        val e = point - 1
        val sign = if (x < 0) "-" else ""
        if (e >= -4 && e < 6) {
            val body = when {
                point <= 0 -> "0." + "0".repeat(-point) + digits
                point >= digits.length -> digits + "0".repeat(point - digits.length)
                else -> digits.substring(0, point) + "." + digits.substring(point)
            }
            return sign + body
        }
        val mantissa = if (digits.length > 1) digits[0] + "." + digits.substring(1) else digits
        return sign + mantissa + "e" + (if (e < 0) "-" else "+") + String.format("%02d", Math.abs(e))
    }

    fun commas(v: Long): String = String.format(java.util.Locale.ROOT, "%,d", v)

    fun textRepr(s: String): String {
        val quote = if (s.contains('\'') && !s.contains('"')) '"' else '\''
        val out = StringBuilder().append(quote)
        var i = 0
        while (i < s.length) {
            val cp = s.codePointAt(i)
            i += Character.charCount(cp)
            when {
                cp == quote.code || cp == '\\'.code -> out.append('\\').appendCodePoint(cp)
                cp == '\t'.code -> out.append("\\t")
                cp == '\n'.code -> out.append("\\n")
                cp == '\r'.code -> out.append("\\r")
                cp < 0x20 || cp == 0x7F -> out.append(String.format("\\x%02x", cp))
                cp < 0x7F -> out.appendCodePoint(cp)
                printable(cp) -> out.appendCodePoint(cp)
                cp <= 0xFF -> out.append(String.format("\\x%02x", cp))
                cp <= 0xFFFF -> out.append(String.format("\\u%04x", cp))
                else -> out.append(String.format("\\U%08x", cp))
            }
        }
        return out.append(quote).toString()
    }

    private fun printable(cp: Int): Boolean = when (Character.getType(cp).toByte()) {
        Character.CONTROL, Character.FORMAT, Character.SURROGATE, Character.PRIVATE_USE, Character.UNASSIGNED, Character.LINE_SEPARATOR, Character.PARAGRAPH_SEPARATOR, Character.SPACE_SEPARATOR -> false
        else -> true
    }

    fun repr(v: Any?): String = when (v) {
        null -> "None"
        is Boolean -> if (v) "True" else "False"
        is Long -> v.toString()
        is BigInteger -> v.toString()
        is Double -> floatRepr(v)
        is String -> textRepr(v)
        is PyRange -> v.dataRepr()
        is ArrayList<*> -> v.joinToString(", ", "[", "]") { repr(it) }
        is Tup -> if (v.items.size == 1) "(" + repr(v.items[0]) + ",)" else v.items.joinToString(", ", "(", ")") { repr(it) }
        is Map<*, *> -> v.entries.joinToString(", ", "{", "}") { repr(it.key) + ": " + repr(it.value) }
        else -> v.toString()
    }

    fun short(v: Any?): String {
        val text = repr(v)
        return if (text.length <= 40) text else text.substring(0, 37) + "..."
    }

    fun parseWhole(text: String): BigInteger? {
        val points = points(text)
        var i = 0
        val n = points.size
        while (i < n && isSpace(points[i])) i++
        var end = n
        while (end > i && isSpace(points[end - 1])) end--
        if (i >= end) return null
        val out = StringBuilder()
        if (points[i] == '+'.code || points[i] == '-'.code) {
            if (points[i] == '-'.code) out.append('-')
            i++
        }
        var digits = 0
        var lastUnderscore = false
        while (i < end) {
            val cp = points[i]
            if (cp == '_'.code) {
                if (digits == 0 || lastUnderscore) return null
                lastUnderscore = true
            } else {
                val d = decimal(cp)
                if (d < 0) return null
                out.append(('0'.code + d).toChar())
                digits++
                lastUnderscore = false
            }
            i++
        }
        if (digits == 0 || lastUnderscore) return null
        return BigInteger(out.toString())
    }

    fun parseFloat(text: String): Double? {
        val points = points(text)
        val ascii = StringBuilder()
        for (cp in points) {
            val d = decimal(cp)
            when {
                d >= 0 -> ascii.append(('0'.code + d).toChar())
                isSpace(cp) -> ascii.append(' ')
                cp < 128 -> ascii.append(cp.toChar())
                else -> return null
            }
        }
        val s = ascii.toString().trim(' ', '\t', '\n', '\u000b', '\u000c', '\r', '\u001c', '\u001d', '\u001e', '\u001f')
        if (!FLOAT.matches(s)) return null
        return java.lang.Double.parseDouble(s.replace("_", ""))
    }

    private val FLOAT = Regex("[+-]?(?:[0-9](?:_?[0-9])*(?:\\.(?:[0-9](?:_?[0-9])*)?)?|\\.[0-9](?:_?[0-9])*)(?:[eE][+-]?[0-9](?:_?[0-9])*)?")

    private fun decimal(cp: Int): Int = if (Character.getType(cp) == Character.DECIMAL_DIGIT_NUMBER.toInt()) Character.digit(cp, 10) else -1

    fun roundTo(x: Double, digits: Int): Double {
        val rounded = java.lang.Double.parseDouble(BigDecimal(x).setScale(digits, RoundingMode.HALF_EVEN).toString())
        return if (rounded == 0.0) Math.copySign(0.0, x) else rounded
    }

    fun roundWhole(x: Long, digits: Int): Long = if (digits >= 0) x else BigDecimal(x).setScale(digits, RoundingMode.HALF_EVEN).toBigIntegerExact().toLong()

    fun floatFloorDiv(a: Double, b: Double): Double {
        var mod = a % b
        var div = (a - mod) / b
        if (mod != 0.0) {
            if ((b < 0) != (mod < 0)) {
                mod += b
                div -= 1.0
            }
        }
        return if (div != 0.0) {
            var floor = Math.floor(div)
            if (div - floor > 0.5) floor += 1.0
            floor
        } else {
            Math.copySign(0.0, a / b)
        }
    }

    fun floatMod(a: Double, b: Double): Double {
        var mod = a % b
        if (mod != 0.0) {
            if ((b < 0) != (mod < 0)) mod += b
        } else {
            mod = Math.copySign(0.0, b)
        }
        return mod
    }
}
