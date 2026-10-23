package nz.pebble.robot.recall

import org.json.JSONObject
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File
import java.util.Collections
import kotlin.concurrent.thread

class SentenceModelTest {
    @get:Rule
    val folder = TemporaryFolder()

    private class Phone(override val present: Boolean = true) : SentenceModel.Phone {
        @Volatile var writingNow = false
        @Volatile var hotNow = false
        @Volatile var eyesOn = true
        @Volatile var earsPhase = "ready"
        @Volatile var questionMs = 0L
        @Volatile var noteMs = 0L
        @Volatile var failLoad = false
        @Volatile var ranWhileWriting = 0
        @Volatile var ranWhileHot = 0
        val batches: MutableList<List<IntArray>> = Collections.synchronizedList(ArrayList())
        val words = WordPiece.load(listOf("[PAD]", "[UNK]", "[CLS]", "[SEP]", "represent", "this", "sentence", "for", "searching", "relevant", "passages", ":", "note").joinToString("\n"))

        @Volatile var writingSlices = 0
        @Volatile var stops = 0

        override fun encoder(): Encoder {
            if (failLoad) throw IllegalStateException("the model file is broken")
            return object : Encoder {
                @Volatile private var current: Any? = null
                @Volatile private var stopping = false

                override fun encode(rows: List<IntArray>, token: Any?): Array<FloatArray> {
                    if (writingNow) ranWhileWriting++
                    if (hotNow) ranWhileHot++
                    current = token
                    stopping = false
                    try {
                        val asking = rows.any { it.size > 1 && it[1] == 4 }
                        val until = System.nanoTime() + (if (asking) questionMs else noteMs) * 1_000_000L
                        while (System.nanoTime() < until) {
                            if (stopping) throw Encoder.Stopped()
                            if (writingNow) writingSlices++
                            Thread.sleep(5)
                        }
                    } finally {
                        current = null
                    }
                    batches += rows
                    return Array(rows.size) { r -> Pooling.normalize(FloatArray(Pooling.DIM).also { v -> v[0] = rows[r].size.toFloat(); v[1] = 1f }) }
                }

                override fun stop(token: Any) {
                    if (current === token) {
                        stops++
                        stopping = true
                    }
                }

                override fun close() = Unit
            }
        }

        override fun words(): WordPiece = words
        override fun writing(): Boolean = writingNow
        override fun hot(): Boolean = hotNow
        override fun heat(): JSONObject = JSONObject().put("level", if (hotNow) "hot" else "cool")
        override fun eyes(): Boolean = eyesOn
        override fun ears(): String = earsPhase
        override fun place(): JSONObject = JSONObject().put("core", 2).put("pinned", true)
        override fun placed(): JSONObject = place()
    }

    private val fast = SentenceModel.Limits(queryWaitMs = 200, batchWaitMs = 300, pollMs = 10, settleMs = 300, settlePollMs = 10, benchMs = 5_000, times = 1, batchTimes = 1)

    private fun choice() = RecallChoice(File(folder.root, RecallChoice.NAME))

    private fun model(phone: Phone, limits: SentenceModel.Limits = fast) = SentenceModel(phone, choice(), "test/key", limits)

    private fun settle(model: SentenceModel) {
        val until = System.currentTimeMillis() + 10_000
        while (model.measuringNow() && System.currentTimeMillis() < until) Thread.sleep(10)
        assertFalse("the bench finished", model.measuringNow())
    }

    @Test
    fun notesGoInBatchesOfUpTo32AndComeBackInOrder() {
        val phone = Phone()
        model(phone).use { model ->
            val texts = List(70) { "note ".repeat(it + 1).trim() }
            val rows = model.embed(texts, false)!!
            assertEquals(70, rows.size)
            assertEquals(listOf(32, 32, 6), phone.batches.map { it.size })
            for ((n, row) in rows.withIndex()) {
                val size = Math.sqrt((n + 3.0) * (n + 3.0) + 1.0)
                assertEquals((n + 3) / size, row[0].toDouble(), 1e-5)
            }
            assertEquals(70L, model.choiceJson().getLong("served"))
        }
    }

    @Test
    fun aLongCallGetsItsTimeForEveryBatch() {
        val phone = Phone()
        phone.noteMs = 250
        model(phone, fast.copy(batchWaitMs = 100, runMs = 400)).use { model ->
            val rows = model.embed(List(96) { "note" }, false)
            assertNotNull(rows)
            assertEquals(96, rows!!.size)
            assertEquals(listOf(32, 32, 32), phone.batches.map { it.size })
        }
    }

