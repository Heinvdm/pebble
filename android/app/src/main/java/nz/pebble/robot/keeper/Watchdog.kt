package nz.pebble.robot.keeper

class Backoff(private val steps: LongArray = longArrayOf(2_000, 5_000, 10_000, 30_000, 60_000), private val healthyMs: Long = 600_000) {
    private var failures = 0
    private var since = 0L

    fun next(): Long {
        val delay = steps[failures.coerceAtMost(steps.size - 1)]
        failures++
        return delay
    }

    fun healthy(now: Long, startedAt: Long) {
        if (startedAt > 0 && now - startedAt >= healthyMs && failures != 0) failures = 0
        since = now
    }

    val count: Int get() = failures
}

enum class Want { RUN, PAUSE, HOLD }

data class Seen(
    val now: Long,
    val want: Want,
    val alive: Boolean,
    val startedAt: Long,
    val heartbeatAt: Long,
    val exitCode: Int?,
    val exitAt: Long,
    val charging: Boolean,
    val resting: Boolean,
)

sealed class Act {
    object Nothing : Act()
    data class Start(val why: String) : Act()
    data class Kill(val why: String) : Act()
    data class Stop(val why: String) : Act()
    data class Rest(val why: String) : Act()
    data class Wait(val why: String) : Act()
}

class Watchdog(
    private val graceMs: Long = 180_000,
    private val hangMs: Long = 60_000,
    private val sealedRetryMs: Long = 600_000,
    private val startingMs: Long = 20_000,
    private val backoff: Backoff = Backoff(),
) {
    private var restartAt = -1L
    private var handledExit = 0L
    private var planned = false
    var lastWhy = ""
        private set
    var restarts = 0
        private set

    fun planned() {
        planned = true
        restartAt = -1
    }

    private fun delay(): Long {
        if (planned) {
            planned = false
            return 0
        }
        return backoff.next()
    }

    fun decide(s: Seen): Act {
        val act = choose(s)
        if (act is Act.Kill || (act is Act.Start && s.startedAt > 0)) restarts++
        lastWhy = when (act) {
            is Act.Start -> act.why
            is Act.Kill -> act.why
            is Act.Stop -> act.why
            is Act.Rest -> act.why
            is Act.Wait -> act.why
            Act.Nothing -> lastWhy
        }
        return act
    }

    private fun choose(s: Seen): Act {
        if (s.want == Want.PAUSE) return if (s.alive) Act.Stop("paused by the owner") else Act.Nothing
        if (s.want == Want.HOLD) return if (s.alive) Act.Stop("held while the owner changes a setting") else Act.Nothing
        if (s.alive) {
            restartAt = -1
            backoff.healthy(s.now, s.startedAt)
            val since = maxOf(s.startedAt, s.heartbeatAt)
            if (s.startedAt > 0 && s.now - s.startedAt > graceMs && s.now - since > hangMs) {
                return Act.Kill("the brain stopped answering (no heartbeat for ${(s.now - since) / 1000} s)")
            }
            return Act.Nothing
        }
        if (s.startedAt > 0 && s.now - s.startedAt < startingMs && s.exitAt < s.startedAt) return Act.Wait("the brain is starting")
        if (s.exitCode != null && s.exitAt > handledExit) {
            handledExit = s.exitAt
            when (s.exitCode) {
                EXIT_SHUTDOWN -> return Act.Rest("the battery ran low, so Pebble rests until it is charging")
                EXIT_SEALED -> {
                    restartAt = s.now + sealedRetryMs
                    return Act.Wait("the sealed self cannot be opened on this phone; recover it in the admin screen")
                }
                else -> restartAt = s.now + delay()
            }
        }
        if (s.resting) return if (s.charging) Act.Start("charging again after resting") else Act.Wait("resting until it is charging")
        if (s.startedAt == 0L) return Act.Start("starting the brain")
        if (restartAt < 0) restartAt = s.now + delay()
        if (s.now < restartAt) return Act.Wait("waiting ${(restartAt - s.now + 999) / 1000} s before starting the brain again")
        restartAt = -1
        return Act.Start("the brain was not running")
    }

    companion object {
        const val EXIT_SHUTDOWN = 3
        const val EXIT_SEALED = 4
    }
}
