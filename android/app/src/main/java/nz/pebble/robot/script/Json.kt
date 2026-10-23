package nz.pebble.robot.script

import java.math.BigInteger

class JsonError(message: String) : Exception(message)

object Json {
    fun parse(text: String): Any? {
        val reader = Reader(text)
        reader.space()
        val value = reader.value()
        reader.space()
        if (reader.at < text.length) throw JsonError("extra data at ${reader.at}")
        return value
    }

    fun write(value: Any?): String {
        val out = StringBuilder()
        put(out, value)
        return out.toString()
    }

    fun put(out: StringBuilder, value: Any?) {
        when (value) {
            null -> out.append("null")
            is Boolean -> out.append(if (value) "true" else "false")
            is Long -> out.append(value)
            is Int -> out.append(value)
            is BigInteger -> out.append(value.toString())
            is Double -> {
                if (!value.isFinite()) throw JsonError("a number that JSON can't hold")
                out.append(Py.floatRepr(value))
            }
            is String -> text(out, value)
            is List<*> -> {
                out.append('[')
                value.forEachIndexed { index, item ->
                    if (index > 0) out.append(',')
                    put(out, item)
                }
                out.append(']')
            }
            is Tup -> put(out, value.items)
            is Map<*, *> -> {
                out.append('{')
                var first = true
                for ((key, item) in value) {
                    if (!first) out.append(',')
                    first = false
                    text(out, keyText(key))
                    out.append(':')
                    put(out, item)
                }
                out.append('}')
            }
            is PyRange -> text(out, value.dataRepr())
            else -> text(out, value.toString())
        }
    }

    private fun keyText(key: Any?): String = when (key) {
        is String -> key
        null -> "null"
        is Boolean -> if (key) "true" else "false"
        is Double -> Py.floatRepr(key)
        else -> key.toString()
    }

    private fun text(out: StringBuilder, value: String) {
        out.append('"')
        for (c in value) {
            when (c) {
                '"' -> out.append("\\\"")
                '\\' -> out.append("\\\\")
                '\n' -> out.append("\\n")
                '\r' -> out.append("\\r")
                '\t' -> out.append("\\t")
                '\b' -> out.append("\\b")
                '\u000c' -> out.append("\\f")
                else -> if (c < ' ') out.append("\\u").append(String.format("%04x", c.code)) else out.append(c)
            }
        }
        out.append('"')
    }

    private class Reader(val text: String) {
        var at = 0

        fun space() {
            while (at < text.length && (text[at] == ' ' || text[at] == '\t' || text[at] == '\n' || text[at] == '\r')) at++
        }

        fun value(): Any? {
            if (at >= text.length) throw JsonError("nothing to read")
            return when (val c = text[at]) {
                '{' -> obj()
                '[' -> list()
                '"' -> string()
                't' -> word("true", true)
                'f' -> word("false", false)
                'n' -> word("null", null)
                else -> if (c == '-' || c in '0'..'9') number() else throw JsonError("unexpected ${c} at $at")
            }
        }

        private fun word(word: String, value: Any?): Any? {
            if (!text.startsWith(word, at)) throw JsonError("unexpected word at $at")
            at += word.length
            return value
        }

        private fun obj(): LinkedHashMap<Any, Any?> {
            val out = LinkedHashMap<Any, Any?>()
            at++
            space()
            if (at < text.length && text[at] == '}') {
                at++
                return out
            }
            while (true) {
                space()
                if (at >= text.length || text[at] != '"') throw JsonError("expected a key at $at")
                val key = string()
                space()
                if (at >= text.length || text[at] != ':') throw JsonError("expected : at $at")
                at++
                space()
                out[key] = value()
                space()
                if (at >= text.length) throw JsonError("unfinished object")
                when (text[at]) {
                    ',' -> at++
                    '}' -> {
                        at++
                        return out
                    }
                    else -> throw JsonError("expected , or } at $at")
                }
            }
        }

        private fun list(): ArrayList<Any?> {
            val out = ArrayList<Any?>()
            at++
            space()
            if (at < text.length && text[at] == ']') {
                at++
                return out
            }
            while (true) {
                space()
                out.add(value())
                space()
                if (at >= text.length) throw JsonError("unfinished list")
                when (text[at]) {
                    ',' -> at++
                    ']' -> {
                        at++
                        return out
                    }
                    else -> throw JsonError("expected , or ] at $at")
                }
            }
        }

        private fun string(): String {
            at++
            val out = StringBuilder()
            while (true) {
                if (at >= text.length) throw JsonError("unfinished text")
                val c = text[at++]
                when {
                    c == '"' -> return out.toString()
                    c == '\\' -> {
                        if (at >= text.length) throw JsonError("unfinished escape")
                        when (val e = text[at++]) {
                            '"' -> out.append('"')
                            '\\' -> out.append('\\')
                            '/' -> out.append('/')
                            'b' -> out.append('\b')
                            'f' -> out.append('\u000c')
                            'n' -> out.append('\n')
                            'r' -> out.append('\r')
                            't' -> out.append('\t')
                            'u' -> {
                                if (at + 4 > text.length) throw JsonError("short \\u escape")
                                val hex = text.substring(at, at + 4)
                                if (!hex.all { it in '0'..'9' || it in 'a'..'f' || it in 'A'..'F' }) throw JsonError("bad \\u escape")
                                out.append(hex.toInt(16).toChar())
                                at += 4
                            }
                            else -> throw JsonError("bad escape \\$e")
                        }
                    }
                    c < ' ' -> throw JsonError("a control character in text")
                    else -> out.append(c)
                }
            }
        }

        private fun number(): Any {
            val start = at
            if (text[at] == '-') at++
            if (at >= text.length) throw JsonError("bad number")
            if (text[at] == '0') {
                at++
            } else if (text[at] in '1'..'9') {
                while (at < text.length && text[at] in '0'..'9') at++
            } else {
                throw JsonError("bad number")
            }
            var whole = true
            if (at < text.length && text[at] == '.' && at + 1 < text.length && text[at + 1] in '0'..'9') {
                whole = false
                at++
                while (at < text.length && text[at] in '0'..'9') at++
            }
            if (at < text.length && (text[at] == 'e' || text[at] == 'E')) {
                var probe = at + 1
                if (probe < text.length && (text[probe] == '+' || text[probe] == '-')) probe++
                if (probe < text.length && text[probe] in '0'..'9') {
                    whole = false
                    at = probe
                    while (at < text.length && text[at] in '0'..'9') at++
                }
            }
            val literal = text.substring(start, at)
            if (!whole) return literal.toDouble()
            return literal.toLongOrNull() ?: BigInteger(literal)
        }
    }
}
