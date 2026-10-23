package nz.pebble.robot.keeper

import android.content.Context
import android.util.Log
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import nz.pebble.robot.Paths
import nz.pebble.robot.brain.Bridge
import nz.pebble.robot.brain.KeyVault
import org.json.JSONObject

object SelfOps {
    private const val TAG = "PebbleAdmin"
    private const val LOG_LIMIT = 256L * 1024
    private const val TRACE_LINES = 40
    private val NO_BRIDGE = setOf("cards", "setup_status", "finish_setup", "birth_draw")

    fun python(context: Context, function: String, vararg args: String): String = synchronized(this) {
        try {
            val paths = Paths(context)
            if (!Python.isStarted()) Python.start(AndroidPlatform(context.applicationContext))
            val module = Python.getInstance().getModule("pebble.android.seal")
            val parts: Array<Any> = arrayOf(*args)
            if (function in NO_BRIDGE) module.callAttr(function, *parts).toString()
            else module.callAttr(function, *parts, Bridge(KeyVault(context, paths.wrappedKey), null, null, null, null)).toString()
        } catch (e: Exception) {
            failed(context, function, e)
        }
    }

    fun admin(context: Context, module: String, function: String, vararg args: String): String = synchronized(this) {
        try {
            val paths = Paths(context)
            if (!Python.isStarted()) Python.start(AndroidPlatform(context.applicationContext))
            val parts: Array<Any> = arrayOf(*args)
            Python.getInstance().getModule(module).callAttr(function, *parts, Bridge(KeyVault(context, paths.wrappedKey), null, null, null, null)).toString()
        } catch (e: Exception) {
            failed(context, "$module.$function", e)
        }
    }

    private fun failed(context: Context, what: String, e: Exception): String {
        Log.w(TAG, "$what failed", e)
        try {
            val log = Paths(context).adminLog
            log.parentFile?.mkdirs()
            if (log.length() > LOG_LIMIT) log.delete()
            log.appendText(java.util.Date().toString() + " " + what + ": " + Log.getStackTraceString(e).lines().take(TRACE_LINES).joinToString(System.lineSeparator()) + System.lineSeparator())
        } catch (ignored: Exception) {
            Log.d(TAG, "could not write the admin log")
        }
        return JSONObject().put("ok", false).put("message", "something went wrong inside Pebble's own code, so nothing was changed. \"Admin screen log\" at the bottom of this screen has the details.").toString()
    }

    fun withBrainHeld(context: Context, work: () -> String): String {
        KeeperService.start(context, KeeperService.ACTION_HOLD)
        val deadline = System.currentTimeMillis() + 30_000
        Thread.sleep(1_000)
        while (brainAlive(context) && System.currentTimeMillis() < deadline) Thread.sleep(250)
        return try {
            if (brainAlive(context)) JSONObject().put("ok", false).put("message", "Pebble's brain did not stop, so nothing was changed.").toString() else work()
        } finally {
            KeeperService.start(context, KeeperService.ACTION_RELEASE)
        }
    }

    fun withBrainStopped(context: Context, function: String, vararg args: String): String {
        val paths = Paths(context)
        KeeperService.start(context, KeeperService.ACTION_PAUSE)
        val deadline = System.currentTimeMillis() + 30_000
        Thread.sleep(1_000)
        while (brainAlive(context) && System.currentTimeMillis() < deadline) Thread.sleep(500)
        val answer = if (brainAlive(context)) JSONObject().put("ok", false).put("message", "Pebble's brain did not stop, so nothing was changed.").toString() else python(context, function, *args)
        KeeperService.start(context, KeeperService.ACTION_RESUME)
        return answer
    }

    fun brainAlive(context: Context): Boolean = BrainProcess.pid(context, Paths(context).heartbeat) != null
}
