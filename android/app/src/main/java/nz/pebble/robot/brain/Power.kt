package nz.pebble.robot.brain

import android.content.Context
import android.util.Log
import nz.pebble.robot.Atomic
import nz.pebble.robot.Paths
import nz.pebble.robot.admin.Kiosk
import org.json.JSONObject

class Power(private val context: Context, private val paths: Paths) {
    fun powerOff(mode: String): String {
        val kiosk = Kiosk(context)
        return when (mode) {
            "reboot" -> if (kiosk.reboot()) "rebooting the phone" else "none"
            "rest" -> {
                Atomic.write(paths.rest, JSONObject().put("at", System.currentTimeMillis()).put("why", "battery").toString().toByteArray())
                val dark = kiosk.lockScreenNow()
                Log.w(TAG, "resting: the models stop and Pebble starts again on charge")
                if (dark) "resting: screen off, models stopping, Pebble starts again when it is charging" else "resting: models stopping, Pebble starts again when it is charging (the screen could not be turned off)"
            }
            else -> "none"
        }
    }

    companion object {
        const val TAG = "PebblePower"
    }
}
