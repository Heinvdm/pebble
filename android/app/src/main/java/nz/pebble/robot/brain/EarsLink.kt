package nz.pebble.robot.brain

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
import android.os.Process
import android.os.RemoteException
import android.os.SystemClock
import android.util.Log
import nz.pebble.robot.keeper.Backoff
import org.json.JSONObject

class EarsLink(
    private val context: Context,
    private val hasModels: Boolean,
    private val emit: (JSONObject) -> Unit,
    private val changed: () -> Unit,
) : AudioSink {
    private val thread = HandlerThread("pebble-ears-client").also { it.start() }
    private val handler = Handler(thread.looper)
    private val incoming = Messenger(Handler(thread.looper) { msg ->
        receive(msg)
        true
    })
    private val settings = JSONObject()
    private val lock = Object()
    private val held = HeldSound()
    private val relay = SegmentRelay()
    private val backoff = Backoff(RESTART_STEPS_MS, HEALTHY_MS)
    @Volatile private var remote: Messenger? = null
    @Volatile private var listening = false
    @Volatile private var bound = false
    @Volatile private var shut = false
    @Volatile private var state = JSONObject()
    @Volatile private var holding = true
    @Volatile private var choked = false
    @Volatile private var chokedAt = 0.0
    @Volatile private var replayFrom = Double.NEGATIVE_INFINITY
    @Volatile private var heardSinceConnect = false
    @Volatile private var connectedAt = 0L
    @Volatile private var lastStateAt = 0L
    @Volatile private var restartAt = 0L
    @Volatile private var restingUntil = 0L
    private val deathTimes = ArrayDeque<Long>()
    @Volatile var deaths = 0
        private set
    @Volatile var kills = 0
        private set
    @Volatile var lostSegments = 0
        private set
    @Volatile var replayedS = 0.0
        private set
    @Volatile var missedS = 0.0
        private set
    @Volatile var chokes = 0
        private set
    @Volatile var problem = ""
        private set

    private val connection = object : ServiceConnection {
        override fun onServiceConnected(name: ComponentName, service: IBinder) {
            handler.post { connected(Messenger(service)) }
        }

        override fun onServiceDisconnected(name: ComponentName) {
            handler.post { died("the ears process stopped") }
        }

        override fun onBindingDied(name: ComponentName) {
            handler.post {
                if (remote != null) died("the link to the ears process broke")
                unbind()
                scheduleRestart()
            }
        }
    }

    private val watch = object : Runnable {
        override fun run() {
            check()
            if (!shut) handler.postDelayed(this, WATCH_MS)
        }
    }

    init {
        handler.postDelayed(watch, WATCH_MS)
    }

    val available: Boolean
        get() = hasModels && !resting() && state.optBoolean("available", true)

    val ready: Boolean
        get() = remote != null && state.optBoolean("ready", false)

    val mode: String
        get() = if (remote != null) state.optString("mode", HearingSettings.MODE_OFF) else HearingSettings.MODE_OFF

    fun unavailableBecause(): String = when {
        !hasModels -> "this build has no speech models"
        resting() -> problem
        else -> state.optString("unavailable_because", "")
    }

    fun phase(): String = when {
        !hasModels -> "none"
        resting() -> "resting"
        remote == null && deaths > 0 -> "restarting"
        remote == null -> "starting"
        !state.optBoolean("ready", false) -> "loading"
        else -> "ready"
    }

    fun bind() {
        handler.post { bindNow() }
    }

    fun configure(text: String) {
        synchronized(settings) { Ears.merge(settings, text) }
        post(config(text))
    }

    fun start() {
        if (!listening) {
            synchronized(lock) {
                held.clear()
                replayFrom = if (holding) Double.NEGATIVE_INFINITY else now()
            }
        }
        listening = true
        post(Message.obtain(null, Ears.MSG_LISTEN, 1, 0))
        handler.post { bindNow() }
    }

    fun stop() {
        listening = false
        synchronized(lock) { held.clear() }
        post(Message.obtain(null, Ears.MSG_LISTEN, 0, 0))
    }

    fun endProcessForTest() {
        post(Message.obtain(null, Ears.MSG_EXIT))
    }

    override fun onAudio(pcm: ShortArray, count: Int, speaking: Boolean) {
        if (!listening) return
        val at = now()
        synchronized(lock) {
            held.add(pcm, count, at, speaking)
            if (holding || choked) return
            val target = remote ?: return
            if (!send(target, audio(pcm.copyOf(count), speaking, at))) {
                choked = true
                chokedAt = at - count.toDouble() / Microphone.RATE
                chokes++
                Log.w(TAG, "the ears process is not taking sound; holding it until it does")
            }
        }
    }

    fun info(): JSONObject = JSONObject(state.toString())
        .put("process", "ears")
        .put("phase", phase())
        .put("connected", remote != null)
        .put("deaths", deaths)
        .put("ended_stuck", kills)
        .put("restart_in_s", if (restartAt > 0L) Math.round((restartAt - SystemClock.elapsedRealtime()) / 100.0) / 10.0 else 0.0)
        .put("holding", holding && listening)
        .put("held_s", Math.round(synchronized(lock) { held.heldS } * 10) / 10.0)
        .put("replayed_s", Math.round(replayedS * 10) / 10.0)
        .put("missed_s", Math.round(missedS * 10) / 10.0)
        .put("lost_segments", lostSegments)
        .put("choked", choked)
        .put("chokes", chokes)
        .put("resting", resting())
        .put("link_problem", problem)

    fun shutdown() {
        listening = false
        shut = true
        handler.post {
            unbind()
            handler.removeCallbacksAndMessages(null)
            thread.quitSafely()
        }
    }

    private fun now(): Double = System.nanoTime() / 1e9

    private fun bindNow() {
        if (bound || shut || restartAt > 0L || resting()) return
        bound = try {
            context.bindService(Intent(context, EarsService::class.java), connection, Context.BIND_AUTO_CREATE or Context.BIND_IMPORTANT)
        } catch (e: Exception) {
            problem = "the ears process would not start: ${e.message}"
            false
        }
        if (!bound) {
            if (problem.isEmpty()) problem = "the ears process would not start"
            scheduleRestart()
        }
    }

    private fun unbind() {
        if (!bound) return
        bound = false
        remote = null
        try {
            context.unbindService(connection)
        } catch (e: Exception) {
            Log.d(TAG, "the ears were not bound")
        }
    }

    private fun config(text: String): Message = Message.obtain(null, Ears.MSG_CONFIG).apply { data = Bundle().apply { putString(Ears.KEY_JSON, text) } }

    private fun audio(pcm: ShortArray, speaking: Boolean, at: Double): Message = Message.obtain(null, Ears.MSG_AUDIO).apply {
        data = Bundle().apply {
            putShortArray(Ears.KEY_PCM, pcm)
            putBoolean(Ears.KEY_SPEAKING, speaking)
            putDouble(Ears.KEY_AT, at)
        }
    }

    private fun send(target: Messenger, message: Message): Boolean = try {
        target.send(message)
        true
    } catch (e: RemoteException) {
        false
    }

    private fun post(message: Message) {
        val target = remote ?: return
        send(target, message)
    }

    private fun connected(target: Messenger) {
        if (shut) return
        remote = target
        connectedAt = SystemClock.elapsedRealtime()
        lastStateAt = connectedAt
        heardSinceConnect = false
        relay.restarted()
        state = JSONObject()
        choked = false
        send(target, Message.obtain(null, Ears.MSG_HELLO).apply { replyTo = incoming })
        val known = synchronized(settings) { settings.toString() }
        if (known != "{}") send(target, config(known))
        send(target, Message.obtain(null, Ears.MSG_LISTEN, if (listening) 1 else 0, 0))
        synchronized(lock) {
            if (listening) {
                val from = replayFrom
                val oldest = held.oldest
                if (from.isFinite() && oldest.isFinite() && from < oldest) {
                    missedS += oldest - from
                    replayFrom = oldest
                }
                var replayed = 0
                for (piece in held.since(from)) {
                    if (!send(target, audio(piece.pcm, piece.speaking, piece.at))) break
                    replayed += piece.pcm.size
                }
                if (deaths > 0) {
                    replayedS += replayed.toDouble() / Microphone.RATE
                    Log.i(TAG, "the ears are back: ${Math.round(replayed * 100.0 / Microphone.RATE) / 100.0} s of held sound sent first")
                }
            }
            holding = false
        }
        if (deaths > 0 && !resting()) problem = ""
        changed()
    }

    private fun receive(msg: Message) {
        val text = msg.data?.getString(Ears.KEY_JSON) ?: return
        val o = try {
            JSONObject(text)
        } catch (e: Exception) {
            return
        }
        when (msg.what) {
            Ears.MSG_EVENT -> emit(relay.pass(o))
            Ears.MSG_STATE -> {
                val before = available
                val wasReady = state.optBoolean("ready", false)
                state = o
                lastStateAt = SystemClock.elapsedRealtime()
                val isReady = o.optBoolean("ready", false)
                if (isReady) {
                    heardSinceConnect = true
                    backoff.healthy(lastStateAt, connectedAt)
                }
                if (choked) unchoke()
                if (before != available || wasReady != isReady) changed()
            }
        }
    }

    private fun unchoke() {
        synchronized(lock) {
            val target = remote ?: return
            if (!choked || holding) return
            for (piece in held.since(chokedAt)) {
                if (!send(target, audio(piece.pcm, piece.speaking, piece.at))) return
                chokedAt = piece.at
            }
            choked = false
        }
        Log.i(TAG, "the ears process takes sound again")
    }

    private fun check() {
        if (remote == null || shut) return
        val now = SystemClock.elapsedRealtime()
        val stalled = state.optDouble("stalled_s", 0.0)
        val why = when {
            now - lastStateAt > STUCK_MS -> "the ears process stopped answering for ${(now - lastStateAt) / 1000} s"
            stalled > STUCK_MS / 1000.0 -> "the ears process stopped hearing for ${stalled.toInt()} s"
            else -> return
        }
        val pid = state.optInt("pid", 0)
        if (pid <= 0 || pid == Process.myPid()) return
        kills++
        Log.w(TAG, "$why; ending it so that it starts again")
        Process.killProcess(pid)
    }

    private fun died(why: String) {
        if (remote == null && !bound) return
        val diedAt = now()
        remote = null
        deaths++
        synchronized(lock) {
            holding = true
            if (heardSinceConnect) {
                val from = relay.replayFrom(diedAt, state.optString("mode") == HearingSettings.MODE_WORDS)
                replayFrom = if (choked) minOf(from, chokedAt) else from
            }
            choked = false
        }
        relay.lost(diedAt)?.let {
            lostSegments++
            emit(it)
        }
        state = JSONObject(state.toString()).put("ready", false)
        unbind()
        val stamp = SystemClock.elapsedRealtime()
        val tooMany = synchronized(deathTimes) {
            deathTimes.addLast(stamp)
            while (deathTimes.isNotEmpty() && stamp - deathTimes.first() > DEATH_WINDOW_MS) deathTimes.removeFirst()
            (deathTimes.size >= MAX_DEATHS).also { if (it) deathTimes.clear() }
        }
        if (tooMany) {
            rest(stamp)
        } else {
            scheduleRestart()
            problem = "$why; it starts again in ${Math.round((restartAt - stamp) / 100.0) / 10.0} s, and what is said meanwhile is heard when it is back"
            Log.w(TAG, problem)
        }
        changed()
    }

    private fun scheduleRestart() {
        if (shut || restartAt > 0L || resting()) return
        val delay = backoff.next()
        restartAt = SystemClock.elapsedRealtime() + delay
        handler.postDelayed({
            restartAt = 0L
            bindNow()
        }, delay)
    }

    private fun rest(stamp: Long) {
        restingUntil = stamp + REST_MS
        problem = "the speech models stopped their process $MAX_DEATHS times in ${DEATH_WINDOW_MS / 60_000} minutes, so Pebble listens with Android's own recognizer for ${REST_MS / 60_000} minutes"
        Log.w(TAG, problem)
        synchronized(lock) { held.clear() }
        handler.postDelayed({
            problem = ""
            changed()
            bindNow()
        }, REST_MS)
    }

    private fun resting(): Boolean = SystemClock.elapsedRealtime() < restingUntil

    companion object {
        const val TAG = "PebbleEarsLink"
        const val MAX_DEATHS = 5
        const val DEATH_WINDOW_MS = 10 * 60_000L
        const val REST_MS = 30 * 60_000L
        const val HEALTHY_MS = 2 * 60_000L
        const val STUCK_MS = 20_000L
        const val WATCH_MS = 5_000L
        val RESTART_STEPS_MS = longArrayOf(1_000, 2_000, 5_000, 10_000, 30_000)
    }
}
