package nz.pebble.robot.ui

import nz.pebble.robot.PebbleConfig
import nz.pebble.robot.llm.ModelFiles
import nz.pebble.robot.llm.TalkBench
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class FaceNoteTest {
    private val now = 1_000_000L

    private fun status(main: JSONObject, want: String = "run", mind: String = "llama", at: Long = now) = JSONObject()
        .put("at", at)
        .put("brain", JSONObject().put("want", want))
        .put("resting", false)
        .put("config", PebbleConfig(mind = mind).toJson())
        .put("models", JSONObject().put("main", main))

    @Test
    fun aMissingModelSaysWhichFileGoesWhere() {
        val text = FaceNote.text(status(JSONObject().put("state", "off").put("kind", ModelFiles.MISSING)), now)!!
        assertTrue(text, text.contains("gemma-4-E4B_q4_0-it.gguf") && text.contains(FaceNote.FOLDER) && text.contains("step 8"))
    }

    @Test
    fun theTalkBenchSaysNothingIsWrong() {
        val bench = JSONObject().put("measuring", "cancel at batch 128").put("step", TalkBench.step("cancel at batch 128")).put("steps", TalkBench.STEPS)
        val text = FaceNote.text(status(JSONObject().put("state", "ready").put("kind", "").put("bench", bench)), now)!!
        assertTrue(text, text.contains("step 2 of 5") && text.contains("10 to 15 minutes") && text.contains("nothing is wrong"))
    }

    @Test
    fun aDamagedFileOutranksTheBench() {
        val bench = JSONObject().put("measuring", "starting").put("step", 1).put("steps", 5)
        val text = FaceNote.text(status(JSONObject().put("state", "loading").put("kind", ModelFiles.BAD_FILE).put("bench", bench)), now)!!
        assertTrue(text, text.contains("damaged or cut short"))
    }

    @Test
    fun loadingTooBigAndRestartingEachHaveTheirOwnWords() {
        assertTrue(FaceNote.text(status(JSONObject().put("state", "loading").put("kind", "")), now)!!.contains("loading"))
        assertTrue(FaceNote.text(status(JSONObject().put("state", "off").put("kind", ModelFiles.TOO_BIG)), now)!!.contains("too big"))
        assertTrue(FaceNote.text(status(JSONObject().put("state", "waiting").put("kind", ModelFiles.STOPPED)), now)!!.contains("starting again"))
        assertTrue(FaceNote.text(status(JSONObject().put("state", "off").put("kind", ModelFiles.COPYING)), now)!!.contains("still being copied"))
    }

    @Test
    fun nothingShowsWhenPebbleCanTalkOrIsMeantToBeQuiet() {
        assertNull(FaceNote.text(status(JSONObject().put("state", "ready").put("kind", "")), now))
        assertNull(FaceNote.text(status(JSONObject().put("state", "busy").put("kind", "")), now))
        assertNull(FaceNote.text(status(JSONObject().put("state", "off").put("kind", ModelFiles.MISSING), want = "pause"), now))
        assertNull(FaceNote.text(status(JSONObject().put("state", "off").put("kind", ModelFiles.MISSING), mind = "scripted"), now))
        assertNull(FaceNote.text(status(JSONObject().put("state", "off").put("kind", ModelFiles.MISSING), at = now - FaceNote.STALE_MS - 1), now))
        assertNull(FaceNote.text(null, now))
    }

    @Test
    fun theBenchStepsCoverEveryPhase() {
        assertEquals(1, TalkBench.step("reading speed at batch 512"))
        assertEquals(2, TalkBench.step("cancel at batch 64"))
        assertEquals(3, TalkBench.step("talking, with the drafter, cool"))
        assertEquals(4, TalkBench.step("talking, without the drafter, hot"))
        assertEquals(5, TalkBench.step("memory"))
        assertEquals(1, TalkBench.step("starting"))
    }
}
