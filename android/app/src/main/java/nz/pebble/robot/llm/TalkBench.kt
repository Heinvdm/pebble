package nz.pebble.robot.llm

import android.util.Log
import org.json.JSONObject

class TalkBench(
    private val port: Int,
    private val drafterAvailable: () -> Boolean,
    private val hotS: Int,
    private val control: Control,
    private val heat: () -> JSONObject,
    private val memory: () -> JSONObject,
) {
    data class Tune(val batch: Int, val drafter: Boolean)

    interface Control {
        fun use(tune: Tune)
        fun state(tune: Tune): String
    }

    @Volatile var phase = "starting"
        private set
    @Volatile var wanted = Tune(LlamaPlan.BATCH, false)
        private set
    @Volatile var result: JSONObject? = null
        private set
    @Volatile var done = false
        private set
    @Volatile private var stopped = false
    private var thread: Thread? = null
    private val http = LlamaHttp(port)

    fun start() {
        thread = Thread({ run() }, "pebble-talk-bench").also {
            it.isDaemon = true
            it.start()
        }
    }

    fun stop() {
        stopped = true
        thread?.interrupt()
    }

    private fun run() {
        val started = System.currentTimeMillis()
        val out = JSONObject()
        try {
            val speeds = LinkedHashMap<Int, Double>()
            for (batch in LlamaPlan.BATCHES) {
                phase = "reading speed at batch $batch"
                if (!switchTo(Tune(batch, false))) continue
                speeds[batch] = readSpeed(batch)
            }
            out.put("batches", JSONObject().apply { speeds.forEach { (b, v) -> put(b.toString(), LlamaHttp.round(v)) } })
            var batch = LlamaPlan.pickBatch(speeds) ?: LlamaPlan.BATCH
            val cancels = JSONObject()
            while (true) {
                phase = "cancel at batch $batch"
                if (!switchTo(Tune(batch, false))) break
                val ms = cancelMs()
                cancels.put(batch.toString(), LlamaHttp.round(ms))
                if (ms <= LlamaPlan.CANCEL_MS) break
                batch = LlamaPlan.smallerBatch(batch) ?: break
            }
            out.put("cancel_ms", cancels)
            out.put("batch", batch)
            val drafts = if (drafterAvailable()) listOf(true, false) else listOf(false)
            val cool = JSONObject()
            val usable = ArrayList<Boolean>()
            for (drafter in drafts) {
                phase = "talking, ${label(drafter)}, cool"
                if (!switchTo(Tune(batch, drafter))) {
                    cool.put(label(drafter), JSONObject().put("failed", true))
                    continue
                }
                cool.put(label(drafter), talk().json())
                usable += drafter
            }
            out.put("cool", cool)
            val hot = JSONObject()
            val hotAnswers = HashMap<Boolean, LlamaHttp.Answer>()
            val heatBefore = heat()
            for ((index, drafter) in usable.withIndex()) {
                phase = "talking, ${label(drafter)}, hot"
                if (!switchTo(Tune(batch, drafter))) continue
                duty(if (index == 0) hotS else maxOf(30, hotS / 3))
                val answer = talk()
                hotAnswers[drafter] = answer
                hot.put(label(drafter), answer.json().put("heat", heat()))
            }
            out.put("hot", hot)
            out.put("heat_before", heatBefore)
            out.put("heat_after", heat())
            val keep = LlamaPlan.keepDrafter(hotAnswers[true]?.twentiethMs, hotAnswers[false]?.twentiethMs)
            val drafter = when {
                true !in drafts -> null
                true !in usable -> LlamaChoice.DRAFTER_FAILED
                keep -> LlamaChoice.DRAFTER_ON
                else -> LlamaChoice.DRAFTER_OFF
            }
            out.put("drafter", drafter ?: JSONObject.NULL)
            val chosen = hotAnswers[keep] ?: hotAnswers[false] ?: hotAnswers.values.firstOrNull()
            if (chosen != null) {
                val firstWords = CLOSE_MS + (chosen.fifthMs ?: chosen.firstMs ?: 0.0) + VOICE_MS
                out.put("first_words_ms", LlamaHttp.round(firstWords))
                out.put("answer_ms", LlamaHttp.round(CLOSE_MS + (chosen.twentiethMs ?: 0.0) + VOICE_MS))
                out.put("write_tps", LlamaHttp.round(chosen.writeTps))
                out.put("meets_targets", firstWords <= FIRST_WORDS_TARGET_MS && CLOSE_MS + (chosen.twentiethMs ?: Double.MAX_VALUE) + VOICE_MS <= ANSWER_TARGET_MS)
            }
            phase = "memory"
            if (switchTo(Tune(batch, keep))) {
                val m = memory()
                out.put("memory", m)
                out.put("memory_ok", m.optLong("free", Long.MAX_VALUE) >= LlamaPlan.FREE_WITH_BOTH)
            }
        } catch (e: InterruptedException) {
            out.put("problem", "stopped before it finished")
        } catch (e: Exception) {
            Log.w(TAG, "the talk bench failed", e)
            out.put("problem", "the talk bench failed: ${e.message}")
        }
        out.put("took_s", (System.currentTimeMillis() - started) / 1000)
        out.put("at", System.currentTimeMillis())
        result = out
        phase = "done"
        done = true
        Log.i(TAG, "talk bench: $out")
        control.use(wanted)
    }

    private fun label(drafter: Boolean) = if (drafter) "with the drafter" else "without the drafter"

    private fun switchTo(tune: Tune): Boolean {
        wanted = tune
        control.use(tune)
        val deadline = System.currentTimeMillis() + WAIT_MS
        while (!stopped && System.currentTimeMillis() < deadline) {
            when (control.state(tune)) {
                "ready" -> return true
                "failed" -> return false
            }
            Thread.sleep(POLL_MS)
        }
        if (stopped) throw InterruptedException()
        return false
    }

    private fun readSpeed(batch: Int): Double {
        var best = 0.0
        for (round in 0 until 2) {
            val answer = http.complete(BenchText.words(SEED_SPEED + batch * 10 + round, SPEED_WORDS), 1, TIMEOUT_MS, stream = false)
            best = maxOf(best, answer.promptTps)
        }
        return best
    }

    private fun cancelMs(): Double {
        http.complete("Hello.", 1, TIMEOUT_MS, stream = false)
        val closedAt = http.abandon(BenchText.words(SEED_CANCEL + (System.nanoTime() % 1000).toInt(), CANCEL_WORDS), CANCEL_AFTER_MS, TIMEOUT_MS) ?: return 0.0
        http.complete("Hello.", 1, TIMEOUT_MS, stream = false)
        return (System.nanoTime() - closedAt) / 1e6
    }

    private fun talk(): LlamaHttp.Answer {
        val base = BenchText.words(SEED_BASE, BASE_WORDS)
        http.complete(base, 1, TIMEOUT_MS, stream = false)
        return http.complete(base + " " + BenchText.words(SEED_TAIL + (System.nanoTime() % 1000).toInt(), TAIL_WORDS) + TAIL, ANSWER_TOKENS, TIMEOUT_MS)
    }

    private fun duty(seconds: Int) {
        val base = BenchText.words(SEED_BASE, BASE_WORDS)
        val until = System.currentTimeMillis() + seconds * 1000L
        var round = 0
        while (!stopped && System.currentTimeMillis() < until) {
            http.complete(base + " " + BenchText.words(SEED_DUTY + round, DUTY_WORDS), ANSWER_TOKENS, TIMEOUT_MS, stream = false)
            round++
        }
        if (stopped) throw InterruptedException()
    }

    companion object {
        const val TAG = "PebbleTalkBench"
        const val WAIT_MS = 20 * 60_000L
        const val POLL_MS = 1_000L
        const val TIMEOUT_MS = 10 * 60_000
        const val SPEED_WORDS = 450
        const val CANCEL_WORDS = 1_100
        const val CANCEL_AFTER_MS = 1_000L
        const val BASE_WORDS = 1_850
        const val TAIL_WORDS = 9
        const val DUTY_WORDS = 110
        const val ANSWER_TOKENS = 20
        const val TAIL = "\n<end_of_turn>\n<start_of_turn>model\n"
        const val CLOSE_MS = 250.0
        const val VOICE_MS = 100.0
        const val FIRST_WORDS_TARGET_MS = 1_500.0
        const val ANSWER_TARGET_MS = 5_000.0
        const val SEED_SPEED = 1_000
        const val SEED_CANCEL = 5_000
        const val SEED_BASE = 7
        const val SEED_TAIL = 9_000
        const val SEED_DUTY = 20_000
        const val STEPS = 5

        fun step(phase: String): Int = when {
            phase.startsWith("reading speed") -> 1
            phase.startsWith("cancel") -> 2
            phase.startsWith("talking") && phase.endsWith("cool") -> 3
            phase.startsWith("talking") && phase.endsWith("hot") -> 4
            phase == "memory" || phase == "done" -> 5
            else -> 1
        }

        fun plain(phase: String): String = when (step(phase)) {
            1 -> "how fast it reads"
            2 -> "how quickly it stops when someone starts talking"
            3 -> "how fast it answers"
            4 -> "how fast it answers after a few minutes of steady work"
            else -> "how much memory is left"
        }
    }
}

