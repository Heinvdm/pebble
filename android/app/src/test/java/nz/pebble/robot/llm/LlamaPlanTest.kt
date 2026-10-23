package nz.pebble.robot.llm

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder

class LlamaPlanTest {
    @get:Rule
    val folder = TemporaryFolder()

    private val pixel6Pro = listOf(1_803_000L, 1_803_000L, 1_803_000L, 1_803_000L, 2_253_000L, 2_253_000L, 2_802_000L, 2_802_000L)
    private val s22 = listOf(1_785_600L, 1_785_600L, 1_785_600L, 1_785_600L, 2_496_000L, 2_496_000L, 2_496_000L, 2_995_200L)

    @Test
    fun theMainModelGetsTheBigCoresAndTheSmallOneTheLittleCores() {
        for (phone in listOf(pixel6Pro, s22)) {
            val (main, sub) = LlamaPlan.plan(phone)
            assertEquals(4, main.first)
            assertEquals("0xF0", main.second)
            assertEquals(2, sub.first)
            assertEquals("0x3", sub.second)
        }
    }

    @Test
    fun theMainModelGetsTheBigAndMiddleCoresWhereverTheyAreNumbered() {
        val reversed = pixel6Pro.reversed()
        val (main, sub) = LlamaPlan.plan(reversed)
        assertEquals("0xF", main.second)
        assertEquals("0x30", sub.second)
    }

    @Test
    fun equalCoresGetNoMask() {
        val (main, sub) = LlamaPlan.plan(List(8) { 2_000_000L })
        assertNull(main.second)
        assertNull(sub.second)
        assertEquals(2, LlamaPlan.plan(listOf(0L, 0L)).first.first)
    }

    @Test
    fun argumentsMatchTheBrainsModelProfiles() {
        val model = File("/m/g.gguf")
        val args = LlamaPlan.args(LlamaPlan.Server("main", 8080, model, 4096, 4, "0xF0", true))
        assertEquals(listOf("-m", model.path, "-c", "4096", "--host", "127.0.0.1", "--port", "8080", "-t", "4", "-np", "1", "-b", "128", "-ub", "128", "--metrics", "--no-webui", "--jinja", "--reasoning", "off", "-C", "0xF0", "--cpu-strict", "1"), args)
        val sub = LlamaPlan.args(LlamaPlan.Server("sub", 8081, File("/m/l.gguf"), 2048, 2, null, false))
        assertFalse("--jinja" in sub)
        assertFalse("--reasoning" in sub)
    }

    @Test
    fun aRungSetsTheWindowTheCacheAndTheSlidingLayers() {
        val model = File("/m/g.gguf")
        val main = LlamaPlan.args(LlamaPlan.server("main", 8080, model, 4 to "0xF0", true, null, LlamaPlan.MAIN_RUNGS[5], 5, "k"))
        assertEquals("8192", main[main.indexOf("-c") + 1])
        assertTrue("--swa-full" in main)
        assertEquals("q8_0", main[main.indexOf("-ctk") + 1])
        assertEquals("q8_0", main[main.indexOf("-ctv") + 1])
        assertEquals("384", main[main.indexOf("--cache-ram") + 1])
        assertEquals(1, main.count { it == "-np" })
        assertEquals("1", main[main.indexOf("-np") + 1])
        val sub = LlamaPlan.args(LlamaPlan.server("sub", 8081, File("/m/l.gguf"), 2 to "0x3", false, null, LlamaPlan.SUB_RUNGS[0], 0, "k"))
        assertFalse("--swa-full" in sub)
        assertFalse("-ctk" in sub)
        assertEquals("128", sub[sub.indexOf("--cache-ram") + 1])
        assertEquals("2048", sub[sub.indexOf("-c") + 1])
    }

