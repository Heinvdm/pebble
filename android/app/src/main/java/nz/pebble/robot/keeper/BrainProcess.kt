package nz.pebble.robot.keeper

import android.app.ActivityManager
import android.content.Context
import java.io.File

object BrainProcess {
    fun name(context: Context): String = "${context.packageName}:brain"

    fun pid(context: Context, heartbeat: File): Int? {
        val name = name(context)
        val listed = try {
            context.getSystemService(ActivityManager::class.java).runningAppProcesses?.firstOrNull { it.processName == name }?.pid
        } catch (e: Exception) {
            null
        }
        if (listed != null) return listed
        val written = try {
            pidOf(heartbeat.readText())
        } catch (e: Exception) {
            null
        } ?: return null
        return written.takeIf { named(it) == name }
    }

    fun pidOf(heartbeat: String): Int? = heartbeat.trim().split(Regex("\\s+")).getOrNull(1)?.toIntOrNull()?.takeIf { it > 0 }

    fun nameOf(cmdline: ByteArray): String = String(cmdline.takeWhile { it != 0.toByte() }.toByteArray(), Charsets.UTF_8)

    private fun named(pid: Int): String? = try {
        nameOf(File("/proc/$pid/cmdline").readBytes())
    } catch (e: Exception) {
        null
    }
}
