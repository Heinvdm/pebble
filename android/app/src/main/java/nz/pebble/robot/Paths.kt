package nz.pebble.robot

import android.content.Context
import java.io.File

class Paths(context: Context) {
    val files: File = context.filesDir
    val self = File(files, "self")
    val keys = File(files, "keys")
    val wrappedKey = File(keys, "pebble-device.key")
    val run = File(files, "run")
    val heartbeat = File(run, "brain.alive")
    val exit = File(run, "brain.exit")
    val rest = File(run, "resting")
    val config = File(files, "pebble.json")
    val pin = File(files, "admin-pin.json")
    val logs = File(files, "logs")
    val brainLog = File(logs, "brain.log")
    val adminLog = File(logs, "admin.log")
    val external: File = context.getExternalFilesDir(null) ?: File(files, "external")
    val models = File(files, "models")
    val modelDrop = File(external, "models")
    val modelsSeen = File(models, ".checked.json")
    val oldProfile = File(external, "body_android.json")
    val profileOverlay = File(files, "body_overlay.json")
    val profileMerged = File(run, "body.json")
    val nativeLibs = File(context.applicationInfo.nativeLibraryDir)

    fun ensure(): Paths {
        listOf(keys, run, logs, models, modelDrop).forEach { it.mkdirs() }
        return this
    }
}
