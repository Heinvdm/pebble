package nz.pebble.robot.brain

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class EarsRelayTest {
    private fun chunk(value: Short, n: Int = 320) = ShortArray(n) { value }

    private fun event(kind: String, segment: Int, t: Double, extra: JSONObject.() -> Unit = {}) = JSONObject().put("kind", kind).put("segment", segment).put("t", t).apply(extra)

    @Test
    fun heldSoundKeepsOnlyTheLastSeconds() {
        val held = HeldSound(keepS = 1.0)
        for (i in 0 until 100) held.add(chunk(i.toShort()), 320, (i + 1) * 0.02, false)
        assertEquals(1.0, held.heldS, 0.021)
        assertEquals(2.0 - 1.0, held.oldest, 0.021)
    }

    @Test
    fun heldSoundComesBackInOrderInHalfSecondPiecesSplitWherePebbleSpeaks() {
        val held = HeldSound(keepS = 10.0)
        for (i in 0 until 100) held.add(chunk(i.toShort()), 320, (i + 1) * 0.02, i in 40 until 50)
        val pieces = held.since(0.51)
        val samples = pieces.sumOf { it.pcm.size }
        assertEquals(75 * 320, samples)
        assertTrue(pieces.all { it.pcm.size <= 8_000 })
        val values = pieces.flatMap { p -> p.pcm.toList().chunked(320).map { it.first() } }
        assertEquals((25 until 100).map { it.toShort() }, values)
        assertTrue(pieces.zipWithNext().all { (a, b) -> a.at < b.at })
        val spoken = pieces.filter { it.speaking }
        assertEquals(10 * 320, spoken.sumOf { it.pcm.size })
        assertEquals(1.0, spoken.single().at, 1e-9)
        assertEquals(2.0, pieces.last().at, 1e-9)
    }

    @Test
    fun heldSoundKeepsOnlyTheSamplesItWasGiven() {
        val held = HeldSound(keepS = 10.0)
        held.add(chunk(7, 500), 200, 0.1, false)
        val pieces = held.since(Double.NEGATIVE_INFINITY)
        assertEquals(200, pieces.single().pcm.size)
        assertTrue(held.since(0.1).isEmpty())
    }

    @Test
    fun segmentsKeepCountingAcrossARestart() {
        val relay = SegmentRelay()
        assertEquals(1, relay.pass(event("voice_start", 1, 1.0)).getInt("segment"))
        relay.pass(event("voice_end", 1, 2.0))
        assertEquals(2, relay.pass(event("keyword", 2, 2.5)).getInt("segment"))
        relay.restarted()
        assertEquals(3, relay.pass(event("voice_start", 1, 5.0)).getInt("segment"))
        assertEquals(3, relay.pass(event("final", 1, 6.0)).getInt("segment"))
        assertEquals("spoken", relay.pass(JSONObject().put("kind", "spoken").put("t", 7.0)).getString("kind"))
    }

    @Test
    fun aSegmentCutByACrashIsClosedAndHeardAgainFromItsStart() {
        val relay = SegmentRelay()
        relay.pass(event("voice_start", 1, 10.3) { put("start", 10.0) })
        relay.pass(event("partial", 1, 10.8) { put("text", "what can") })
        assertEquals(9.5, relay.replayFrom(11.0, true), 1e-9)
        val closed = relay.lost(11.0)!!
        assertEquals("voice_end", closed.getString("kind"))
        assertEquals(1, closed.getInt("segment"))
        assertEquals(10.8, closed.getDouble("end"), 1e-9)
        assertTrue(closed.getBoolean("lost"))
        assertNull(relay.lost(11.5))
    }

    @Test
    fun aSegmentStillWaitingForItsWordsIsHeardAgainButNotInKeywordsMode() {
        val relay = SegmentRelay()
        relay.pass(event("voice_start", 1, 10.3) { put("start", 10.0) })
        relay.pass(event("voice_end", 1, 12.3) { put("end", 12.0) })
        assertNull(relay.lost(12.5))
        assertEquals(9.5, relay.replayFrom(12.5, true), 1e-9)
        assertEquals(12.25, relay.replayFrom(12.5, false), 1e-9)
        assertEquals(14.75, relay.replayFrom(15.0, true), 1e-9)
        relay.pass(event("final", 1, 12.6) { put("text", "hello") })
        assertEquals(12.55, relay.replayFrom(12.8, true), 1e-9)
    }

    @Test
    fun aNewPauseDropsQueuedPausesAndVoiceEndsAlwaysStay() {
        val queue = java.util.concurrent.LinkedBlockingQueue<Runnable>()
        fun add(after: String, segment: Int) {
            TurnJob.prune(queue, after, segment)
            queue.add(TurnJob(after, segment) {})
        }
        add("pause", 1)
        add("pause", 1)
        add("voice_end", 1)
        add("pause", 2)
        add("pause", 2)
        add("pause", 3)
        val left = queue.map { (it as TurnJob).after + it.segment }
        assertEquals(listOf("voice_end1", "pause3"), left)
        add("voice_end", 3)
        assertEquals(listOf("voice_end1", "voice_end3"), queue.map { (it as TurnJob).after + it.segment })
    }
}
