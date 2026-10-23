package nz.pebble.robot.recall

import nz.pebble.robot.llm.LlamaPlan
import java.io.File
import java.util.concurrent.TimeUnit

object LittleCore {
    fun pick(maxFreqs: List<Long>): Int? {
        if (maxFreqs.isEmpty()) return null
        val order = LlamaPlan.ranked(maxFreqs)
        val distinct = maxFreqs.toSet().size > 1
        val (main, sub) = LlamaPlan.cores(maxFreqs)
        val taken = if (distinct) (main + sub).toSet() else emptySet()
        val free = order.filter { it !in taken }.ifEmpty { order }
        val slowest = free.minOf { maxFreqs[it] }
        return free.last { maxFreqs[it] == slowest }
    }

    fun parse(list: String): List<Int>? {
        val text = list.trim()
        if (text.isEmpty()) return null
        val out = ArrayList<Int>()
        for (part in text.split(',')) {
            val bounds = part.trim().split('-')
            val low = bounds[0].trim().toIntOrNull() ?: return null
            val high = (if (bounds.size > 1) bounds[1].trim().toIntOrNull() else low) ?: return null
            if (high < low || high - low > 1024) return null
            for (core in low..high) out += core
        }
        return out
    }

    fun allowed(tid: Int): List<Int>? = try {
        File("/proc/self/task/$tid/status").readLines().firstOrNull { it.startsWith("Cpus_allowed_list:") }?.substringAfter(':')?.let { parse(it) }
    } catch (e: Exception) {
        null
    }

    fun pin(tid: Int, core: Int): String {
        if (core !in 0..62) return "no such core"
        return try {
            val process = ProcessBuilder("taskset", "-p", java.lang.Long.toHexString(1L shl core), tid.toString()).redirectErrorStream(true).start()
            val said = process.inputStream.bufferedReader().use { it.readText() }.trim()
            if (!process.waitFor(PIN_WAIT_S, TimeUnit.SECONDS)) {
                process.destroy()
                return "taskset did not finish"
            }
            if (allowed(tid) == listOf(core)) "" else "taskset said: ${said.take(160)}"
        } catch (e: Exception) {
            "taskset could not run: ${e.message?.take(120)}"
        }
    }

    const val PIN_WAIT_S = 5L
}
