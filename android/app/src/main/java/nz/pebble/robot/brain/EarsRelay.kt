package nz.pebble.robot.brain

import org.json.JSONObject
import kotlin.math.max

class TurnJob(val after: String, val segment: Int, private val work: () -> Unit) : Runnable {
    override fun run() = work()

    companion object {
        const val PAUSE = "pause"

        fun prune(queue: java.util.concurrent.BlockingQueue<Runnable>, after: String, segment: Int) {
            queue.removeIf { it is TurnJob && it.after == PAUSE && (after == PAUSE || it.segment <= segment) }
        }
    }
}

class HeldSound(private val keepS: Double = KEEP_S, private val rate: Int = Microphone.RATE) {
    class Piece(val pcm: ShortArray, val at: Double, val speaking: Boolean)

    private val pieces = ArrayDeque<Piece>()
    private var samples = 0

    val heldS: Double get() = samples.toDouble() / rate

    val oldest: Double get() = pieces.firstOrNull()?.let { it.at - it.pcm.size.toDouble() / rate } ?: Double.POSITIVE_INFINITY

    fun add(pcm: ShortArray, count: Int, at: Double, speaking: Boolean) {
        if (count <= 0) return
        pieces.addLast(Piece(pcm.copyOf(count), at, speaking))
        samples += count
        val keep = (keepS * rate).toInt()
        while (pieces.size > 1 && samples - pieces.first().pcm.size >= keep) samples -= pieces.removeFirst().pcm.size
    }

    fun clear() {
        pieces.clear()
        samples = 0
    }

    fun since(from: Double, longestS: Double = PIECE_S): List<Piece> {
        val most = max(1, (longestS * rate).toInt())
        val out = ArrayList<Piece>()
        var run = ArrayList<Piece>()
        var runSamples = 0
        fun close() {
            if (run.isEmpty()) return
            val pcm = ShortArray(runSamples)
            var at = 0
            for (p in run) {
                System.arraycopy(p.pcm, 0, pcm, at, p.pcm.size)
                at += p.pcm.size
            }
            out += Piece(pcm, run.last().at, run.last().speaking)
            run = ArrayList()
            runSamples = 0
        }
        for (p in pieces) {
            if (p.at <= from) continue
            if (run.isNotEmpty() && (run.last().speaking != p.speaking || runSamples + p.pcm.size > most)) close()
            run += p
            runSamples += p.pcm.size
        }
        close()
        return out
    }

    companion object {
        const val KEEP_S = 12.0
        const val PIECE_S = 0.5
    }
}

class SegmentRelay {
    private var offset = 0
    private var highest = 0
    private var open: Int? = null
    private var openStart = 0.0
    private var openLast = 0.0
    private var ended: Int? = null
    private var endedStart = 0.0
    private var endedAt = 0.0

    val openSegment: Int? get() = open

    fun restarted() {
        offset = highest
        open = null
        ended = null
    }

    fun pass(event: JSONObject): JSONObject {
        if (!event.has("segment")) return event
        val segment = event.optInt("segment") + offset
        event.put("segment", segment)
        highest = max(highest, segment)
        val t = event.optDouble("t", 0.0)
        when (event.optString("kind")) {
            "voice_start" -> {
                open = segment
                openStart = event.optDouble("start", t)
                openLast = t
            }
            "partial", "pause", "keyword" -> if (segment == open) openLast = max(openLast, t)
            "voice_end" -> if (segment == open) {
                open = null
                ended = segment
                endedStart = openStart
                endedAt = event.optDouble("end", t)
            }
            "final" -> if (segment == ended) ended = null
        }
        return event
    }

    fun lost(now: Double): JSONObject? {
        val segment = open ?: return null
        open = null
        return JSONObject()
            .put("kind", "voice_end")
            .put("t", now)
            .put("segment", segment)
            .put("end", max(openStart, openLast))
            .put("pebble_speaking", false)
            .put("lost", true)
    }

    fun replayFrom(diedAt: Double, words: Boolean): Double {
        open?.let { return openStart - PRE_S }
        val waiting = ended
        if (words && waiting != null && diedAt - endedAt <= FINAL_WAIT_S) return endedStart - PRE_S
        return diedAt - OVERLAP_S
    }

    companion object {
        const val PRE_S = 0.5
        const val OVERLAP_S = 0.25
        const val FINAL_WAIT_S = 2.0
    }
}
