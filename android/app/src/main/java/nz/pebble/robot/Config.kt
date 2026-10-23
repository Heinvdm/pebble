package nz.pebble.robot

import org.json.JSONArray
import org.json.JSONObject
import java.io.File

data class PebbleConfig(
    val link: String = LINK_WIFI,
    val host: String = AUTO,
    val port: Int = 7777,
    val mind: String = "llama",
    val sub: Boolean = false,
    val mainModel: String = "gemma-4-E4B_q4_0-it.gguf",
    val subModel: String = "LFM2.5-230M-Q8_0.gguf",
    val mainProjector: String = AUTO,
    val dryRun: Boolean = false,
    val listen: Boolean = true,
    val camera: Boolean = true,
    val reverse: Boolean = false,
    val testImage: String = "",
    val testAudio: String = "",
    val extra: List<String> = emptyList(),
    val mainDrafter: String = AUTO,
    val bench: Boolean = true,
    val benchHotS: Int = 180,
) {
    fun toJson(): JSONObject = JSONObject()
        .put("link", link)
        .put("host", host)
        .put("port", port)
        .put("mind", mind)
        .put("sub", sub)
        .put("mainModel", mainModel)
        .put("subModel", subModel)
        .put("mainProjector", mainProjector)
        .put("dryRun", dryRun)
        .put("listen", listen)
        .put("camera", camera)
        .put("reverse", reverse)
        .put("testImage", testImage)
        .put("testAudio", testAudio)
        .put("extra", JSONArray(extra))
        .put("mainDrafter", mainDrafter)
        .put("bench", bench)
        .put("benchHotS", benchHotS)

    fun usesModels(): Boolean = mind == "llama"

    fun linkSpec(resolvedHost: String?): String? = when (link) {
        LINK_SIM -> null
        LINK_USB -> "tcp:127.0.0.1:$USB_PORT"
        else -> "tcp:${resolvedHost ?: if (host == AUTO) "pebble.local" else host}:$port"
    }

    fun brainArgs(self: File, profile: File?, resolvedHost: String?): List<String> {
        val args = mutableListOf("--self", self.path, "--body", profile?.path ?: "android", "--mind", if (mind == "scripted") "scripted" else "llama")
        args += listOf("--screen", "--screen-host", "127.0.0.1", "--screen-port", SCREEN_PORT.toString())
        if (mind != "scripted" && sub) args += listOf("--sub", "lfm25_230m")
        val spec = linkSpec(resolvedHost)
        if (spec == null) args += "--sim" else args += listOf("--link", spec)
        if (dryRun) args += "--dry-run"
        if (!camera) args += "--no-camera"
        args += extra.filter { it.isNotBlank() }
        return args
    }

    companion object {
        const val AUTO = "auto"
        const val NONE = "none"
        const val LINK_WIFI = "wifi"
        const val LINK_USB = "usb"
        const val LINK_SIM = "sim"
        const val USB_PORT = 7778
        const val SCREEN_PORT = 8765
        private val HOST = Regex("^[A-Za-z0-9.:-]{1,253}$")

        fun validHost(text: String): Boolean = text == AUTO || HOST.matches(text)

        fun fromJson(text: String): PebbleConfig {
            val o = JSONObject(text)
            val base = PebbleConfig()
            val extra = o.optJSONArray("extra")?.let { a -> (0 until a.length()).map { a.optString(it) } } ?: base.extra
            val host = o.optString("host", base.host).trim()
            return PebbleConfig(
                link = o.optString("link", base.link).takeIf { it in listOf(LINK_WIFI, LINK_USB, LINK_SIM) } ?: base.link,
                host = if (validHost(host)) host else base.host,
                port = o.optInt("port", base.port).takeIf { it in 1..65535 } ?: base.port,
                mind = o.optString("mind", base.mind).takeIf { it == "llama" || it == "scripted" } ?: base.mind,
                sub = o.optBoolean("sub", base.sub),
                mainModel = o.optString("mainModel", base.mainModel).takeIf { Models.validName(it) } ?: base.mainModel,
                subModel = o.optString("subModel", base.subModel).takeIf { Models.validName(it) } ?: base.subModel,
                mainProjector = o.optString("mainProjector", base.mainProjector).takeIf { it == AUTO || it == NONE || Models.validName(it) } ?: base.mainProjector,
                dryRun = o.optBoolean("dryRun", base.dryRun),
                listen = o.optBoolean("listen", base.listen),
                camera = o.optBoolean("camera", base.camera),
                reverse = o.optBoolean("reverse", base.reverse),
                testImage = o.optString("testImage", base.testImage),
                testAudio = o.optString("testAudio", base.testAudio),
                extra = extra,
                mainDrafter = o.optString("mainDrafter", base.mainDrafter).takeIf { it == AUTO || it == NONE || Models.validName(it) } ?: base.mainDrafter,
                bench = o.optBoolean("bench", base.bench),
                benchHotS = o.optInt("benchHotS", base.benchHotS).coerceIn(10, 900),
            )
        }

        fun load(file: File): PebbleConfig = try {
            if (file.exists()) fromJson(file.readText()) else PebbleConfig()
        } catch (e: Exception) {
            PebbleConfig()
        }

        fun save(file: File, config: PebbleConfig) {
            Atomic.write(file, config.toJson().toString(2).toByteArray())
        }
    }
}

object Models {
    private val NAME = Regex("^[A-Za-z0-9._-]{1,120}[.]gguf$")

    fun validName(name: String): Boolean = NAME.matches(name) && !name.startsWith(".")
}

object Atomic {
    fun write(file: File, bytes: ByteArray) {
        file.parentFile?.mkdirs()
        val tmp = File(file.parentFile, ".${file.name}.tmp")
        java.io.FileOutputStream(tmp).use {
            it.write(bytes)
            it.fd.sync()
        }
        if (!tmp.renameTo(file)) {
            file.delete()
            if (!tmp.renameTo(file)) throw java.io.IOException("could not replace $file")
        }
    }
}
