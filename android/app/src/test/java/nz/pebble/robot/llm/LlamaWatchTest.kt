package nz.pebble.robot.llm

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class LlamaWatchTest {
    private fun slot(processing: Boolean, decoded: Int?): String {
        val next = if (decoded == null) "" else ", \"next_token\": [{\"has_next_token\": true, \"n_remain\": -1, \"n_decoded\": $decoded}]"
        return "{\"id\": 0, \"n_ctx\": 8192, \"speculative\": false, \"is_processing\": $processing$next}"
    }

    @Test
    fun onlyASlotThatHasWrittenATokenCountsAsWriting() {
        assertFalse(LlamaHttp.writing("[${slot(false, null)}]"))
        assertFalse(LlamaHttp.writing("[${slot(false, 12)}]"))
        assertFalse(LlamaHttp.writing("[${slot(true, 0)}]"))
        assertTrue(LlamaHttp.writing("[${slot(true, 1)}]"))
        assertTrue(LlamaHttp.writing("[${slot(false, 0)}, ${slot(true, 5)}]"))
        assertFalse(LlamaHttp.writing("{\"error\": \"no slots\"}"))
        assertFalse(LlamaHttp.writing(""))
    }

    @Test
    fun anyServerWritingCountsAndASilentServerDoesNot() {
        val answers = mutableMapOf<Int, String?>(8080 to "[${slot(false, 3)}]", 8081 to null, 8090 to "[${slot(true, 0)}]")
        var asked = 0
        val watch = LlamaWatch(listOf(8080, 8081, 8090), 400, 0L) { port, _ ->
            asked++
            answers[port]
        }
        assertFalse(watch.writing())
        assertEquals(3, asked)
        answers[8081] = "[${slot(true, 2)}]"
        assertTrue(watch.writing())
    }

    @Test
    fun aFreshAnswerIsReusedForAMoment() {
        var asked = 0
        val watch = LlamaWatch(listOf(8080), 400, 60_000L) { _, _ ->
            asked++
            "[${slot(true, 4)}]"
        }
        assertTrue(watch.writing())
        assertTrue(watch.writing())
        assertEquals(1, asked)
        assertEquals(1L, watch.checks)
    }
}
