package nz.pebble.robot.admin

import android.Manifest
import android.app.Activity
import android.app.ActivityManager
import android.app.admin.DevicePolicyManager
import android.app.admin.SystemUpdatePolicy
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.BatteryManager
import android.os.Build
import android.os.UserManager
import android.provider.Settings
import android.util.Log
import nz.pebble.robot.Atomic
import nz.pebble.robot.Paths
import nz.pebble.robot.ui.HomeActivity
import java.io.File

class Kiosk(private val context: Context) {
    private val dpm = context.getSystemService(DevicePolicyManager::class.java)
    private val admin = PebbleAdmin.component(context)

    val isOwner: Boolean get() = dpm.isDeviceOwnerApp(context.packageName)

    fun applyPolicies(): List<String> {
        if (!isOwner) return listOf("Pebble is not the device owner, so it runs as a normal app (see SETUP.md).")
        val problems = mutableListOf<String>()
        fun attempt(what: String, block: () -> Unit) {
            try {
                block()
            } catch (e: Exception) {
                Log.w(TAG, "$what failed", e)
                problems += "$what: ${e.message}"
            }
        }
        attempt("lock task") {
            dpm.setLockTaskPackages(admin, arrayOf(context.packageName))
            dpm.setLockTaskFeatures(admin, DevicePolicyManager.LOCK_TASK_FEATURE_GLOBAL_ACTIONS)
        }
        attempt("home app") {
            val filter = IntentFilter(Intent.ACTION_MAIN).apply {
                addCategory(Intent.CATEGORY_HOME)
                addCategory(Intent.CATEGORY_DEFAULT)
            }
            dpm.addPersistentPreferredActivity(admin, filter, ComponentName(context, HomeActivity::class.java))
        }
        attempt("keyguard") { dpm.setKeyguardDisabled(admin, true) }
        attempt("status bar") { dpm.setStatusBarDisabled(admin, true) }
        attempt("screen on while charging") {
            val plugged = BatteryManager.BATTERY_PLUGGED_AC or BatteryManager.BATTERY_PLUGGED_USB or BatteryManager.BATTERY_PLUGGED_WIRELESS
            dpm.setGlobalSetting(admin, Settings.Global.STAY_ON_WHILE_PLUGGED_IN, plugged.toString())
        }
        attempt("night updates") { dpm.setSystemUpdatePolicy(admin, SystemUpdatePolicy.createWindowedInstallPolicy(UPDATE_FROM, UPDATE_TO)) }
        attempt("permissions") {
            val wanted = mutableListOf(Manifest.permission.CAMERA, Manifest.permission.RECORD_AUDIO)
            if (Build.VERSION.SDK_INT >= 33) wanted += Manifest.permission.POST_NOTIFICATIONS
            for (permission in wanted) {
                dpm.setPermissionGrantState(admin, context.packageName, permission, DevicePolicyManager.PERMISSION_GRANT_STATE_GRANTED)
            }
        }
        for (restriction in restrictions()) attempt("restriction $restriction") { dpm.addUserRestriction(admin, restriction) }
        attempt("adb") { enforceAdb(System.currentTimeMillis()) }
        return problems
    }

    private val paths = Paths(context)
    private val adbFile = File(paths.run, ADB_UNTIL)

    fun adbAllowedUntil(): Long = try {
        if (adbFile.exists()) adbFile.readText().trim().toLongOrNull() ?: 0L else 0L
    } catch (e: Exception) {
        0L
    }

    fun adbWindowOpen(now: Long): Boolean = adbAllowedUntil() > now

    fun adbOpen(now: Long): Boolean = nz.pebble.robot.BuildConfig.DEBUG || !AdminPin(paths.pin).isSet() || adbWindowOpen(now)

    fun allowAdbFor(minutes: Int): Boolean {
        if (!isOwner) return false
        Atomic.write(adbFile, (System.currentTimeMillis() + minutes * 60_000L).toString().toByteArray())
        return enforceAdb(System.currentTimeMillis())
    }

    fun blockAdbNow(): Boolean {
        adbFile.delete()
        return enforceAdb(System.currentTimeMillis())
    }

    fun enforceAdb(now: Long): Boolean {
        if (!isOwner) return false
        val open = adbOpen(now)
        if (!open && adbFile.exists()) adbFile.delete()
        return try {
            val blocked = dpm.getUserRestrictions(admin).getBoolean(UserManager.DISALLOW_DEBUGGING_FEATURES, false)
            if (open && blocked) dpm.clearUserRestriction(admin, UserManager.DISALLOW_DEBUGGING_FEATURES)
            if (!open && !blocked) dpm.addUserRestriction(admin, UserManager.DISALLOW_DEBUGGING_FEATURES)
            true
        } catch (e: Exception) {
            Log.w(TAG, "could not change adb", e)
            false
        }
    }

