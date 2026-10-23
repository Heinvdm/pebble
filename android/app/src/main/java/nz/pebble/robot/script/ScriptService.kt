package nz.pebble.robot.script

import android.app.Service
import android.content.Intent
import android.os.Bundle
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.Message
import android.os.Messenger
import android.os.Process
import android.os.RemoteException
import android.os.SystemClock
import java.util.concurrent.CountDownLatch

open class ScriptService : Service() {
    private lateinit var handler: Handler
    private lateinit var messenger: Messenger
    private lateinit var host: ScriptHost
    private val guard = Guard(DEFAULT_MEMORY_MB.toLong(), SELF_STOP_MS, { heapMb() }, { SystemClock.elapsedRealtime() }, { Runtime.getRuntime().gc() })
    @Volatile private var pending: Pending? = null
    @Volatile private var watching = true

    private class Pending(val back: Messenger, val seq: Int)

    override fun onCreate() {
        super.onCreate()
        host = ScriptHost(pong = { pong() }, extra = { op, message -> extra(op, message) })
        val ready = CountDownLatch(1)
        Thread(null, {
            Looper.prepare()
            handler = Handler(Looper.myLooper()!!) { msg ->
                receive(msg)
                true
            }
            ready.countDown()
            Looper.loop()
        }, "pebble-script", STACK_BYTES).start()
        ready.await()
        messenger = Messenger(handler)
        Thread({ watch() }, "pebble-script-watch").apply { isDaemon = true }.start()
    }

    override fun onBind(intent: Intent): IBinder {
        guard.ceilingMb = intent.getIntExtra(EXTRA_MEMORY_MB, DEFAULT_MEMORY_MB).coerceIn(MIN_MEMORY_MB, MAX_MEMORY_MB).toLong()
        return messenger.binder
    }

    override fun onUnbind(intent: Intent): Boolean {
        end()
        return false
    }

    protected open fun extra(op: String, message: Map<*, *>): Map<String, Any?>? = null

    private fun pong(): Map<String, Any?> = linkedMapOf(
        "limited" to true,
        "isolated" to Process.isIsolated(),
        "pid" to Process.myPid().toLong(),
        "uid" to Process.myUid().toLong(),
        "memory_mb" to guard.ceilingMb,
        "heap_mb" to heapMb(),
        "self_stop_s" to SELF_STOP_MS / 1000L,
    )

    private fun receive(msg: Message) {
        if (msg.what != MSG_LINE) return
        val back = msg.replyTo ?: return
        val line = msg.data?.getString(KEY_LINE) ?: return
        val pendingNow = Pending(back, msg.arg1)
        pending = pendingNow
        guard.begin()
        var answer: String?
        var die = false
        try {
            answer = host.handle(line)
        } catch (full: OutOfMemoryError) {
            answer = Json.write(crash(host.lastId, "limit", "size", "it used too much memory"))
            die = true
        }
        guard.end()
        pending = null
        if (guard.overMemory()) {
            answer = Json.write(crash(host.lastId, "limit", "size", "it used too much memory"))
            die = true
        }
        if (answer != null) send(back, msg.arg1, answer)
        if (die || host.quit) end()
    }

    private fun watch() {
        while (watching) {
            try {
                Thread.sleep(WATCH_MS)
            } catch (e: InterruptedException) {
                return
            }
            val why = guard.check() ?: continue
            val now = pending
            if (now != null) {
                val message = if (why == Guard.MEMORY) crash(host.lastId, "limit", "size", "it used too much memory") else crash(host.lastId, "limit", "time", "it computed for too long without stopping, so its process was stopped")
                send(now.back, now.seq, Json.write(message))
            }
            end()
        }
    }

    private fun send(back: Messenger, seq: Int, line: String) {
        try {
            back.send(Message.obtain(null, MSG_ANSWER, seq, 0).apply { data = Bundle().apply { putString(KEY_LINE, line) } })
        } catch (e: RemoteException) {
            end()
        }
    }

    private fun end() {
        watching = false
        Process.killProcess(Process.myPid())
    }

    class Guard(var ceilingMb: Long, private val stopMs: Long, private val heap: () -> Long, private val clock: () -> Long, private val collect: () -> Unit = {}) {
        @Volatile private var since = 0L

        fun begin() {
            since = clock()
        }

        fun end() {
            since = 0L
        }

        fun overMemory(): Boolean {
            if (heap() <= ceilingMb) return false
            collect()
            return heap() > ceilingMb
        }

        fun check(): String? {
            if (overMemory()) return MEMORY
            val started = since
            if (started != 0L && clock() - started > stopMs) return SILENT
            return null
        }

        companion object {
            const val MEMORY = "memory"
            const val SILENT = "silent"
        }
    }

    companion object {
        const val MSG_LINE = 1
        const val MSG_ANSWER = 2
        const val KEY_LINE = "line"
        const val EXTRA_MEMORY_MB = "memory_mb"
        const val DEFAULT_MEMORY_MB = 64
        const val MIN_MEMORY_MB = 16
        const val MAX_MEMORY_MB = 256
        const val SELF_STOP_MS = 5_000L
        const val WATCH_MS = 100L
        const val STACK_BYTES = 16L * 1024L * 1024L

        fun heapMb(): Long {
            val runtime = Runtime.getRuntime()
            return (runtime.totalMemory() - runtime.freeMemory()) / (1024L * 1024L)
        }

        fun crash(id: String, kind: String, what: String, text: String): Map<String, Any?> = linkedMapOf("id" to id, "crash" to kind, "what" to what, "line" to 0L, "text" to text)
    }
}