    @Test
    fun theCacheCostIsReadFromTheModelFile() {
        val meta = gguf(
            "general.architecture" to "gemma4",
            "gemma4.block_count" to 6L,
            "gemma4.embedding_length" to 2560L,
            "gemma4.attention.head_count" to 8L,
            "gemma4.attention.head_count_kv" to listOf(2L, 2L, 2L, 2L, 2L, 2L),
            "gemma4.attention.key_length" to 512L,
            "gemma4.attention.value_length" to 512L,
            "gemma4.attention.key_length_swa" to 256L,
            "gemma4.attention.value_length_swa" to 256L,
            "gemma4.attention.sliding_window" to 512L,
            "gemma4.attention.sliding_window_pattern" to listOf(true, false, true, true, true, false),
            "gemma4.attention.shared_kv_layers" to 2L,
            "tokenizer.ggml.tokens" to List(3000) { "token$it" },
            "tokenizer.ggml.scores" to List(5000) { 0.5f },
            "general.name" to "made up",
        )
        val file = folder.newFile("made-up.gguf").apply { writeBytes(meta) }
        val read = Gguf.meta(file)
        assertEquals("gemma4", read["general.architecture"])
        assertEquals("made up", read["general.name"])
        assertNull(read["tokenizer.ggml.tokens"])
        val kv = KvCost.read(file)!!
        assertEquals(2048L, kv.fullPerToken)
        assertEquals(3072L, kv.swaPerToken)
        assertEquals(512, kv.window)
        assertEquals((2048L + 3072L) * 8192 * 2, kv.cache(8192, true, KvCost.F16))
        assertEquals((2048L * 8192 + 3072L * 768) * 2, kv.cache(8192, false, KvCost.F16))
        assertEquals((2048L * 8192 + 3072L * 1024) * 2, kv.cache(8192, false, KvCost.F16, 512))
        assertEquals((2048L * 8192 + 3072L * 768) * 2, kv.cache(8192, false, KvCost.F16, 64))
        assertEquals(3072L * 768 * 2 * 32, kv.checkpoints(8192, false, KvCost.F16, 32))
        assertEquals(3072L * 1024 * 2 * 32, kv.checkpoints(8192, false, KvCost.F16, 32, 512))
        assertEquals(0L, kv.checkpoints(8192, true, KvCost.F16, 32))
        assertTrue(kv.cache(8192, true, KvCost.Q8) < kv.cache(8192, true, KvCost.F16) * 6 / 10)
        assertNull(KvCost.read(folder.newFile("not-a-model.gguf").apply { writeText("hello") }))
    }

    @Test
    fun gemma4E4BCostsWhatItsConfigSays() {
        val pattern = List(42) { it % 6 < 5 }
        val kv = KvCost.of(Gguf.read(ByteArrayInputStream(gguf(
            "general.architecture" to "gemma4",
            "gemma4.block_count" to 42L,
            "gemma4.embedding_length" to 2560L,
            "gemma4.attention.head_count" to 8L,
            "gemma4.attention.head_count_kv" to 2L,
            "gemma4.attention.key_length" to 512L,
            "gemma4.attention.value_length" to 512L,
            "gemma4.attention.key_length_swa" to 256L,
            "gemma4.attention.value_length_swa" to 256L,
            "gemma4.attention.sliding_window" to 512L,
            "gemma4.attention.sliding_window_pattern" to pattern,
            "gemma4.attention.shared_kv_layers" to 18L,
        ))))!!
        assertEquals(4L * 2 * 1024, kv.fullPerToken)
        assertEquals(20L * 2 * 512, kv.swaPerToken)
        assertEquals(448L * LlamaPlan.MB, kv.cache(8192, true, KvCost.F16))
    }

