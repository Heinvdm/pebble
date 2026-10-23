package nz.pebble.robot.ui

import org.json.JSONObject

object BirthText {
    fun offered(birth: JSONObject?): Boolean = birth != null && birth.optBoolean("setup") && birth.isNull("born")

    fun describe(birth: JSONObject?): String {
        if (birth == null) return "Pebble's birth draw could not be read."
        val lines = mutableListOf<String>()
        birth.optString("line").takeIf { it.isNotEmpty() }?.let { lines += it }
        val traits = birth.optJSONObject("traits")
        val usual = birth.optJSONObject("usual")
        if (traits != null && traits.length() > 0) {
            val listed = traits.keys().asSequence().sorted().joinToString(", ") { name ->
                val value = traits.optInt(name)
                val before = usual?.takeIf { it.has(name) }?.optInt(name)
                if (before != null && before != value) "$name $value (usually $before)" else "$name $value"
            }
            lines += "Draw ${birth.optInt("draw", 1)}. Traits: $listed."
        }
        val values = birth.optJSONObject("values")
        if (values != null && values.length() > 0) lines += "Free values: " + values.keys().asSequence().sorted().joinToString(", ") { "$it ${values.optInt(it)}" } + "."
        val tastes = birth.optJSONArray("tastes")
        if (tastes != null && tastes.length() > 0) lines += "First tastes: " + (0 until tastes.length()).joinToString(" and ") { tastes.optString(it) } + "."
        if (!birth.isNull("born")) lines += "Born on ${birth.optString("born")}; this draw is its own now."
        return lines.joinToString("\n")
    }
}
