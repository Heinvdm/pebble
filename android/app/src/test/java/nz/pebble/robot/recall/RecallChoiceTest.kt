package nz.pebble.robot.recall

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File

class RecallChoiceTest {
    @get:Rule
    val folder = TemporaryFolder()

    @Test
    fun aSlowQuestionOrASlowBatchFallsBackToTheStandIn() {
        assertEquals(RecallChoice.ONNX, RecallChoice.decide(JSONObject().put("query_ms", 60.0).put("per_note_ms", 30.0)).first)
        assertEquals(RecallChoice.ONNX, RecallChoice.decide(JSONObject().put("query_ms", 500.0).put("per_note_ms", 250.0)).first)
        val slowQuestion = RecallChoice.decide(JSONObject().put("query_ms", 620.0).put("per_note_ms", 30.0))
        assertEquals(RecallChoice.STAND_IN, slowQuestion.first)
        assertTrue(slowQuestion.second, slowQuestion.second.contains("620"))
        assertEquals(RecallChoice.STAND_IN, RecallChoice.decide(JSONObject().put("query_ms", 60.0).put("per_note_ms", 251.0)).first)
        assertEquals(RecallChoice.STAND_IN, RecallChoice.decide(JSONObject()).first)
    }

    @Test
    fun theChoiceIsKeptForThisPhoneAndModelOnly() {
        val file = File(folder.root, RecallChoice.NAME)
        val choice = RecallChoice(file)
        assertNull(choice.read("1/Pixel 6 Pro/arm64-v8a/22972992/2"))
        val bench = JSONObject().put("query_ms", 55.5).put("per_note_ms", 21.0).put("core", 2).put("batch", 32)
        assertTrue(choice.keep("1/Pixel 6 Pro/arm64-v8a/22972992/2", RecallChoice.ONNX, "fast enough", bench))
        val saved = choice.read("1/Pixel 6 Pro/arm64-v8a/22972992/2")!!
        assertEquals(RecallChoice.ONNX, saved.rung)
        assertEquals("fast enough", saved.why)
        assertEquals(55.5, saved.bench!!.getDouble("query_ms"), 0.0)
        assertNull(choice.read("2/Pixel 6 Pro/arm64-v8a/22972992/2"))
        choice.keep("k", RecallChoice.UNMEASURED, "", null)
        assertNull(choice.read("k"))
        choice.forget()
        assertNull(choice.read("1/Pixel 6 Pro/arm64-v8a/22972992/2"))
    }

    @Test
    fun theAdminScreenSaysWhatMemorySearchUses() {
        assertTrue(RecallChoice.describe(null).startsWith("not measured yet"))
        val onnx = JSONObject().put("rung", RecallChoice.ONNX).put("bench", JSONObject().put("query_ms", 55.5).put("per_note_ms", 21.2).put("core", 2).put("batch", 32))
        assertEquals("the sentence model on core 2: a question about 56 ms, a memory about 21 ms in a batch of 32", RecallChoice.describe(onnx))
        val slow = JSONObject().put("rung", RecallChoice.STAND_IN).put("why", "a question took 620 ms (more than 500)")
        assertEquals("the simple stand-in, because a question took 620 ms (more than 500)", RecallChoice.describe(slow))
    }
}
