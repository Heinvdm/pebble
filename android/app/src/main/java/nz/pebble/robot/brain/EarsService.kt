package nz.pebble.robot.brain

import android.app.Service
import android.content.Intent
import android.os.Bundle
import android.os.Handler
import android.os.HandlerThread
import android.os.IBinder
import android.os.Message
import android.os.Messenger
import android.os.Process
import android.os.RemoteException
import android.util.Log
import org.json.JSONObject
import kotlin.system.exitProcess

class EarsService : Service() {
    private lateinit var thread: HandlerThread
    private lateinit var handler: Handler
    private lateinit var ears: SherpaEars
    @Volatile private var client: Messenger? = null

    override fun onCreate() {
        super.onCreate()
        thread = HandlerThread("pebble-ears-link", Process.THREAD_PRIORITY_URGENT_AUDIO).also { it.start() }
        handler = Handler(thread.looper) { msg ->
            handle(msg)
            true
        }
        ears = SherpaEars(SpeechModels(this), TurnModel(this)) { event -> send(Ears.MSG_EVENT, event.toString()) }
        ears.onChange = { handler.post { pushState() } }
        handler.postDelayed(object : Runnable {
            override fun run() {
                pushState()
                handler.postDelayed(this, Ears.STATE_EVERY_MS)
            }
        }, Ears.STATE_EVERY_MS)
        Log.i(TAG, "the ears process started (pid ${Process.myPid()})")
    }

    override fun onBind(intent: Intent): IBinder = Messenger(handler).binder

    override fun onUnbind(intent: Intent): Boolean {
        client = null
        ears.stop()
        return false
    }

    private fun handle(msg: Message) {
        when (msg.what) {
            Ears.MSG_HELLO -> {
                client = msg.replyTo
                pushState()
            }
            Ears.MSG_AUDIO -> {
                val data = msg.data
                val pcm = data.getShortArray(Ears.KEY_PCM) ?: return
                ears.hear(pcm, pcm.size, data.getBoolean(Ears.KEY_SPEAKING), data.getDouble(Ears.KEY_AT))
            }
            Ears.MSG_CONFIG -> {
                ears.configure(msg.data.getString(Ears.KEY_JSON) ?: "{}")
                pushState()
            }
            Ears.MSG_LISTEN -> {
                if (msg.arg1 == 1) ears.start() else ears.stop()
                pushState()
            }
            Ears.MSG_STATE -> pushState()
            Ears.MSG_EXIT -> {
                Log.w(TAG, "asked to end the ears process")
                exitProcess(255)
            }
        }
    }

    private fun pushState() {
        val state = ears.info()
            .put("available", ears.available())
            .put("unavailable_because", ears.unavailableBecause())
            .put("pid", Process.myPid())
        send(Ears.MSG_STATE, state.toString())
    }

    private fun send(what: Int, text: String) {
        val target = client ?: return
        try {
            target.send(Message.obtain(null, what).apply { data = Bundle().apply { putString(Ears.KEY_JSON, text) } })
        } catch (e: RemoteException) {
            client = null
        }
    }

    override fun onDestroy() {
        ears.stop()
        thread.quitSafely()
        super.onDestroy()
    }

    companion object {
        const val TAG = "PebbleEars"
    }
}

object Ears {
    const val MSG_HELLO = 1
    const val MSG_AUDIO = 2
    const val MSG_CONFIG = 3
    const val MSG_LISTEN = 4
    const val MSG_STATE = 5
    const val MSG_EVENT = 6
    const val MSG_EXIT = 7
    const val KEY_PCM = "pcm"
    const val KEY_AT = "at"
    const val KEY_SPEAKING = "speaking"
    const val KEY_JSON = "json"
    const val STATE_EVERY_MS = 5_000L

    fun merge(into: JSONObject, text: String): JSONObject {
        val o = try {
            JSONObject(text)
        } catch (e: Exception) {
            return into
        }
        for (key in o.keys()) into.put(key, o.get(key))
        return into
    }
}
