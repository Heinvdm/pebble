package nz.pebble.robot.recall

import android.content.Context
import android.os.Build
import android.os.Process
import android.util.Log
import nz.pebble.robot.BuildConfig
import nz.pebble.robot.keeper.HeatLevel
import nz.pebble.robot.keeper.PaceFile
import nz.pebble.robot.llm.BenchText
import nz.pebble.robot.llm.LlamaServer
import nz.pebble.robot.llm.LlamaWatch
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.util.concurrent.Callable
import java.util.concurrent.CancellationException
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.ExecutionException
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import java.util.concurrent.Future
import java.util.concurrent.RejectedExecutionException
import java.util.concurrent.TimeUnit
import java.util.concurrent.TimeoutException

class SentenceModel(
    private val phone: Phone,
    private val choice: RecallChoice,
    private val key: String,
    private val limits: Limits = Limits(),
) : AutoCloseable {
    interface Phone {
        val present: Boolean
        fun encoder(): Encoder
        fun words(): WordPiece
        fun writing(): Boolean
        fun hot(): Boolean
        fun heat(): JSONObject
        fun eyes(): Boolean
        fun ears(): String
        fun place(): JSONObject
        fun placed(): JSONObject
    }

    data class Limits(
        val batch: Int = BATCH,
        val queryWaitMs: Long = 1_200L,
        val queryRunMs: Long = 1_500L,
        val batchWaitMs: Long = 60_000L,
        val runMs: Long = 60_000L,
        val pollMs: Long = 100L,
        val settleMs: Long = 180_000L,
        val settlePollMs: Long = 1_000L,
        val benchMs: Long = 30 * 60_000L,
        val times: Int = TIMES,
        val batchTimes: Int = BATCH_TIMES,
    )

    private class Ran(val rows: Array<FloatArray>?, val why: String, val ms: Double = 0.0)

    private val lock = Object()
    private var rung: String
    private var why: String
    private var bench: JSONObject? = null
    private var measuring = ""
    private var served = 0L
    private var runs = 0L
    private var failures = 0
    private var loadMs = -1.0
    private var waitedMs = 0L
    private var yielded = 0L
    private var last: JSONObject? = null
    private val refused = LinkedHashMap<String, Long>()
    private var benchThread: Thread? = null
    @Volatile private var closed = false
    @Volatile private var place = JSONObject()
    @Volatile private var encoder: Encoder? = null
    @Volatile private var words: WordPiece? = null
    @Volatile private var batchToken: Any? = null
    private val pending: MutableSet<Future<*>> = ConcurrentHashMap.newKeySet()
    private val worker: ExecutorService = Executors.newSingleThreadExecutor { job ->
        Thread({
            place = try {
                phone.place()
            } catch (e: Throwable) {
                JSONObject().put("problem", e.message ?: e.javaClass.simpleName)
            }
            job.run()
        }, "pebble-recall").apply { isDaemon = true }
    }

    init {
        val saved = if (phone.present) choice.read(key) else null
        when {
            !phone.present -> {
                rung = RecallChoice.MISSING
                why = "the sentence model is not in this app"
            }
            saved != null -> {
                rung = saved.rung
                why = saved.why
                bench = saved.bench
            }
            else -> {
                rung = RecallChoice.UNMEASURED
                why = "not measured on this phone yet"
            }
        }
    }

    fun start() {
        if (synchronized(lock) { rung == RecallChoice.UNMEASURED }) measure(true)
    }

    fun measure(settle: Boolean): Boolean = synchronized(lock) {
        if (closed || !phone.present || benchThread?.isAlive == true) return false
        benchThread = Thread({ benchLoop(settle) }, "pebble-recall-bench").apply {
            isDaemon = true
            start()
        }
        true
    }

    fun measuringNow(): Boolean = synchronized(lock) { benchThread?.isAlive == true }

    private fun usable(): Boolean = rung == RecallChoice.ONNX || rung == RecallChoice.UNMEASURED

    fun embed(texts: List<String>, query: Boolean): Array<FloatArray>? {
        if (texts.isEmpty()) return emptyArray()
        if (closed) return refuse(CLOSED)
        if (!synchronized(lock) { usable() }) return refuse(STAND_IN)
        val deadline = now() + if (query) limits.queryWaitMs else limits.batchWaitMs
        val out = ArrayList<FloatArray>(texts.size)
        for (part in texts.chunked(limits.batch)) {
            val rows = chunk(part, query, deadline) ?: return null
            out.addAll(rows)
        }
        synchronized(lock) {
            if (closed || !usable()) return refuse(STAND_IN)
            served += out.size
        }
        return out.toTypedArray()
    }

    fun embedJson(texts: String, query: Boolean): ByteArray {
        val list = try {
            val all = JSONArray(texts)
            List(all.length()) { all.optString(it, "") }
        } catch (e: Exception) {
            return ByteArray(0)
        }
        val rows = embed(list, query) ?: return ByteArray(0)
        return Pooling.pack(rows)
    }

    private fun chunk(texts: List<String>, query: Boolean, deadline: Long): Array<FloatArray>? {
        val token = if (query) null else Any()
        while (true) {
            val blocked = waitClear(query, deadline)
            if (blocked != null) return refuse(blocked)
            if (query) batchToken?.let { running -> encoder?.stop(running) }
            val watch = token?.let { mine -> { if (batchToken === mine && phone.writing()) encoder?.stop(mine) } }
            val ran = submit(now() + if (query) limits.queryRunMs else limits.runMs, watch) { run(texts, query, !query, token) } ?: return refuse(if (closed) CLOSED else BUSY)
            if (ran.rows != null) return ran.rows
            if (ran.why != WRITING && ran.why != HOT && ran.why != YIELDED) return refuse(ran.why)
            if (ran.why == YIELDED && now() >= deadline) return refuse(YIELDED)
        }
    }

    private fun waitClear(query: Boolean, deadline: Long): String? {
        while (true) {
            if (closed) return CLOSED
            val reason = when {
                !query && phone.hot() -> HOT
                phone.writing() -> WRITING
                else -> return null
            }
            val left = deadline - now()
            if (left <= 0) return reason
            val nap = minOf(limits.pollMs, left)
            try {
                Thread.sleep(nap)
            } catch (e: InterruptedException) {
                Thread.currentThread().interrupt()
                return CLOSED
            }
            synchronized(lock) { waitedMs += nap }
        }
    }

    private fun <T> submit(until: Long, watch: (() -> Unit)? = null, job: () -> T): T? {
        if (closed) return null
        val future = try {
            worker.submit(Callable { job() })
        } catch (e: RejectedExecutionException) {
            return null
        }
        pending += future
        return try {
            var answer: T? = null
            while (true) {
                val left = until - now()
                if (left <= 0) {
                    future.cancel(false)
                    break
                }
                try {
                    answer = future.get(if (watch == null) left else minOf(left, limits.pollMs), TimeUnit.MILLISECONDS)
                    break
                } catch (e: TimeoutException) {
                    watch?.invoke()
                }
            }
            answer
        } catch (e: CancellationException) {
            null
        } catch (e: ExecutionException) {
            Log.w(TAG, "the sentence model's worker failed", e.cause)
            null
        } catch (e: InterruptedException) {
            Thread.currentThread().interrupt()
            future.cancel(false)
            null
        } finally {
            pending -= future
        }
    }

    private fun run(texts: List<String>, query: Boolean, check: Boolean, token: Any?): Ran {
        if (closed) return Ran(null, CLOSED)
        if (check) {
            if (phone.hot()) return Ran(null, HOT)
            if (phone.writing()) return Ran(null, WRITING)
        }
        val (model, pieces) = loaded() ?: return Ran(null, FAILED)
        place = try {
            phone.placed()
        } catch (e: Throwable) {
            place
        }
        val started = System.nanoTime()
        return try {
            val ids = texts.map { pieces.ids(if (query) QUERY_PREFIX + it else it) }
            if (token != null) batchToken = token
            val rows = try {
                model.encode(ids, token)
            } finally {
                if (token != null) batchToken = null
            }
            if (rows.size != texts.size || rows.any { it.size != Pooling.DIM }) throw IllegalStateException("it gave ${rows.size} rows of ${rows.firstOrNull()?.size ?: 0} numbers for ${texts.size} lines")
            val ms = (System.nanoTime() - started) / 1e6
            synchronized(lock) {
                runs++
                failures = 0
                last = JSONObject().put("lines", texts.size).put("query", query).put("tokens", ids.sumOf { it.size }).put("ms", round(ms))
            }
            Ran(rows, "", ms)
        } catch (e: Encoder.Stopped) {
            synchronized(lock) { yielded++ }
            Ran(null, YIELDED)
        } catch (e: Throwable) {
            failed("the sentence model failed: ${e.message?.take(160) ?: e.javaClass.simpleName}", e)
            Ran(null, FAILED)
        }
    }

    private fun loaded(): Pair<Encoder, WordPiece>? {
        val haveModel = encoder
        val haveWords = words
        if (haveModel != null && haveWords != null) return haveModel to haveWords
        if (!synchronized(lock) { usable() }) return null
        val started = System.nanoTime()
        return try {
            val madeWords = haveWords ?: phone.words()
            words = madeWords
            val madeModel = haveModel ?: phone.encoder()
            encoder = madeModel
            synchronized(lock) { loadMs = (System.nanoTime() - started) / 1e6 }
            Log.i(TAG, "the sentence model is loaded in ${Math.round((System.nanoTime() - started) / 1e6)} ms, ${madeWords.size} word pieces, place $place")
            madeModel to madeWords
        } catch (e: Throwable) {
            Log.w(TAG, "the sentence model would not load", e)
            turn(RecallChoice.FAILED, "the sentence model would not load: ${e.message?.take(160) ?: e.javaClass.simpleName}", null)
            null
        }
    }

    private fun failed(reason: String, e: Throwable) {
        Log.w(TAG, reason, e)
        val give = synchronized(lock) {
            failures++
            failures >= MAX_FAILURES && usable()
        }
        if (give) turn(RecallChoice.FAILED, reason, null)
    }

    private fun turn(to: String, reason: String, measured: JSONObject?) {
        val kept = synchronized(lock) {
            rung = to
            why = reason
            if (measured != null) bench = measured
            bench
        }
        if (!choice.keep(key, to, reason, kept)) Log.w(TAG, "could not keep the sentence model's choice")
        Log.i(TAG, "memory search: $to ($reason)")
    }

    private fun refuse(reason: String): Array<FloatArray>? {
        synchronized(lock) { refused[reason] = (refused[reason] ?: 0L) + 1L }
        return null
    }

    private fun setMeasuring(phase: String) = synchronized(lock) { measuring = phase }

    private fun benchLoop(settle: Boolean) {
        val started = System.currentTimeMillis()
        try {
            if (settle) {
                setMeasuring("waiting for the eyes and ears")
                val until = now() + limits.settleMs
                while (!closed && now() < until && !(phone.eyes() && phone.ears() == EARS_READY)) Thread.sleep(limits.settlePollMs)
            }
            if (closed) return
            val result = JSONObject().put("eyes", phone.eyes()).put("ears", phone.ears()).put("heat_before", phone.heat())
            val until = now() + limits.benchMs
            setMeasuring("loading")
            if (submit(until) { loaded() != null } != true) {
                if (!closed) Log.w(TAG, "the sentence model could not be measured: it did not load")
                return
            }
            setMeasuring("timing")
            val notes = List(limits.batch) { BenchText.words(SEED_NOTE + it, 12 + it % 9) }
            val questions = List(limits.times) { BenchText.words(SEED_QUESTION + it, 8) }
            timed(until, notes.take(1), false) ?: return quit()
            val single = (0 until limits.times).map { timed(until, listOf(notes[(it + 1) % notes.size]), false) ?: return quit() }
            val asked = (0 until limits.times).map { timed(until, listOf(questions[it]), true) ?: return quit() }
            val batches = (0 until limits.batchTimes).map { timed(until, notes, false) ?: return quit() }
            val tokens = words?.let { w -> notes.sumOf { w.ids(it).size } / notes.size.toDouble() } ?: 0.0
            val batchMs = median(batches)
            result.put("load_ms", round(synchronized(lock) { loadMs }))
                .put("note_ms", round(median(single)))
                .put("query_ms", round(median(asked)))
                .put("batch_ms", round(batchMs))
                .put("per_note_ms", round(batchMs / notes.size))
                .put("batch", notes.size)
                .put("tokens", round(tokens))
                .put("core", place.opt("core") ?: JSONObject.NULL)
                .put("pinned", place.optBoolean("pinned"))
                .put("cpus", place.opt("cpus") ?: JSONObject.NULL)
                .put("heat_after", phone.heat())
                .put("took_s", (System.currentTimeMillis() - started) / 1000)
                .put("at", System.currentTimeMillis())
            val (to, reason) = RecallChoice.decide(result)
            turn(to, reason, result)
            Log.i(TAG, "sentence model bench: $result")
        } catch (e: InterruptedException) {
            Log.i(TAG, "the sentence model's bench was stopped")
        } catch (e: Exception) {
            Log.w(TAG, "the sentence model's bench failed", e)
        } finally {
            setMeasuring("")
        }
    }

    private fun quit() {
        if (closed) return
        val why = if (synchronized(lock) { usable() }) "no quiet moment came in ${limits.benchMs / 60_000} minutes" else "it failed"
        Log.w(TAG, "the sentence model was not measured: $why; it tries again at the next start")
    }

    private fun timed(until: Long, texts: List<String>, query: Boolean): Double? {
        val token = Any()
        val watch = { if (batchToken === token && phone.writing()) encoder?.stop(token) }
        while (true) {
            if (waitClear(false, until) != null) return null
            val ran = submit(now() + limits.runMs, watch) { run(texts, query, true, token) } ?: return null
            if (ran.rows != null) return ran.ms
            if (ran.why != WRITING && ran.why != HOT && ran.why != YIELDED) return null
        }
    }

    fun choiceJson(): JSONObject = synchronized(lock) {
        JSONObject()
            .put("model", MODEL_NAME)
            .put("present", phone.present)
            .put("rung", rung)
            .put("why", why)
            .put("measured", rung in RecallChoice.KEPT)
            .put("standin_now", !usable() && served == 0L)
            .put("measuring", measuring)
            .put("served", served)
            .put("bench", bench ?: JSONObject.NULL)
    }

    fun info(): JSONObject {
        val out = choiceJson()
        synchronized(lock) {
            out.put("loaded", encoder != null)
                .put("load_ms", if (loadMs < 0) JSONObject.NULL else round(loadMs))
                .put("runs", runs)
                .put("failures", failures)
                .put("waited_ms", waitedMs)
                .put("gave_way", yielded)
                .put("refused", JSONObject(refused as Map<*, *>))
                .put("last", last ?: JSONObject.NULL)
                .put("place", JSONObject(place.toString()))
                .put("batch", limits.batch)
                .put("closed", closed)
        }
        return out
    }

    override fun close() {
        synchronized(lock) {
            if (closed) return
            closed = true
            benchThread?.interrupt()
        }
        pending.forEach { it.cancel(false) }
        try {
            worker.submit {
                encoder?.close()
                encoder = null
            }
        } catch (e: RejectedExecutionException) {
            Log.d(TAG, "the sentence model's worker had already stopped")
        }
        worker.shutdown()
    }

    companion object {
        const val TAG = "PebbleRecall"
        const val BATCH = 32
        const val MODEL_NAME = "snowflake-arctic-embed-xs-int8"
        const val MODEL_FILE = "arctic_embed_xs_int8.onnx"
        const val VOCAB_FILE = "arctic_embed_xs_vocab.txt"
        const val MODEL_ASSET = "recall/$MODEL_FILE"
        const val VOCAB_ASSET = "recall/$VOCAB_FILE"
        const val QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
        const val CLOSED = "closed"
        const val STAND_IN = "stand-in"
        const val BUSY = "busy"
        const val WRITING = "writing"
        const val HOT = "hot"
        const val YIELDED = "gave way"
        const val FAILED = "failed"
        const val EARS_READY = "ready"
        const val MAX_FAILURES = 3
        const val TIMES = 5
        const val BATCH_TIMES = 3
        const val SEED_NOTE = 31_000
        const val SEED_QUESTION = 32_000

        private fun now(): Long = System.nanoTime() / 1_000_000L

        fun round(value: Double): Double = Math.round(value * 10) / 10.0

        fun median(values: List<Double>): Double {
            if (values.isEmpty()) return Double.NaN
            val sorted = values.sorted()
            val mid = sorted.size / 2
            return if (sorted.size % 2 == 1) sorted[mid] else (sorted[mid - 1] + sorted[mid]) / 2
        }

        fun choiceFile(context: Context): File = File(context.noBackupFilesDir, RecallChoice.NAME)

        fun forget(context: Context) {
            choiceFile(context).delete()
        }

        fun forPhone(context: Context, pace: File, eyes: () -> Boolean, ears: () -> String): SentenceModel {
            val core = try {
                LittleCore.pick(LlamaServer.maxFreqs())
            } catch (e: Exception) {
                null
            }
            val phone = AndroidPhone(context, pace, eyes, ears, core)
            val size = try {
                context.assets.openFd(MODEL_ASSET).use { it.length }
            } catch (e: Exception) {
                -1L
            }
            val key = listOf(BuildConfig.VERSION_CODE.toString(), Build.MODEL, Build.SUPPORTED_ABIS.firstOrNull() ?: "-", size.toString(), core?.toString() ?: "-").joinToString("/")
            return SentenceModel(phone, RecallChoice(choiceFile(context)), key)
        }
    }
}

