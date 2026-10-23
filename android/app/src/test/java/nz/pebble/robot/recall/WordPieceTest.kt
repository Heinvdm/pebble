package nz.pebble.robot.recall

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

class WordPieceTest {
    private fun cases(): JSONObject = JSONObject(String(javaClass.getResourceAsStream("/recall/cases.json")!!.readBytes(), Charsets.UTF_8))

    private fun vocab(): File {
        val path = System.getProperty("pebble.recallVocab") ?: error("the build passes the word list's path as pebble.recallVocab")
        return File(path).also { assertTrue("the sentence model's word list is fetched by the build: $it", it.exists()) }
    }

    @Test
    fun theWordPiecesMatchThePcTokenizer() {
        val pieces = WordPiece.load(vocab().readText(Charsets.UTF_8))
        assertEquals(30_522, pieces.size)
        val fixture = cases()
        val prefix = fixture.getString("prefix")
        val tokens = fixture.getJSONArray("tokens")
        assertTrue(tokens.length() >= 40)
        val wrong = ArrayList<String>()
        for (i in 0 until tokens.length()) {
            val case = tokens.getJSONObject(i)
            val text = case.getString("text")
            val want = case.getJSONArray("ids").let { a -> IntArray(a.length()) { a.getInt(it) } }
            val got = pieces.ids(if (case.getBoolean("query")) prefix + text else text)
            if (!want.contentEquals(got)) wrong += "${JSONObject.quote(text)}: want ${want.toList()}, got ${got.toList()}"
        }
        assertTrue(wrong.joinToString("\n"), wrong.isEmpty())
    }

    @Test
    fun theFirstLineSplitsTheWayThePcSplitsIt() {
        val pieces = WordPiece.load(vocab().readText(Charsets.UTF_8))
        assertEquals(listOf("hello", ",", "pebble", "!", "cafe", "?"), pieces.basic("Hello, Pebble! Café?"))
        assertArrayEquals(intArrayOf(101, 7592, 1010, 21877, 11362, 999, 7668, 1029, 102), pieces.ids("Hello, Pebble! Café?"))
    }

    @Test
    fun aSmallWordListGivesThePcTestsIds() {
        val pieces = WordPiece.load(listOf("[PAD]", "[UNK]", "[CLS]", "[SEP]", "[MASK]", "hello", ",", "peb", "##ble", "!", "cafe").joinToString("\n"))
        assertArrayEquals(intArrayOf(2, 5, 6, 7, 8, 9, 10, 1, 3), pieces.ids("Hello, Pebble! Café?"))
        assertEquals(16, pieces.ids("hello ".repeat(400), 16).size)
        assertEquals(128, pieces.ids("hello ".repeat(400)).size)
        assertArrayEquals(intArrayOf(2, 3), pieces.ids(""))
        assertArrayEquals(intArrayOf(2, 1, 3), pieces.ids("x".repeat(101)))
    }

    @Test
    fun theWordListIsReadLineByLineAsPythonReadsIt() {
        assertEquals(listOf("a", "b", "c", "d", "e"), WordPiece.lines("a\nb\r\nc\rd e\n"))
        assertEquals(listOf("x", "", "y"), WordPiece.lines("x\n\ny"))
        assertEquals(emptyList<String>(), WordPiece.lines(""))
        val pieces = WordPiece.load("[PAD]\n\n[UNK]\n[CLS]\n[SEP]\nhello\nhello\n")
        assertArrayEquals(intArrayOf(3, 5, 4), pieces.ids("hello"))
    }

    @Test
    fun capitalSigmaEndsAWordOnlyAfterALetter() {
        assertEquals("οδος", WordPiece.lower("ΟΔΟΣ"))
        assertEquals("σ", WordPiece.lower("Σ"))
        assertEquals("σας", WordPiece.lower("ΣΑΣ"))
        assertEquals("ασ'β", WordPiece.lower("ΑΣ'Β"))
        assertEquals("ας'", WordPiece.lower("ΑΣ'"))
        assertEquals("i̇stanbul", WordPiece.lower("İstanbul"))
    }

    @Test
    fun theFixtureHoldsThePcVectorsForEveryGroup() {
        val fixture = cases()
        val dim = fixture.getInt("dim")
        val groups = fixture.getJSONArray("groups")
        assertTrue(groups.length() >= 10)
        for (i in 0 until groups.length()) {
            val group = groups.getJSONObject(i)
            val texts: JSONArray = group.getJSONArray("texts")
            val rows = Pooling.unpack(java.util.Base64.getDecoder().decode(group.getString("vectors")), dim)
            assertEquals(texts.length(), rows.size)
            for (row in rows) {
                val length = Math.sqrt(row.sumOf { it.toDouble() * it })
                assertEquals(1.0, length, 1e-4)
            }
        }
    }
}