    @Test
    fun thePhonePicksTheHighestRungThatLeavesRoomForTheSmallModel() {
        val gemma = KvCost(8192, 20480, 512)
        val model = 4_977_171_584L + 990_372_672L
        val small = KvCost(1024, 0, 0)
        val subFloor = LlamaPlan.need(250_000_000L, small, LlamaPlan.SUB_RUNGS.last())
        val gib = LlamaPlan.GB
        val roomy = LlamaPlan.pick("gemma", LlamaPlan.MAIN_RUNGS, 0, model, gemma, 113 * gib / 10, 8 * gib, 0, subFloor)
        assertEquals(2, roomy.step)
        assertEquals(LlamaPlan.Rung(16384, true, KvCost.Q8, 768), roomy.rung)
        assertTrue(roomy.fit.ok)
        val tighter = LlamaPlan.pick("gemma", LlamaPlan.MAIN_RUNGS, 0, model, gemma, 110 * gib / 10, 8 * gib, 0, subFloor)
        assertEquals(5, tighter.step)
        assertEquals(LlamaPlan.Rung(8192, true, KvCost.Q8, 384), tighter.rung)
        val big = LlamaPlan.pick("gemma", LlamaPlan.MAIN_RUNGS, 0, model, gemma, 16 * gib, 12 * gib, 0, subFloor)
        assertEquals(0, big.step)
        val stored = LlamaPlan.pick("gemma", LlamaPlan.MAIN_RUNGS, 3, model, gemma, 16 * gib, 12 * gib, 0, subFloor)
        assertEquals(3, stored.step)
        assertEquals(8192, stored.rung?.context)
        val busy = LlamaPlan.pick("gemma", LlamaPlan.MAIN_RUNGS, 0, model, gemma, 16 * gib, gib, 0, subFloor)
        assertEquals(0, busy.step)
        assertFalse(busy.fit.ok)
        assertTrue(busy.fit.why.contains("tried again later"))
        val tiny = LlamaPlan.pick("gemma", LlamaPlan.MAIN_RUNGS, 0, model, gemma, 8 * gib, 6 * gib, 0, subFloor)
        assertNull(tiny.rung)
        assertTrue(tiny.fit.why.contains("not started"))
        val main = LlamaPlan.server("main", 8080, File("/m/g.gguf"), 4 to null, true, null, LlamaPlan.MAIN_RUNGS[1], 1, "k")
        assertEquals(LlamaPlan.MAIN_RUNGS[1], LlamaPlan.rungOf(main))
        assertEquals(LlamaPlan.need(0L, gemma, LlamaPlan.MAIN_RUNGS[1]), LlamaPlan.needOf(main, gemma))
        assertTrue(LlamaPlan.need(model, null, LlamaPlan.MAIN_RUNGS[3]) > LlamaPlan.need(model, gemma, LlamaPlan.MAIN_RUNGS[3]))
    }

    @Test
    fun aTwelveGigabytePhoneWithoutTheSmallModelGetsTheBigWindow() {
        val gemma = KvCost(8192, 20480, 512)
        val model = 4_977_171_584L + 990_372_672L
        val gib = LlamaPlan.GB
        for (total in listOf(113 * gib / 10, 110 * gib / 10)) {
            val pick = LlamaPlan.pick("gemma", LlamaPlan.MAIN_RUNGS, 0, model, gemma, total, 8 * gib)
            assertEquals(1, pick.step)
            assertEquals(LlamaPlan.Rung(16384, true, KvCost.F16, 768), pick.rung)
            assertTrue(pick.fit.ok)
        }
        val sixteen = LlamaPlan.pick("gemma", LlamaPlan.MAIN_RUNGS, 0, model, gemma, 16 * gib, 12 * gib)
        assertEquals(LlamaPlan.Rung(16384, true, KvCost.F16, 1536), sixteen.rung)
        assertEquals(LlamaPlan.need(0L, gemma, LlamaPlan.MAIN_RUNGS[0]) - LlamaPlan.need(0L, gemma, LlamaPlan.MAIN_RUNGS[3]), 448L * LlamaPlan.MB)
        val args = LlamaPlan.args(LlamaPlan.server("main", 8080, File("/m/g.gguf"), 4 to null, true, null, LlamaPlan.MAIN_RUNGS[1], 1, "k"))
        assertEquals("16384", args[args.indexOf("-c") + 1])
        assertTrue("--swa-full" in args)
        assertFalse("-ctk" in args)
        assertEquals("768", args[args.indexOf("--cache-ram") + 1])
    }

    @Test
    fun theChoiceIsKeptPerPhoneAndModelAndForgotten() {
        val model = folder.newFile("g.gguf").apply { writeBytes(ByteArray(10)) }
        val choice = LlamaChoice(File(folder.root, "llama-main.json"))
        val key = LlamaChoice.key(7, "Pixel 6 Pro", model, null)
        assertNull(choice.step(key))
        assertTrue(choice.keep(key, 2, "it stopped while loading"))
        assertEquals(2, choice.step(key))
        assertNull(choice.step(LlamaChoice.key(8, "Pixel 6 Pro", model, null)))
        choice.forget()
        assertNull(choice.step(key))
    }