private class AndroidPhone(
    private val context: Context,
    private val pace: File,
    private val eyesOn: () -> Boolean,
    private val earsPhase: () -> String,
    private val core: Int?,
) : SentenceModel.Phone {
    private val watch = LlamaWatch()
    private var heatAt = 0L
    private var heatNow = JSONObject()
    private var tid = -1
    private var pinned = false
    private var pinProblem = ""

    override val present: Boolean = try {
        context.assets.list("recall")?.toSet()?.containsAll(listOf(SentenceModel.MODEL_FILE, SentenceModel.VOCAB_FILE)) == true
    } catch (e: Exception) {
        false
    }

    override fun encoder(): Encoder = OrtEncoder(context.assets.open(SentenceModel.MODEL_ASSET).use { it.readBytes() })

    override fun words(): WordPiece = WordPiece.load(context.assets.open(SentenceModel.VOCAB_ASSET).bufferedReader(Charsets.UTF_8).use { it.readText() })

    override fun writing(): Boolean = watch.writing()

    @Synchronized
    private fun fresh(): JSONObject {
        val now = System.currentTimeMillis()
        if (now - heatAt >= HEAT_EVERY_MS) {
            heatNow = try {
                PaceFile.forBrain(context, pace)
            } catch (e: Exception) {
                JSONObject().put("level", HeatLevel.COOL)
            }
            heatAt = now
        }
        return heatNow
    }

    override fun hot(): Boolean = fresh().optString("level", HeatLevel.COOL) == HeatLevel.HOT

    override fun heat(): JSONObject {
        val now = fresh()
        return JSONObject().put("level", now.optString("level", HeatLevel.COOL)).put("headroom", now.optDouble("headroom", -1.0))
    }

    override fun eyes(): Boolean = try {
        eyesOn()
    } catch (e: Exception) {
        false
    }

    override fun ears(): String = try {
        earsPhase()
    } catch (e: Exception) {
        "none"
    }

    override fun place(): JSONObject {
        Process.setThreadPriority(Process.THREAD_PRIORITY_BACKGROUND)
        tid = Process.myTid()
        if (core != null) {
            pinProblem = LittleCore.pin(tid, core)
            pinned = pinProblem.isEmpty()
            if (!pinned) Log.w(SentenceModel.TAG, "the sentence model could not be kept on core $core: $pinProblem")
        }
        return where()
    }

    override fun placed(): JSONObject {
        if (core != null && pinned && LittleCore.allowed(tid) != listOf(core)) {
            pinProblem = LittleCore.pin(tid, core)
            pinned = pinProblem.isEmpty()
        }
        return where()
    }

    private fun where(): JSONObject = JSONObject()
        .put("core", core ?: JSONObject.NULL)
        .put("pinned", pinned)
        .put("cpus", LittleCore.allowed(tid)?.joinToString(",") ?: JSONObject.NULL)
        .put("problem", pinProblem)
        .put("priority", try {
            Process.getThreadPriority(tid)
        } catch (e: Exception) {
            0
        })
        .put("threads", 1)
        .put("llama_checks", watch.checks)

    companion object {
        const val HEAT_EVERY_MS = 2_000L
    }
}