object BenchText {
    private val WORDS = listOf(
        "the", "little", "robot", "rolled", "across", "kitchen", "floor", "and", "looked", "at", "a", "bright", "window", "while", "people",
        "talked", "about", "their", "day", "in", "garden", "with", "two", "cats", "who", "slept", "near", "warm", "door", "after", "long",
        "walk", "by", "river", "where", "children", "played", "small", "boats", "made", "from", "old", "paper", "rain", "fell", "softly",
        "on", "roof", "of", "house", "someone", "made", "tea", "asked", "what", "it", "had", "seen", "today", "answer", "was", "short",
        "kind", "funny", "story", "about", "dog", "chasing", "leaves", "under", "tree", "evening", "light", "turned", "orange", "then",
        "blue", "music", "played", "quietly", "friends", "laughed", "together", "cooking", "soup", "bread", "smelled", "good", "everyone",
        "sat", "down", "eat", "share", "plans", "for", "weekend", "trip", "mountains", "beach", "maybe", "both",
    )

    fun words(seed: Int, count: Int): String {
        var state = seed.toLong() * 6364136223846793005L + 1442695040888963407L
        val out = StringBuilder()
        for (i in 0 until count) {
            state = state * 6364136223846793005L + 1442695040888963407L
            val index = ((state ushr 33) % WORDS.size).toInt()
            if (i > 0) out.append(if (i % 13 == 0) ". " else " ")
            out.append(WORDS[index])
        }
        return out.append('.').toString()
    }
}