    @Test
    fun aCraftedHeaderCannotTakeTheKeeperDown() {
        val huge = folder.newFile("huge.gguf").apply {
            writeBytes(gguf(
                "general.architecture" to "gemma4",
                "gemma4.block_count" to 2_000_000_000L,
                "gemma4.embedding_length" to 2560L,
                "gemma4.attention.head_count" to 8L,
            ))
        }
        assertNull(KvCost.read(huge))
        val bytes = gguf("general.architecture" to "gemma4", "general.name" to "x").copyOf(40)
        val cut = folder.newFile("cut.gguf").apply { writeBytes(bytes) }
        assertNull(KvCost.read(cut))
        val lying = java.nio.ByteBuffer.allocate(64).order(java.nio.ByteOrder.LITTLE_ENDIAN)
            .putInt(0x46554747).putInt(3).putLong(0).putLong(1).putLong(Long.MAX_VALUE / 2).array()
        assertNull(KvCost.read(folder.newFile("lying.gguf").apply { writeBytes(lying) }))
    }

    private fun gguf(vararg pairs: Pair<String, Any>): ByteArray {
        val out = ByteArrayOutputStream()
        fun u32(v: Long) = out.write(ByteBuffer.allocate(4).order(ByteOrder.LITTLE_ENDIAN).putInt(v.toInt()).array())
        fun u64(v: Long) = out.write(ByteBuffer.allocate(8).order(ByteOrder.LITTLE_ENDIAN).putLong(v).array())
        fun f32(v: Float) = out.write(ByteBuffer.allocate(4).order(ByteOrder.LITTLE_ENDIAN).putFloat(v).array())
        fun text(v: String) {
            val bytes = v.toByteArray()
            u64(bytes.size.toLong())
            out.write(bytes)
        }
        fun typed(v: Any) {
            when (v) {
                is String -> {
                    u32(8)
                    text(v)
                }
                is Long -> {
                    u32(4)
                    u32(v)
                }
                is List<*> -> {
                    u32(9)
                    when (val first = v.first()) {
                        is String -> {
                            u32(8)
                            u64(v.size.toLong())
                            v.forEach { text(it as String) }
                        }
                        is Long -> {
                            u32(4)
                            u64(v.size.toLong())
                            v.forEach { u32(it as Long) }
                        }
                        is Boolean -> {
                            u32(7)
                            u64(v.size.toLong())
                            v.forEach { out.write(if (it as Boolean) 1 else 0) }
                        }
                        is Float -> {
                            u32(6)
                            u64(v.size.toLong())
                            v.forEach { f32(it as Float) }
                        }
                        else -> throw IllegalArgumentException("no writer for $first")
                    }
                }
                else -> throw IllegalArgumentException("no writer for $v")
            }
        }
        u32(0x46554747L)
        u32(3)
        u64(0)
        u64(pairs.size.toLong())
        for ((key, value) in pairs) {
            text(key)
            typed(value)
        }
        return out.toByteArray()
    }

    @Test
    fun spaceAndMemoryAreCheckedWithPlainReasons() {
        val gb = LlamaPlan.GB
        assertTrue(LlamaPlan.fitsDisk(5 * gb, 8 * gb).ok)
        val disk = LlamaPlan.fitsDisk(5 * gb, 5 * gb)
        assertFalse(disk.ok)
        assertTrue(disk.why.contains("5.0 GB"))
        assertTrue(LlamaPlan.fitsMemory("gemma", 4 * gb + gb / 2, 8 * gb, 3 * gb).ok)
        assertFalse(LlamaPlan.fitsMemory("big", 7 * gb, 8 * gb, 6 * gb).ok)
        assertFalse(LlamaPlan.fitsMemory("gemma", 4 * gb, 8 * gb, gb / 2).ok)
    }

