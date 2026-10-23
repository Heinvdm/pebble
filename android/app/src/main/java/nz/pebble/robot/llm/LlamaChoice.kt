package nz.pebble.robot.llm

import nz.pebble.robot.Atomic
import org.json.JSONObject
import java.io.File

class LlamaChoice(private val file: File) {
    private fun read(key: String): JSONObject? = try {
        if (file.exists()) JSONObject(file.readText()).takeIf { it.optString("key") == key } else null
    } catch (e: Exception) {
        null
    }

    private fun write(key: String, change: JSONObject.() -> Unit): Boolean = try {
        val o = read(key) ?: JSONObject().put("key", key)
        o.change()
        o.put("at", System.currentTimeMillis())
        Atomic.write(file, o.toString(2).toByteArray())
        true
    } catch (e: Exception) {
        false
    }

    fun step(key: String): Int? = read(key)?.takeIf { it.has("step") }?.optInt("step")

    fun keep(key: String, step: Int, why: String): Boolean = write(key) {
        put("step", step)
        put("why", why)
    }

    fun batch(key: String): Int? = read(key)?.takeIf { it.has("batch") }?.optInt("batch")

    fun drafter(key: String): String? = read(key)?.optString("drafter")?.takeIf { it.isNotEmpty() }

    fun bench(key: String): JSONObject? = read(key)?.optJSONObject("bench")

    fun keepDrafter(key: String, state: String, why: String): Boolean = write(key) {
        put("drafter", state)
        put("drafter_why", why)
    }

    fun keepBench(key: String, batch: Int, drafter: String?, bench: JSONObject): Boolean = write(key) {
        put("batch", batch)
        if (drafter != null) put("drafter", drafter)
        put("bench", bench)
    }

    fun forget() {
        file.delete()
    }

    companion object {
        const val DRAFTER_ON = "on"
        const val DRAFTER_OFF = "off"
        const val DRAFTER_FAILED = "failed"

        fun key(version: Int, phone: String, model: File, projector: File?, drafter: File? = null): String =
            listOf(version.toString(), phone, model.name, model.length().toString(), projector?.name ?: "-", (projector?.length() ?: 0L).toString(), drafter?.name ?: "-", (drafter?.length() ?: 0L).toString()).joinToString("/")
    }
}