    fun usbData(wanted: Boolean): String {
        if (!isOwner) return "not the device owner"
        if (Build.VERSION.SDK_INT < 31) return "this Android is too old to switch USB data off"
        return try {
            if (!dpm.canUsbDataSignalingBeDisabled()) return "this phone does not let an app switch USB data off"
            if (dpm.isUsbDataSignalingEnabled != wanted) dpm.setUsbDataSignalingEnabled(wanted)
            if (wanted) "on" else "off"
        } catch (e: Exception) {
            Log.w(TAG, "could not change USB data", e)
            "could not be changed: ${e.message}"
        }
    }

    fun kioskPauseOver(now: Long): Boolean {
        val pause = File(paths.run, HomeActivity.KIOSK_PAUSE)
        if (!pause.exists()) return false
        val until = try {
            pause.readText().trim().toLongOrNull() ?: 0L
        } catch (e: Exception) {
            0L
        }
        if (until > now) return false
        pause.delete()
        return true
    }

    fun enter(activity: Activity) {
        if (!isOwner || inLockTask()) return
        try {
            activity.startLockTask()
        } catch (e: Exception) {
            Log.w(TAG, "could not start lock task", e)
        }
    }

    fun leave(activity: Activity) {
        try {
            if (inLockTask()) activity.stopLockTask()
        } catch (e: Exception) {
            Log.w(TAG, "could not stop lock task", e)
        }
        if (isOwner) {
            try {
                dpm.setStatusBarDisabled(admin, false)
            } catch (e: Exception) {
                Log.w(TAG, "could not show the status bar", e)
            }
        }
    }

    fun inLockTask(): Boolean =
        context.getSystemService(ActivityManager::class.java).lockTaskModeState != ActivityManager.LOCK_TASK_MODE_NONE

    fun adbBlocked(): Boolean = isOwner && dpm.getUserRestrictions(admin).getBoolean(UserManager.DISALLOW_DEBUGGING_FEATURES, false)

    fun lockScreenNow(): Boolean = try {
        dpm.lockNow()
        true
    } catch (e: Exception) {
        Log.w(TAG, "could not turn the screen off", e)
        false
    }

    fun reboot(): Boolean = try {
        if (isOwner) {
            dpm.reboot(admin)
            true
        } else false
    } catch (e: Exception) {
        Log.w(TAG, "could not reboot", e)
        false
    }

    fun giveUpOwnership(): Boolean {
        if (!isOwner) return false
        return try {
            dpm.clearPackagePersistentPreferredActivities(admin, context.packageName)
            dpm.setStatusBarDisabled(admin, false)
            dpm.setKeyguardDisabled(admin, false)
            dpm.clearUserRestriction(admin, UserManager.DISALLOW_DEBUGGING_FEATURES)
            for (restriction in restrictions()) {
                try {
                    dpm.clearUserRestriction(admin, restriction)
                } catch (e: Exception) {
                    Log.w(TAG, "could not clear $restriction", e)
                }
            }
            if (Build.VERSION.SDK_INT >= 31 && dpm.canUsbDataSignalingBeDisabled()) dpm.setUsbDataSignalingEnabled(true)
            adbFile.delete()
            dpm.setLockTaskPackages(admin, arrayOf())
            @Suppress("DEPRECATION")
            dpm.clearDeviceOwnerApp(context.packageName)
            true
        } catch (e: Exception) {
            Log.w(TAG, "could not give up device owner", e)
            false
        }
    }

    companion object {
        const val TAG = "PebbleKiosk"
        const val ADB_UNTIL = "adb-allowed-until"
        const val ADB_MINUTES = 30

        fun restrictions(): List<String> {
            val all = mutableListOf(
                UserManager.DISALLOW_ADD_USER,
                UserManager.DISALLOW_SAFE_BOOT,
                UserManager.DISALLOW_USB_FILE_TRANSFER,
                UserManager.DISALLOW_MOUNT_PHYSICAL_MEDIA,
                UserManager.DISALLOW_CONFIG_DATE_TIME,
                UserManager.DISALLOW_NETWORK_RESET,
                UserManager.DISALLOW_FACTORY_RESET,
                UserManager.DISALLOW_BLUETOOTH,
                UserManager.DISALLOW_CONFIG_BLUETOOTH,
                UserManager.DISALLOW_BLUETOOTH_SHARING,
            )
            if (Build.VERSION.SDK_INT >= 34) {
                all += listOf(
                    UserManager.DISALLOW_NEAR_FIELD_COMMUNICATION_RADIO,
                    UserManager.DISALLOW_ULTRA_WIDEBAND_RADIO,
                    UserManager.DISALLOW_CELLULAR_2G,
                    "no_add_clone_profile",
                )
            }
            if (Build.VERSION.SDK_INT >= 35) all += UserManager.DISALLOW_ADD_PRIVATE_PROFILE
            return all
        }
        const val UPDATE_FROM = 2 * 60
        const val UPDATE_TO = 5 * 60
    }
}
