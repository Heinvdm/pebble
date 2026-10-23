package nz.pebble.robot.ui

import org.json.JSONObject

object HouseInput {
    private val NUMBERS = Regex("^\\s*(-?\\d+(?:\\.\\d+)?)\\s*[,; ]\\s*(-?\\d+(?:\\.\\d+)?)\\s*$")

    fun latLon(text: String): Pair<Double, Double>? {
        val found = NUMBERS.matchEntire(text) ?: return null
        val lat = found.groupValues[1].toDouble()
        val lon = found.groupValues[2].toDouble()
        return if (lat in -90.0..90.0 && lon in -180.0..180.0) lat to lon else null
    }

    fun names(text: String): List<String> = text.split(',', ';', '\n').map { it.trim() }.filter { it.isNotEmpty() }.distinct()

    fun tsunami(house: JSONObject): String = when {
        !house.has("tsunami_zone") || house.isNull("tsunami_zone") -> ""
        house.optBoolean("tsunami_zone") -> "yes"
        else -> "no"
    }

    fun describe(house: JSONObject?): String {
        if (house == null) return "The house settings could not be read."
        val place = house.optJSONObject("place")
        val home = when {
            place == null -> "not set, so Pebble can't work out sunrise and sunset"
            place.optString("name").isNotEmpty() -> "${place.optString("name")} (${place.optDouble("lat")}, ${place.optDouble("lon")})"
            else -> "${place.optDouble("lat")}, ${place.optDouble("lon")}"
        }
        val wifi = house.optJSONObject("guest_wifi")?.let { "\"${it.optString("ssid")}\" (${if (it.optString("security") == "nopass") "open" else it.optString("security")})" } ?: "not set"
        val guardians = house.optInt("guardians")
        val kids = if (house.optBoolean("children_arrivals")) "on" + (if (guardians > 0) ", with $guardians grown-up${if (guardians == 1) "" else "s"} besides the owner" else "") else "off"
        val zone = when (tsunami(house)) {
            "yes" -> "yes"
            "no" -> "no"
            else -> "not answered, so the \"long or strong, get gone\" line is off"
        }
        val lines = mutableListOf(
            "Home: $home.",
            "Guest Wi-Fi: $wifi.",
            "Children's arrivals told to their grown-ups: $kids.",
            "Cooking watch: ${if (house.optBoolean("cooking_watch")) "on" else "off"}.",
            "Tsunami zone: $zone.",
        )
        if (house.optBoolean("passphrase_set") && house.optBoolean("sealed")) {
            lines += if (house.optBoolean("password_works")) "The self is sealed, so the spoken passphrase no longer opens these: type the owner's password, the one that seals the self." else "A spoken passphrase is set and the sealed self has no owner's password, so these can't be changed here."
        }
        val waiting = house.optInt("waiting")
        if (waiting > 0) lines += "$waiting change${if (waiting == 1) "" else "s"} sent, waiting for Pebble to take ${if (waiting == 1) "it" else "them"}."
        return lines.joinToString("\n")
    }
}
