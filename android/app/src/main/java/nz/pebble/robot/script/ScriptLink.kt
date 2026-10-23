package nz.pebble.robot.script

import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.ServiceConnection
import android.os.Bundle
import android.os.Handler
import android.os.HandlerThread
import android.os.IBinder
import android.os.Message
import android.os.Messenger
import android.os.RemoteException
import android.os.SystemClock
import android.util.Log
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executor
import java.util.concurrent.LinkedBlockingQueue
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.atomic.AtomicLong

class ScriptLink(context: Context, private val service: Class<out ScriptService> = ScriptService::class.java) {
    private val context = context.applicationContext ?: context
    private val thread = HandlerThread("pebble-script-link").also { it.start() }
    private val handler = Handler(thread.looper)
    private val executor = Executor { handler.post(it) }
    private val links = ConcurrentHashMap<String, Link>()
    private val counter = AtomicLong()
    private val stamp = SystemClock.elapsedRealtime().toString(36)
    private val opened = AtomicLong()
    private val timeouts = AtomicLong()
    private val deaths = AtomicLong()
    @Volatile private var lastProblem = ""

    private inner class Link(val id: String) : ServiceConnection {
        @Volatile var remote: Messenger? = null
        @Volatile var binder: IBinder? = null
        @Volatile var dead = false
        @Volatile var pid = 0L
        val connected = CountDownLatch(1)
        val answers = LinkedBlockingQueue<Pair<Int, String>>()
        val seq = AtomicInteger()
        val incoming = Messenger(Handler(thread.looper) { msg ->
            if (msg.what == ScriptService.MSG_ANSWER) answers.add(msg.arg1 to (msg.data?.getString(ScriptService.KEY_LINE) ?: ""))
            true
        })
        private val death = IBinder.DeathRecipient { gone() }

        fun gone() {
            dead = true
            answers.add(-1 to DIED)
        }

        override fun onServiceConnected(name: ComponentName, service: IBinder) {
            try {
                service.linkToDeath(death, 0)
            } catch (e: RemoteException) {
                gone()
            }
            binder = service
            remote = Messenger(service)
            connected.countDown()
        }

        override fun onServiceDisconnected(name: ComponentName) {
            gone()
        }

        override fun onBindingDied(name: ComponentName) {
            gone()
        }

        override fun onNullBinding(name: ComponentName) {
            gone()
            connected.countDown()
        }
    }

    fun open(memoryMb: Int): String {
        val id = "script_${stamp}_${counter.incrementAndGet()}"
        val link = Link(id)
        val intent = Intent(context, service).putExtra(ScriptService.EXTRA_MEMORY_MB, memoryMb)
        val bound = try {
            context.bindIsolatedService(intent, Context.BIND_AUTO_CREATE, id, executor, link)
        } catch (e: Exception) {
            lastProblem = "could not bind: ${e.javaClass.simpleName}"
            Log.w(TAG, "a program's process could not be started", e)
            false
        }
        if (!bound) {
            unbind(link)
            if (lastProblem.isEmpty()) lastProblem = "the system would not start a program's process"
            return ""
        }
        links[id] = link
        if (!link.connected.await(OPEN_WAIT_MS, TimeUnit.MILLISECONDS) || link.remote == null) {
            lastProblem = "a program's process did not start in time"
            close(id)
            return ""
        }
        val pong = try {
            Json.parse(ask(id, "{\"op\":\"ping\"}", OPEN_WAIT_MS)) as? Map<*, *>
        } catch (e: JsonError) {
            null
        }
        if (pong == null || pong["pong"] != true || pong["isolated"] != true) {
            lastProblem = "a program's process was not isolated: $pong"
            Log.e(TAG, lastProblem)
            close(id)
            return ""
        }
        link.pid = (pong["pid"] as? Long) ?: 0L
        opened.incrementAndGet()
        return id
    }

    fun ask(id: String, line: String, waitMs: Long): String {
        val link = links[id] ?: return CLOSED
        if (link.dead) {
            close(id)
            deaths.incrementAndGet()
            return DIED
        }
        if (line.length > LINE_MOST) return "{\"error\":\"line too long\"}"
        val remote = link.remote ?: return CLOSED
        val seq = link.seq.incrementAndGet()
        try {
            remote.send(Message.obtain(null, ScriptService.MSG_LINE, seq, 0).apply {
                replyTo = link.incoming
                data = Bundle().apply { putString(ScriptService.KEY_LINE, line) }
            })
        } catch (e: RemoteException) {
            close(id)
            deaths.incrementAndGet()
            return DIED
        }
        val deadline = SystemClock.elapsedRealtime() + waitMs
        while (true) {
            val left = deadline - SystemClock.elapsedRealtime()
            val answer = if (left > 0) link.answers.poll(left, TimeUnit.MILLISECONDS) else null
            if (answer == null) {
                close(id)
                timeouts.incrementAndGet()
                return TIMEOUT
            }
            if (answer.first == -1) {
                val last = lastWords(link, seq)
                close(id)
                deaths.incrementAndGet()
                return last ?: DIED
            }
            if (answer.first == seq) return answer.second
        }
    }

    private fun lastWords(link: Link, seq: Int): String? {
        val until = SystemClock.elapsedRealtime() + LAST_WORDS_MS
        while (true) {
            val left = until - SystemClock.elapsedRealtime()
            if (left <= 0) return null
            val answer = link.answers.poll(left, TimeUnit.MILLISECONDS) ?: return null
            if (answer.first == seq) return answer.second
        }
    }

    fun close(id: String) {
        val link = links.remove(id) ?: return
        unbind(link)
    }

    fun closeAll() {
        for (id in links.keys.toList()) close(id)
    }

    fun binderOf(id: String): IBinder? = links[id]?.binder

    fun info(): String = Json.write(linkedMapOf(
        "available" to true,
        "running" to links.size.toLong(),
        "opened" to opened.get(),
        "timeouts" to timeouts.get(),
        "deaths" to deaths.get(),
        "problem" to lastProblem,
    ))

    private fun unbind(link: Link) {
        link.dead = true
        try {
            context.unbindService(link)
        } catch (e: IllegalArgumentException) {
            Log.d(TAG, "the program's process was not bound")
        }
    }

    companion object {
        const val TAG = "PebbleScripts"
        const val OPEN_WAIT_MS = 10_000L
        const val LAST_WORDS_MS = 300L
        const val LINE_MOST = 400_000
        const val TIMEOUT = "{\"link\":\"timeout\"}"
        const val DIED = "{\"link\":\"died\"}"
        const val CLOSED = "{\"link\":\"closed\"}"
    }
}
