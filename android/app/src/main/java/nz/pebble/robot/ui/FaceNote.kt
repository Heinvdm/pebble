package nz.pebble.robot.ui

import nz.pebble.robot.llm.ModelFiles
import org.json.JSONObject

object FaceNote {
    const val STALE_MS = 60_000L
    const val FOLDER = "Android/data/nz.pebble.robot/files/models"

    fun text(status: JSONObject?, now: Long): String? {
        if (status == null || now - status.optLong("at") > STALE_MS) return null
        val config = status.optJSONObject("config") ?: return null
        if (config.optString("mind") != "llama") return null
        if (status.optBoolean("resting") || status.optJSONObject("brain")?.optString("want") != "run") return null
        val main = status.optJSONObject("models")?.optJSONObject("main") ?: return null
        val name = config.optString("mainModel")
        when (main.optString("kind")) {
            ModelFiles.MISSING -> return "Pebble can't talk yet: its language model isn't on this phone. Copy $name into $FOLDER (SETUP.md, step 8)."
            ModelFiles.COPYING -> return "Pebble's language model is still being copied in and checked. Pebble starts it by itself once that has finished."
            ModelFiles.UNKNOWN -> return "Pebble can't talk: the file named $name is not a model on Pebble's list, so it was refused. The admin screen says more."
            ModelFiles.TOO_BIG -> return "Pebble can't talk: its language model is too big for this phone's memory. The admin screen says more."
            ModelFiles.BAD_FILE -> return "Pebble can't talk: its language model file is damaged or cut short. Copy $name to the phone again (SETUP.md, step 8)."
            ModelFiles.NO_PROGRAM -> return "This copy of Pebble was built without the language model program for this phone. Build it again (SETUP.md, step 1)."
        }
        val bench = main.optJSONObject("bench")
        if (bench != null && bench.has("measuring")) {
            val step = bench.optInt("step", 1)
            return "Pebble is getting to know this phone: it is timing how fast it can think (step $step of ${bench.optInt("steps", 5)}). This takes about 10 to 15 minutes, once. Until then Pebble can't hold a conversation; nothing is wrong."
        }
        return when (main.optString("state")) {
            "ready", "busy" -> null
            "loading" -> "Pebble's mind is loading. This takes about a minute."
            "waiting", "failed" -> "Pebble's mind stopped and is starting again by itself."
            else -> when (main.optString("kind")) {
                ModelFiles.NO_ROOM_NOW -> "Pebble's mind is waiting for memory to free up. It tries again by itself."
                ModelFiles.STOPPED -> "Pebble's mind stopped and is starting again by itself."
                else -> null
            }
        }
    }
}