    @Test
    fun theProjectorIsFoundNextToTheModel() {
        val files = listOf("gemma-4-E4B-it-Q4_K_M.gguf", "LFM2.5-230M-Q8_0.gguf", "mmproj-F16.gguf")
        assertEquals("mmproj-F16.gguf", LlamaPlan.projector(files, "auto", "gemma-4-E4B-it-Q4_K_M.gguf"))
        assertNull(LlamaPlan.projector(files, "none", "gemma-4-E4B-it-Q4_K_M.gguf"))
        assertNull(LlamaPlan.projector(files.take(2), "auto", "gemma-4-E4B-it-Q4_K_M.gguf"))
        val two = listOf("mmproj-SmolVLM-256M-Instruct-Q8_0.gguf", "gemma-4-E4B-it-mmproj.gguf")
        assertEquals("gemma-4-E4B-it-mmproj.gguf", LlamaPlan.projector(two, "auto", "gemma-4-E4B_q4_0-it.gguf"))
        assertEquals("mmproj-F16.gguf", LlamaPlan.projector(files, "mmproj-F16.gguf", "x.gguf"))
        assertNull(LlamaPlan.projector(files, "missing.gguf", "x.gguf"))
        val args = LlamaPlan.args(LlamaPlan.Server("main", 8080, File("/m/g.gguf"), 4096, 4, null, true, File("/m/mmproj-F16.gguf")))
        assertEquals(File("/m/mmproj-F16.gguf").path, args[args.indexOf("--mmproj") + 1])
    }

    @Test
    fun theDrafterIsFoundNextToTheModelAndRunsAsMultiTokenPrediction() {
        val model = "gemma-4-E4B-it-Q4_K_M.gguf"
        val files = listOf(model, "LFM2.5-230M-Q8_0.gguf", "mmproj-F16.gguf", "mtp-gemma-4-E4B-it-Q8_0.gguf")
        assertEquals("mtp-gemma-4-E4B-it-Q8_0.gguf", LlamaPlan.drafter(files, "auto", model))
        assertNull(LlamaPlan.drafter(files, "none", model))
        assertNull(LlamaPlan.drafter(files.take(3), "auto", model))
        val two = listOf(model, "mtp-gemma-4-E2B-it-Q8_0.gguf", "mtp-gemma-4-E4B-it-Q8_0.gguf")
        assertEquals("mtp-gemma-4-E4B-it-Q8_0.gguf", LlamaPlan.drafter(two, "auto", model))
        assertEquals("gemma-4-E4B-it-assistant.gguf", LlamaPlan.drafter(listOf(model, "gemma-4-E4B-it-assistant.gguf"), "auto", model))
        assertNull(LlamaPlan.drafter(files, "missing.gguf", model))
        val drafter = File("/m/mtp-gemma-4-E4B-it-Q8_0.gguf")
        val args = LlamaPlan.args(LlamaPlan.server("main", 8080, File("/m/g.gguf"), 4 to "0xF0", true, null, LlamaPlan.MAIN_RUNGS[1], 1, "k", 64, drafter))
        assertEquals("draft-mtp", args[args.indexOf("--spec-type") + 1])
        assertEquals(drafter.path, args[args.indexOf("-md") + 1])
        assertEquals("64", args[args.indexOf("-b") + 1])
        assertEquals("64", args[args.indexOf("-ub") + 1])
        assertFalse("--spec-type" in LlamaPlan.args(LlamaPlan.server("main", 8080, File("/m/g.gguf"), 4 to "0xF0", true, null, LlamaPlan.MAIN_RUNGS[1], 1, "k")))
    }

    @Test
    fun theDrafterCountsInTheMemoryCheck() {
        val drafter = folder.newFile("mtp.gguf").apply { writeBytes(ByteArray(1000)) }
        val model = folder.newFile("model.gguf").apply { writeBytes(ByteArray(5000)) }
        val gemma = KvCost(8192, 20480, 512)
        val without = LlamaPlan.server("main", 8080, model, 4 to null, true, null, LlamaPlan.MAIN_RUNGS[1], 1, "k")
        val with = LlamaPlan.server("main", 8080, model, 4 to null, true, null, LlamaPlan.MAIN_RUNGS[1], 1, "k", LlamaPlan.BATCH, drafter)
        assertEquals(1000L, LlamaPlan.needOf(with, gemma) - LlamaPlan.needOf(without, gemma))
    }