    @Test
    fun questionsCarryTheSearchPrefixAndNotesDoNot() {
        val phone = Phone()
        model(phone).use { model ->
            assertNotNull(model.embed(listOf("note"), true))
            assertNotNull(model.embed(listOf("note"), false))
            assertArrayEquals(intArrayOf(2, 4, 5, 6, 7, 8, 9, 10, 11, 12, 3), phone.batches[0][0])
            assertArrayEquals(intArrayOf(2, 12, 3), phone.batches[1][0])
            assertEquals(0, model.embed(emptyList(), false)!!.size)
        }
    }

    @Test
    fun itWaitsWhileALanguageModelWritesAndNeverRunsDuringIt() {
        val phone = Phone()
        phone.writingNow = true
        model(phone, fast.copy(batchWaitMs = 3_000)).use { model ->
            val started = System.nanoTime()
            thread {
                Thread.sleep(300)
                phone.writingNow = false
            }
            val rows = model.embed(listOf("note", "note note"), false)
            val tookMs = (System.nanoTime() - started) / 1e6
            assertNotNull(rows)
            assertTrue("waited $tookMs ms", tookMs >= 250)
            assertEquals(0, phone.ranWhileWriting)
        }
    }

    @Test
    fun aRunningBatchStopsAsSoonAsALanguageModelStartsWritingAndFinishesAfter() {
        val phone = Phone()
        phone.noteMs = 1_500
        model(phone, fast.copy(batchWaitMs = 5_000)).use { model ->
            var rows: Array<FloatArray>? = null
            val caller = thread { rows = model.embed(List(5) { "note" }, false) }
            Thread.sleep(300)
            phone.writingNow = true
            Thread.sleep(500)
            phone.writingNow = false
            caller.join(10_000)
            assertEquals(5, rows!!.size)
            assertTrue("stopped ${phone.stops} times", phone.stops >= 1)
            assertTrue("ran ${phone.writingSlices * 5} ms while writing", phone.writingSlices <= 8)
            assertTrue(model.info().getLong("gave_way") >= 1)
        }
    }

    @Test
    fun aQuestionDoesNotWaitBehindABatch() {
        val phone = Phone()
        phone.noteMs = 2_000
        model(phone, fast.copy(batchWaitMs = 10_000)).use { model ->
            var rows: Array<FloatArray>? = null
            val caller = thread { rows = model.embed(List(5) { "note" }, false) }
            Thread.sleep(200)
            val started = System.nanoTime()
            assertNotNull(model.embed(listOf("note"), true))
            val tookMs = (System.nanoTime() - started) / 1e6
            assertTrue("the question took $tookMs ms", tookMs < 500)
            caller.join(10_000)
            assertEquals(5, rows!!.size)
            assertEquals(listOf(1, 5), phone.batches.map { it.size })
        }
    }

    @Test
    fun aBatchIsRefusedWhenTheWritingOutlastsItsWaitAndAQuestionWaitsOnlyBriefly() {
        val phone = Phone()
        phone.writingNow = true
        model(phone).use { model ->
            assertNull(model.embed(listOf("note"), false))
            val started = System.nanoTime()
            assertNull(model.embed(listOf("note"), true))
            assertTrue((System.nanoTime() - started) / 1e6 < 1_000)
            assertEquals(0, phone.batches.size)
            assertEquals(2L, model.info().getJSONObject("refused").getLong(SentenceModel.WRITING))
        }
    }

    @Test
    fun whenThePhoneIsHotNotesWaitButQuestionsStillRun() {
        val phone = Phone()
        phone.hotNow = true
        model(phone).use { model ->
            assertNotNull(model.embed(listOf("note"), true))
            assertNull(model.embed(listOf("note"), false))
            assertEquals(1, phone.batches.size)
            assertEquals(1L, model.info().getJSONObject("refused").getLong(SentenceModel.HOT))
        }
    }

    @Test
    fun aSlowModelFallsBackToTheStandInBeforeAnyNumbersAreUsed() {
        val phone = Phone()
        phone.questionMs = 600
        model(phone).use { model ->
            assertEquals(RecallChoice.UNMEASURED, model.choiceJson().getString("rung"))
            assertTrue(model.measure(false))
            settle(model)
            val now = model.choiceJson()
            assertEquals(RecallChoice.STAND_IN, now.getString("rung"))
            assertTrue(now.getBoolean("standin_now"))
            assertTrue(now.getJSONObject("bench").getDouble("query_ms") >= 600)
            assertNull(model.embed(listOf("note"), false))
        }
        assertEquals(RecallChoice.STAND_IN, choice().read("test/key")!!.rung)
        model(Phone()).use { again ->
            assertEquals(RecallChoice.STAND_IN, again.choiceJson().getString("rung"))
            assertTrue(again.choiceJson().getBoolean("standin_now"))
            again.start()
            assertFalse(again.measuringNow())
        }
    }

