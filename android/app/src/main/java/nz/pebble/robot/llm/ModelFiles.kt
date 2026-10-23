package nz.pebble.robot.llm

import java.io.File

object ModelFiles {
    const val SETTLE_MS = 15_000L
    const val MISSING = "missing"
    const val COPYING = "copying"
    const val TOO_BIG = "too_big"
    const val NO_ROOM_NOW = "no_room_now"
    const val BAD_FILE = "bad_file"
    const val STOPPED = "stopped"
    const val NO_PROGRAM = "no_program"
    const val UNKNOWN = "unknown_file"

    data class Hold(val kind: String, val why: String)

    data class Failure(val memory: Boolean, val kind: String, val why: String)

    private val MEMORY = listOf("failed to allocate", "unable to allocate", "cannot allocate", "out of memory", "bad_alloc", "failed to mmap", "mmap failed")
    private val PROJECTOR = listOf("mmproj", "multimodal", "clip_init", "clip_model_load")
    private val LOAD_ERROR = Regex("error loading model: ([^\\r\\n]*)")

    fun copying(file: File, now: Long): Boolean = file.exists() && now - file.lastModified() in 0 until SETTLE_MS

    fun hold(file: File, folder: File, here: List<String>, elsewhere: List<File>, now: Long, label: String): Hold? {
        if (!file.exists()) return Hold(MISSING, missing(file.name, folder, here, elsewhere, label))
        if (copying(file, now)) return Hold(COPYING, "$label's file ${file.name} is still being copied (${LlamaPlan.gb(file.length())} so far); it starts once the copy has finished")
        return null
    }

    fun missing(name: String, folder: File, here: List<String>, elsewhere: List<File>, label: String): String {
        val found = elsewhere.firstOrNull { it.name == name } ?: elsewhere.firstOrNull { it.name.equals(name, ignoreCase = true) }
        if (found != null) return "$label's file ${found.name} is in ${found.parent}, not in the models folder; move it into ${folder.path}"
        val others = here.filter { it.lowercase().endsWith(".gguf") && !it.startsWith(".") }.sortedBy { it.lowercase() }
        others.firstOrNull { it.equals(name, ignoreCase = true) }?.let {
            return "$label's file must be named exactly $name (capitals count), and the models folder has $it; rename the file, or type its name under Mind"
        }
        if (others.isNotEmpty()) return "no file named $name for $label in ${folder.path}; the folder has ${others.joinToString(", ")}. Copy $name there, or type the right name under Mind"
        return "no file named $name for $label in ${folder.path} yet; copy it there (SETUP.md, step 8)"
    }

    fun failure(log: String, code: Int?, projector: Boolean): Failure {
        val text = log.lowercase()
        val loading = LOAD_ERROR.findAll(log).lastOrNull()?.groupValues?.get(1)?.trim().orEmpty()
        val low = loading.lowercase()
        return when {
            MEMORY.any { it in text } -> Failure(true, STOPPED, "it ran out of memory while loading")
            code == 137 || code == 9 -> Failure(true, STOPPED, "Android stopped it, most likely to free memory")
            projector && PROJECTOR.any { it in text } && loading.isEmpty() -> Failure(false, BAD_FILE, "its picture projector could not be read; copy the projector again, or set the projector to none under Mind")
            "corrupt" in low || "incomplete" in low || "not within the file bounds" in low -> Failure(false, BAD_FILE, "the file is damaged or cut short; copy it to the phone again")
            "unknown model architecture" in low || "unknown architecture" in low -> Failure(false, BAD_FILE, "this build's llama-server cannot run that kind of model")
            loading.isNotEmpty() || "failed to load model" in text -> Failure(false, BAD_FILE, "llama-server could not read the file; the model log says why")
            else -> Failure(true, STOPPED, "it stopped${if (code != null) " (code $code)" else ""}")
        }
    }
}
