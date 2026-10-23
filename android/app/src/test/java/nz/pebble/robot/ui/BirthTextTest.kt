package nz.pebble.robot.ui

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class BirthTextTest {
    private val drawn = JSONObject(
        """{"setup": true, "born": null, "draw": 3, "line": "I think I'm very playful and an early bird, and I like my blanket and round things.",
        "traits": {"playful": 8, "curious": 7, "chatty": 3, "cautious": 5, "affectionate": 5},
        "usual": {"playful": 6, "curious": 8, "chatty": 3, "cautious": 5, "affectionate": 7},
        "values": {"tidiness": 5, "curiosity": 8, "caution": 4}, "tastes": ["my blanket", "round things"], "passphrase_set": false}""",
    )

    @Test
    fun theDrawReadsAsItsLineThenItsTraits() {
        val text = BirthText.describe(drawn)
        val lines = text.split("\n")
        assertEquals("I think I'm very playful and an early bird, and I like my blanket and round things.", lines[0])
        assertEquals("Draw 3. Traits: affectionate 5 (usually 7), cautious 5, chatty 3, curious 7 (usually 8), playful 8 (usually 6).", lines[1])
        assertEquals("Free values: caution 4, curiosity 8, tidiness 5.", lines[2])
        assertEquals("First tastes: my blanket and round things.", lines[3])
        assertEquals(4, lines.size)
    }

    @Test
    fun aNewDrawIsOfferedOnlyWhileSetupIsOnAndPebbleIsNotBorn() {
        assertTrue(BirthText.offered(drawn))
        assertFalse(BirthText.offered(JSONObject(drawn.toString()).put("setup", false)))
        assertFalse(BirthText.offered(JSONObject(drawn.toString()).put("born", "2026-10-20")))
        assertFalse(BirthText.offered(null))
    }

    @Test
    fun aBornPebbleSaysTheDrawIsItsOwn() {
        val born = JSONObject(drawn.toString()).put("setup", false).put("born", "2026-10-20")
        assertTrue(BirthText.describe(born).endsWith("Born on 2026-10-20; this draw is its own now."))
        assertEquals("Pebble's birth draw could not be read.", BirthText.describe(null))
    }
}