    @Test
    fun aFastModelIsKeptAndTheBenchServesNothing() {
        val phone = Phone()
        model(phone).use { model ->
            model.start()
            settle(model)
            val now = model.choiceJson()
            assertEquals(RecallChoice.ONNX, now.getString("rung"))
            assertFalse(now.getBoolean("standin_now"))
            assertEquals(0L, now.getLong("served"))
            val bench = now.getJSONObject("bench")
            assertTrue(bench.getBoolean("eyes"))
            assertEquals("ready", bench.getString("ears"))
            assertEquals(2, bench.getInt("core"))
            assertEquals(32, bench.getInt("batch"))
            assertNotNull(model.embed(listOf("note"), false))
        }
        assertEquals(RecallChoice.ONNX, choice().read("test/key")!!.rung)
        assertNull(choice().read("other/key"))
    }

    @Test
    fun theBenchWaitsForTheEyesAndEarsThenMeasuresAnyway() {
        val phone = Phone()
        phone.eyesOn = false
        model(phone).use { model ->
            val started = System.nanoTime()
            model.start()
            settle(model)
            assertTrue((System.nanoTime() - started) / 1e6 >= 250)
            assertFalse(model.choiceJson().getJSONObject("bench").getBoolean("eyes"))
        }
    }

    @Test
    fun afterNumbersWereUsedASlowVerdictStopsTheModelButKeepsTheSameNumbers() {
        val phone = Phone()
        model(phone).use { model ->
            assertNotNull(model.embed(listOf("note"), false))
            phone.questionMs = 600
            assertTrue(model.measure(false))
            settle(model)
            val now = model.choiceJson()
            assertEquals(RecallChoice.STAND_IN, now.getString("rung"))
            assertFalse(now.getBoolean("standin_now"))
            assertNull(model.embed(listOf("note"), false))
        }
    }

    @Test
    fun aModelThatWillNotLoadTurnsToTheStandIn() {
        val phone = Phone()
        phone.failLoad = true
        model(phone).use { model ->
            assertNull(model.embed(listOf("note"), false))
            val now = model.choiceJson()
            assertEquals(RecallChoice.FAILED, now.getString("rung"))
            assertTrue(now.getBoolean("standin_now"))
            assertTrue(now.getString("why").contains("broken"))
        }
        assertEquals(RecallChoice.FAILED, choice().read("test/key")!!.rung)
    }

    @Test
    fun withoutTheModelInTheAppItAsksForTheStandInAtOnce() {
        model(Phone(present = false)).use { model ->
            val now = model.choiceJson()
            assertEquals(RecallChoice.MISSING, now.getString("rung"))
            assertTrue(now.getBoolean("standin_now"))
            assertNull(model.embed(listOf("note"), false))
            assertFalse(model.measure(false))
        }
    }

    @Test
    fun closingLetsAWaitingCallerGoAtOnce() {
        val phone = Phone()
        phone.writingNow = true
        val model = model(phone, fast.copy(batchWaitMs = 20_000))
        var rows: Array<FloatArray>? = arrayOf()
        var tookMs = 0.0
        val caller = thread {
            val started = System.nanoTime()
            rows = model.embed(listOf("note"), false)
            tookMs = (System.nanoTime() - started) / 1e6
        }
        Thread.sleep(200)
        model.close()
        caller.join(5_000)
        assertFalse(caller.isAlive)
        assertNull(rows)
        assertTrue("took $tookMs ms", tookMs < 2_000)
        assertNull(model.embed(listOf("note"), true))
    }

    @Test
    fun theJsonDoorPacksLittleEndianFloats() {
        val phone = Phone()
        model(phone).use { model ->
            val bytes = model.embedJson("[\"note\", \"note note\"]", false)
            assertEquals(2 * Pooling.DIM * 4, bytes.size)
            val rows = Pooling.unpack(bytes)
            assertEquals(3 / Math.sqrt(10.0), rows[0][0].toDouble(), 1e-6)
            assertEquals(0, model.embedJson("not json", false).size)
        }
    }
}
