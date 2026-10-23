package nz.pebble.robot.link

import org.json.JSONObject

object ProfileOverlay {
    val FOV = 30.0..150.0
    val CPM = 5.0..60.0
    val TRACK = 100.0..250.0
    val TURNS = setOf(0, 90, 180, 270)
    val CAMERAS = listOf("front", "rear")

    fun clean(raw: JSONObject): JSONObject {
        val out = JSONObject()
        val eyes = JSONObject()
        raw.optJSONObject("eyes")?.let { given ->
            for (camera in CAMERAS) {
                val each = given.optJSONObject(camera) ?: continue
                val kept = JSONObject()
                number(each, "fov_h_deg")?.takeIf { it in FOV }?.let { kept.put("fov_h_deg", it) }
                number(each, "rotate")?.takeIf { it % 1.0 == 0.0 && it.toInt() in TURNS }?.let { kept.put("rotate", it.toInt()) }
                (each.opt("mirror") as? Boolean)?.let { kept.put("mirror", it) }
                if (kept.length() > 0) eyes.put(camera, kept)
            }
        }
        if (eyes.length() > 0) out.put("eyes", eyes)
        val drive = JSONObject()
        raw.optJSONObject("drive")?.let { given ->
            number(given, "cpm")?.takeIf { it == 0.0 || it in CPM }?.let { drive.put("cpm", it) }
            number(given, "wheel_track_mm")?.takeIf { it in TRACK }?.let { drive.put("wheel_track_mm", it) }
        }
        if (drive.length() > 0) out.put("drive", drive)
        return out
    }

    fun merge(base: JSONObject, overlay: JSONObject): JSONObject {
        val merged = JSONObject(base.toString())
        val clean = clean(overlay)
        clean.optJSONObject("drive")?.let { drive ->
            val target = merged.optJSONObject("drive") ?: JSONObject().also { merged.put("drive", it) }
            for (key in drive.keys()) target.put(key, drive.get(key))
        }
        clean.optJSONObject("eyes")?.let { eyes ->
            val target = merged.optJSONObject("eyes") ?: JSONObject().also { merged.put("eyes", it) }
            for (camera in eyes.keys()) {
                val into = target.optJSONObject(camera) ?: JSONObject().also { target.put(camera, it) }
                val from = eyes.getJSONObject(camera)
                for (key in from.keys()) into.put(key, from.get(key))
            }
        }
        return merged
    }

    fun describe(overlay: JSONObject): String {
        val parts = mutableListOf<String>()
        overlay.optJSONObject("eyes")?.let { eyes ->
            for (camera in eyes.keys()) parts += "$camera camera ${eyes.getJSONObject(camera).keys().asSequence().joinToString(", ")}"
        }
        overlay.optJSONObject("drive")?.let { drive -> parts += drive.keys().asSequence().map { "drive $it" } }
        return if (parts.isEmpty()) "nothing" else parts.joinToString("; ")
    }

    private fun number(o: JSONObject, key: String): Double? {
        val value = o.opt(key) as? Number ?: return null
        val d = value.toDouble()
        return if (d.isNaN() || d.isInfinite()) null else d
    }
}
