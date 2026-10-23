package nz.pebble.robot.net

import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageInstaller
import android.content.pm.PackageInfo
import android.os.Build
import android.util.Log
import java.io.File

object SelfUpdate {
    const val TAG = "PebbleUpdate"

    private fun versionOf(info: PackageInfo): Long = if (Build.VERSION.SDK_INT >= 28) info.longVersionCode else @Suppress("DEPRECATION") info.versionCode.toLong()

    fun refusal(installedPackage: String, installedCode: Long, incomingPackage: String?, incomingCode: Long?): String? = when {
        incomingPackage == null || incomingCode == null -> "That is not an APK Android can read; nothing was installed."
        incomingPackage != installedPackage -> "That APK is not Pebble ($incomingPackage); nothing was installed."
        incomingCode <= installedCode -> "That APK's version code ($incomingCode) is not higher than the one on the phone ($installedCode), so it would be a step back; nothing was installed. Build it with -Ppebble.versionCode=${installedCode + 1} or higher."
        else -> null
    }

    fun install(context: Context, apk: File): String {
        val pm = context.packageManager
        val incoming = pm.getPackageArchiveInfo(apk.path, 0)
        val installed = pm.getPackageInfo(context.packageName, 0)
        refusal(context.packageName, versionOf(installed), incoming?.packageName, incoming?.let { versionOf(it) })?.let {
            Log.w(TAG, it)
            apk.delete()
            return it
        }
        val installer = pm.packageInstaller
        val params = PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL)
        params.setAppPackageName(context.packageName)
        if (Build.VERSION.SDK_INT >= 31) params.setRequireUserAction(PackageInstaller.SessionParams.USER_ACTION_NOT_REQUIRED)
        return try {
            val id = installer.createSession(params)
            installer.openSession(id).use { session ->
                session.openWrite("pebble.apk", 0, apk.length()).use { out ->
                    apk.inputStream().use { it.copyTo(out) }
                    session.fsync(out)
                }
                val flags = PendingIntent.FLAG_UPDATE_CURRENT or (if (Build.VERSION.SDK_INT >= 31) PendingIntent.FLAG_MUTABLE else 0)
                val status = PendingIntent.getBroadcast(context, id, Intent(context, InstallReceiver::class.java), flags)
                session.commit(status.intentSender)
            }
            "Installing the update now. Pebble restarts by itself when it is done (about a minute)."
        } catch (e: Exception) {
            Log.e(TAG, "the update failed", e)
            "The update could not be installed: ${e.message}"
        }
    }
}

class InstallReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val status = intent.getIntExtra(PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_FAILURE)
        val message = intent.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE)
        when (status) {
            PackageInstaller.STATUS_SUCCESS -> Log.i(SelfUpdate.TAG, "update installed")
            PackageInstaller.STATUS_PENDING_USER_ACTION -> {
                Log.w(SelfUpdate.TAG, "the update needs a tap on the screen (Pebble is not the device owner)")
                val confirm = if (Build.VERSION.SDK_INT >= 33) intent.getParcelableExtra(Intent.EXTRA_INTENT, Intent::class.java) else @Suppress("DEPRECATION") intent.getParcelableExtra(Intent.EXTRA_INTENT)
                confirm?.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)?.let { context.startActivity(it) }
            }
            else -> Log.e(SelfUpdate.TAG, "update failed ($status): $message")
        }
    }
}
