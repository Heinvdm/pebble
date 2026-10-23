package nz.pebble.robot.llm

import java.io.File

object LlamaPlan {
    const val MAIN_PORT = 8080
    const val SUB_PORT = 8081
    const val GB = 1L shl 30
    const val MB = 1L shl 20
    const val WORK = 400 * MB
    const val SERVER_CHECKPOINTS = 32
    const val GUESS_PER_TOKEN = 128L * 1024
    const val BATCH = 128
    const val SMALLEST_BATCH = 32
    val BATCHES = listOf(128, 64, 512)
    const val BATCH_WITHIN = 0.95
    const val DRAFTER_GAIN = 0.85
    const val CANCEL_MS = 2_500L
    const val FREE_WITH_BOTH = 3L * GB / 2

    data class Server(
        val role: String,
        val port: Int,
        val model: File,
        val context: Int,
        val threads: Int,
        val mask: String?,
        val jinja: Boolean,
        val projector: File? = null,
        val cacheMib: Int? = null,
        val swaFull: Boolean = false,
        val cacheType: String = KvCost.F16,
        val step: Int = 0,
        val key: String = "",
        val batch: Int = BATCH,
        val drafter: File? = null,
    )

    data class Rung(val context: Int, val swaFull: Boolean, val cacheType: String, val cacheMib: Int)

    val MAIN_RUNGS = listOf(
        Rung(16384, true, KvCost.F16, 1536),
        Rung(16384, true, KvCost.F16, 768),
        Rung(16384, true, KvCost.Q8, 768),
        Rung(8192, true, KvCost.F16, 1536),
        Rung(8192, true, KvCost.F16, 768),
        Rung(8192, true, KvCost.Q8, 384),
        Rung(6144, true, KvCost.F16, 192),
    )

    val SUB_RUNGS = listOf(
        Rung(2048, false, KvCost.F16, 128),
        Rung(2048, false, KvCost.F16, 32),
    )

    data class Fit(val ok: Boolean, val why: String, val kind: String = "")

    data class Pick(val step: Int, val rung: Rung?, val need: Long, val fit: Fit)

    fun args(s: Server): List<String> {
        val out = mutableListOf(
            "-m", s.model.path,
            "-c", s.context.toString(),
            "--host", "127.0.0.1",
            "--port", s.port.toString(),
            "-t", s.threads.toString(),
            "-np", "1",
            "-b", s.batch.toString(),
            "-ub", s.batch.toString(),
            "--metrics",
            "--no-webui",
        )
        if (s.jinja) out += listOf("--jinja", "--reasoning", "off")
        if (s.projector != null) out += listOf("--mmproj", s.projector.path)
        if (s.drafter != null) out += listOf("--spec-type", "draft-mtp", "-md", s.drafter.path)
        if (s.mask != null) out += listOf("-C", s.mask, "--cpu-strict", "1")
        if (s.swaFull) out += "--swa-full"
        if (s.cacheType != KvCost.F16) out += listOf("-ctk", s.cacheType, "-ctv", s.cacheType)
        if (s.cacheMib != null) out += listOf("--cache-ram", s.cacheMib.toString())
        return out
    }

    fun server(role: String, port: Int, model: File, threads: Pair<Int, String?>, jinja: Boolean, projector: File?, rung: Rung, step: Int, key: String, batch: Int = BATCH, drafter: File? = null): Server =
        Server(role, port, model, rung.context, threads.first, threads.second, jinja, projector, rung.cacheMib, rung.swaFull, rung.cacheType, step, key, batch, drafter)

    fun cacheBytes(kv: KvCost?, rung: Rung, ubatch: Int = BATCH): Long {
        if (kv == null) return rung.context * GUESS_PER_TOKEN
        return kv.cache(rung.context, rung.swaFull, rung.cacheType, ubatch) + kv.checkpoints(rung.context, rung.swaFull, rung.cacheType, SERVER_CHECKPOINTS, ubatch)
    }

    fun need(modelBytes: Long, kv: KvCost?, rung: Rung, ubatch: Int = BATCH): Long = modelBytes + WORK + cacheBytes(kv, rung, ubatch) + rung.cacheMib * MB

    fun rungOf(s: Server): Rung = Rung(s.context, s.swaFull, s.cacheType, s.cacheMib ?: 0)

    fun needOf(s: Server, kv: KvCost?): Long = need(s.model.length() + (s.projector?.length() ?: 0L) + (s.drafter?.length() ?: 0L), kv, rungOf(s), s.batch)

    fun pick(name: String, rungs: List<Rung>, from: Int, modelBytes: Long, kv: KvCost?, totalBytes: Long, availableBytes: Long, alsoLoaded: Long = 0, reserve: Long = 0, ubatch: Int = BATCH): Pick {
        val start = from.coerceIn(0, rungs.size - 1)
        var last = Fit(false, "")
        for (step in start until rungs.size) {
            val needed = need(modelBytes, kv, rungs[step], ubatch)
            val fit = fitsNeed(name, needed, totalBytes, availableBytes, alsoLoaded + reserve)
            if (fit.ok || withinShare(needed + alsoLoaded + reserve, totalBytes)) return Pick(step, rungs[step], needed, fit)
            last = fit
        }
        return Pick(start, null, 0L, last)
    }