    @Test
    fun theSmallestBatchWithinFivePercentOfTheBestIsChosen() {
        assertEquals(64, LlamaPlan.pickBatch(mapOf(128 to 30.0, 64 to 29.0, 512 to 30.4)))
        assertEquals(128, LlamaPlan.pickBatch(mapOf(128 to 30.0, 64 to 27.0, 512 to 30.4)))
        assertEquals(512, LlamaPlan.pickBatch(mapOf(128 to 20.0, 64 to 19.0, 512 to 30.0)))
        assertNull(LlamaPlan.pickBatch(emptyMap()))
        assertEquals(32, LlamaPlan.smallerBatch(64))
        assertNull(LlamaPlan.smallerBatch(32))
    }

    @Test
    fun theDrafterStaysOnlyWhenTheHotAnswerIsFifteenPercentFaster() {
        assertTrue(LlamaPlan.keepDrafter(3_400.0, 4_000.0))
        assertFalse(LlamaPlan.keepDrafter(3_500.0, 4_000.0))
        assertFalse(LlamaPlan.keepDrafter(null, 4_000.0))
        assertFalse(LlamaPlan.keepDrafter(3_000.0, null))
    }

    @Test
    fun theBenchResultsAndTheDrafterAreKeptWithTheMemorySetting() {
        val model = folder.newFile("g.gguf").apply { writeBytes(ByteArray(10)) }
        val drafter = folder.newFile("mtp-g.gguf").apply { writeBytes(ByteArray(3)) }
        val choice = LlamaChoice(File(folder.root, "llama-main.json"))
        val key = LlamaChoice.key(7, "Pixel 6 Pro", model, null, drafter)
        assertTrue(key != LlamaChoice.key(7, "Pixel 6 Pro", model, null))
        assertNull(choice.bench(key))
        assertTrue(choice.keepBench(key, 64, LlamaChoice.DRAFTER_ON, org.json.JSONObject().put("write_tps", 6.5)))
        assertTrue(choice.keep(key, 1, "it stopped while loading"))
        assertEquals(64, choice.batch(key))
        assertEquals(LlamaChoice.DRAFTER_ON, choice.drafter(key))
        assertEquals(6.5, choice.bench(key)!!.getDouble("write_tps"), 1e-9)
        assertEquals(1, choice.step(key))
        assertTrue(choice.keepDrafter(key, LlamaChoice.DRAFTER_FAILED, "it stopped while loading"))
        assertEquals(LlamaChoice.DRAFTER_FAILED, choice.drafter(key))
        assertEquals(64, choice.batch(key))
        assertNull(choice.batch(LlamaChoice.key(8, "Pixel 6 Pro", model, null, drafter)))
        choice.forget()
        assertNull(choice.bench(key))
        assertNull(choice.drafter(key))
    }

    @Test
    fun theServersCountersAreRead() {
        val text = "# HELP llamacpp:prompt_tokens_total x\n# TYPE llamacpp:prompt_tokens_total counter\nllamacpp:prompt_tokens_total 1200\nllamacpp:tokens_predicted_seconds_total 12.5\nllamacpp:spec_decode_num_accepted_tokens_per_pos_total{position=\"0\"} 4\n"
        val m = LlamaHttp.parseMetrics(text)
        assertEquals(1200.0, m["prompt_tokens_total"]!!, 1e-9)
        assertEquals(12.5, m["tokens_predicted_seconds_total"]!!, 1e-9)
        assertEquals(2, m.size)
    }

    @Test
    fun theBenchTextIsTheSameEveryTime() {
        assertEquals(BenchText.words(7, 50), BenchText.words(7, 50))
        assertTrue(BenchText.words(7, 50) != BenchText.words(8, 50))
        assertEquals(1850, BenchText.words(7, 1850).split(Regex("[ .]+")).count { it.isNotEmpty() })
    }
}
