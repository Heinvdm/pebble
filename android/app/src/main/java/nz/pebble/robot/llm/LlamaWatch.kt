package nz.pebble.robot.llm

class LlamaWatch(
    private val ports: List<Int> = PORTS,
    private val timeoutMs: Int = TIMEOUT_MS,
    private val freshMs: Long = FRESH_MS,
    private val ask: (Int, Int) -> String? = { port, ms -> LlamaHttp(port).slots(ms) },
) {
    private var at = 0L
    private var last = false
    @Volatile var checks = 0L
        private set

    @Synchronized
    fun writing(): Boolean {
        if (at != 0L && System.nanoTime() - at < freshMs * 1_000_000L) return last
        last = ports.any { port -> ask(port, timeoutMs)?.let { LlamaHttp.writing(it) } ?: false }
        at = System.nanoTime()
        checks++
        return last
    }

    companion object {
        const val TIMEOUT_MS = 400
        const val FRESH_MS = 80L
        val PORTS = listOf(LlamaPlan.MAIN_PORT, LlamaPlan.SUB_PORT, nz.pebble.robot.keeper.KeeperService.BENCH_PORT)
    }
}