    fun ranked(maxFreqs: List<Long>): List<Int> = maxFreqs.indices.sortedWith(compareByDescending<Int> { maxFreqs[it] }.thenByDescending { it })

    fun mask(cores: List<Int>): String? {
        if (cores.isEmpty()) return null
        var bits = 0L
        for (core in cores) if (core in 0..62) bits = bits or (1L shl core)
        return "0x" + java.lang.Long.toHexString(bits).uppercase()
    }

    fun plan(maxFreqs: List<Long>): Pair<Pair<Int, String?>, Pair<Int, String?>> {
        val count = maxFreqs.size
        if (count < 4) return (maxOf(1, count) to null) to (1 to null)
        val distinct = maxFreqs.toSet().size > 1
        val (mainCores, subCores) = cores(maxFreqs)
        return (mainCores.size to if (distinct) mask(mainCores) else null) to (subCores.size to if (distinct) mask(subCores) else null)
    }

    fun cores(maxFreqs: List<Long>): Pair<List<Int>, List<Int>> {
        val order = ranked(maxFreqs)
        val count = order.size
        if (count < 4) return emptyList<Int>() to emptyList()
        return order.take(minOf(4, count - 2)) to order.takeLast(2)
    }

    fun projector(files: List<String>, wanted: String, model: String): String? {
        if (wanted == "none") return null
        if (wanted != "auto") return wanted.takeIf { it in files }
        val candidates = files.filter { it.lowercase().contains("mmproj") && it.lowercase().endsWith(".gguf") }.sorted()
        if (candidates.size <= 1) return candidates.firstOrNull()
        val family = model.lowercase().substringBefore('-')
        val matching = candidates.filter { it.lowercase().contains(family) }
        return (if (matching.isNotEmpty()) matching else candidates).firstOrNull()
    }

    fun drafter(files: List<String>, wanted: String, model: String): String? {
        if (wanted == "none") return null
        if (wanted != "auto") return wanted.takeIf { it in files }
        val candidates = files.filter { name ->
            val low = name.lowercase()
            low.endsWith(".gguf") && !low.contains("mmproj") && name != model && (low.contains("mtp") || low.contains("assistant") || low.contains("draft"))
        }.sorted()
        if (candidates.size <= 1) return candidates.firstOrNull()
        val family = model.lowercase().substringBeforeLast('-').substringBeforeLast('-')
        val matching = candidates.filter { it.lowercase().contains(family) }
        return (if (matching.isNotEmpty()) matching else candidates).firstOrNull()
    }

    fun pickBatch(speeds: Map<Int, Double>): Int? {
        val best = speeds.values.filter { it > 0 }.maxOrNull() ?: return null
        return speeds.filter { it.value >= best * BATCH_WITHIN }.keys.minOrNull()
    }

    fun smallerBatch(batch: Int): Int? = (batch / 2).takeIf { it >= SMALLEST_BATCH }

    fun keepDrafter(withMs: Double?, withoutMs: Double?): Boolean = withMs != null && withoutMs != null && withMs > 0 && withMs <= withoutMs * DRAFTER_GAIN

    fun fitsDisk(bytes: Long, free: Long, margin: Long = GB): Fit {
        if (bytes + margin <= free) return Fit(true, "")
        return Fit(false, "not enough free space: the file needs ${gb(bytes)} and the phone has ${gb(free)} free (keep ${gb(margin)} spare)")
    }

    fun fitsMemory(name: String, modelBytes: Long, totalBytes: Long, availableBytes: Long, alsoLoaded: Long = 0): Fit =
        fitsNeed(name, modelBytes + WORK, totalBytes, availableBytes, alsoLoaded)

    fun withinShare(bytes: Long, totalBytes: Long): Boolean = bytes <= totalBytes * 7 / 10

    fun fitsNeed(name: String, needed: Long, totalBytes: Long, availableBytes: Long, alsoLoaded: Long = 0): Fit {
        if (!withinShare(needed + alsoLoaded, totalBytes)) {
            return Fit(false, "$name needs about ${gb(needed)} of memory and this phone has ${gb(totalBytes)} in all; a model that big would starve Android and Pebble's own brain, so it is not started", ModelFiles.TOO_BIG)
        }
        if (needed > availableBytes + 2 * GB) {
            return Fit(false, "$name needs about ${gb(needed)} of memory and only ${gb(availableBytes)} is free right now; it is tried again later", ModelFiles.NO_ROOM_NOW)
        }
        return Fit(true, "")
    }

    fun gb(bytes: Long): String = String.format(java.util.Locale.ROOT, "%.1f GB", bytes.toDouble() / GB)
}
