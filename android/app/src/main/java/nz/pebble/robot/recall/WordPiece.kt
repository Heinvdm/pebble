package nz.pebble.robot.recall

import java.text.Normalizer

class WordPiece(private val vocab: Map<String, Int>) {
    val unk: Int = vocab.getValue("[UNK]")
    val cls: Int = vocab.getValue("[CLS]")
    val sep: Int = vocab.getValue("[SEP]")
    val size: Int get() = vocab.size

    fun basic(text: String): List<String> {
        val cleaned = StringBuilder(text.length + 8)
        var i = 0
        while (i < text.length) {
            val code = text.codePointAt(i)
            i += Character.charCount(code)
            if (code == 0 || code == 0xFFFD || (other(code) && code != TAB && code != NEWLINE && code != RETURN)) continue
            when {
                cjk(code) -> cleaned.append(' ').appendCodePoint(code).append(' ')
                space(code) -> cleaned.append(' ')
                else -> cleaned.appendCodePoint(code)
            }
        }
        val decomposed = Normalizer.normalize(lower(cleaned.toString()), Normalizer.Form.NFD)
        val stripped = StringBuilder(decomposed.length)
        i = 0
        while (i < decomposed.length) {
            val code = decomposed.codePointAt(i)
            i += Character.charCount(code)
            if (Character.getType(code) != Character.NON_SPACING_MARK.toInt()) stripped.appendCodePoint(code)
        }
        val tokens = ArrayList<String>()
        val current = StringBuilder()
        fun flush() {
            if (current.isNotEmpty()) {
                tokens += current.toString()
                current.setLength(0)
            }
        }
        i = 0
        while (i < stripped.length) {
            val code = stripped.codePointAt(i)
            i += Character.charCount(code)
            when {
                space(code) -> flush()
                punctuation(code) -> {
                    flush()
                    tokens += String(Character.toChars(code))
                }
                else -> current.appendCodePoint(code)
            }
        }
        flush()
        return tokens
    }

    fun pieces(word: String): List<Int> {
        val codes = word.codePoints().toArray()
        if (codes.size > LONGEST_WORD) return listOf(unk)
        val out = ArrayList<Int>()
        var start = 0
        while (start < codes.size) {
            var end = codes.size
            var found = -1
            while (start < end) {
                val part = String(codes, start, end - start)
                val id = vocab[if (start == 0) part else "##$part"]
                if (id != null) {
                    found = id
                    break
                }
                end--
            }
            if (found < 0) return listOf(unk)
            out += found
            start = end
        }
        return out
    }

    fun ids(text: String, longest: Int = MAX_TOKENS): IntArray {
        val out = ArrayList<Int>()
        for (word in basic(text)) out.addAll(pieces(word))
        val kept = out.take(maxOf(0, longest - 2))
        val ids = IntArray(kept.size + 2)
        ids[0] = cls
        for ((n, id) in kept.withIndex()) ids[n + 1] = id
        ids[ids.size - 1] = sep
        return ids
    }

    companion object {
        const val MAX_TOKENS = 128
        const val LONGEST_WORD = 100
        private const val TAB = 9
        private const val NEWLINE = 10
        private const val RETURN = 13
        private val IGNORABLE = setOf(0x27, 0x2E, 0x3A, 0xB7, 0x387, 0x55F, 0x5F4, 0x2018, 0x2019, 0x2024, 0x2027, 0xFE13, 0xFE52, 0xFE55, 0xFF07, 0xFF0E, 0xFF1A)
        private val BREAKS = setOf(0x0A, 0x0B, 0x0C, 0x0D, 0x1C, 0x1D, 0x1E, 0x85, 0x2028, 0x2029)

        fun load(text: String): WordPiece {
            val vocab = HashMap<String, Int>(40_000)
            for ((index, line) in lines(text).withIndex()) {
                if (line.isNotEmpty() && line !in vocab) vocab[line] = index
            }
            return WordPiece(vocab)
        }

        fun lines(text: String): List<String> {
            val out = ArrayList<String>()
            var start = 0
            var i = 0
            while (i < text.length) {
                val c = text[i].code
                if (c in BREAKS) {
                    out += text.substring(start, i)
                    i += if (c == 0x0D && i + 1 < text.length && text[i + 1].code == 0x0A) 2 else 1
                    start = i
                } else {
                    i++
                }
            }
            if (start < text.length) out += text.substring(start)
            return out
        }

        fun other(code: Int): Boolean = when (Character.getType(code).toByte()) {
            Character.CONTROL, Character.FORMAT, Character.SURROGATE, Character.PRIVATE_USE, Character.UNASSIGNED -> true
            else -> false
        }

        fun space(code: Int): Boolean {
            if (Character.getType(code) == Character.SPACE_SEPARATOR.toInt()) return true
            return when (Character.getDirectionality(code)) {
                Character.DIRECTIONALITY_WHITESPACE, Character.DIRECTIONALITY_PARAGRAPH_SEPARATOR, Character.DIRECTIONALITY_SEGMENT_SEPARATOR -> true
                else -> false
            }
        }

        fun cjk(code: Int): Boolean =
            code in 0x4E00..0x9FFF || code in 0x3400..0x4DBF || code in 0x20000..0x2A6DF || code in 0xF900..0xFAFF || code in 0x2F800..0x2FA1F

        fun punctuation(code: Int): Boolean {
            if (code in 33..47 || code in 58..64 || code in 91..96 || code in 123..126) return true
            return when (Character.getType(code).toByte()) {
                Character.CONNECTOR_PUNCTUATION, Character.DASH_PUNCTUATION, Character.START_PUNCTUATION, Character.END_PUNCTUATION,
                Character.INITIAL_QUOTE_PUNCTUATION, Character.FINAL_QUOTE_PUNCTUATION, Character.OTHER_PUNCTUATION -> true
                else -> false
            }
        }

        fun lower(text: String): String {
            val codes = text.codePoints().toArray()
            val out = StringBuilder(text.length)
            for ((n, code) in codes.withIndex()) {
                when (code) {
                    0x130 -> out.append('i').append('̇')
                    0x3A3 -> out.appendCodePoint(if (finalSigma(codes, n)) 0x3C2 else 0x3C3)
                    else -> out.appendCodePoint(Character.toLowerCase(code))
                }
            }
            return out.toString()
        }

        private fun cased(code: Int): Boolean = Character.isLowerCase(code) || Character.isUpperCase(code) || Character.isTitleCase(code)

        private fun ignorable(code: Int): Boolean = code in IGNORABLE || when (Character.getType(code).toByte()) {
            Character.NON_SPACING_MARK, Character.ENCLOSING_MARK, Character.FORMAT, Character.MODIFIER_LETTER, Character.MODIFIER_SYMBOL -> true
            else -> false
        }

        private fun finalSigma(codes: IntArray, at: Int): Boolean {
            var j = at - 1
            while (j >= 0 && ignorable(codes[j])) j--
            if (j < 0 || !cased(codes[j])) return false
            j = at + 1
            while (j < codes.size && ignorable(codes[j])) j++
            return j == codes.size || !cased(codes[j])
        }
    }
}
