package nz.pebble.robot.debug

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log
import nz.pebble.robot.Paths
import nz.pebble.robot.PebbleConfig
import nz.pebble.robot.admin.AdminPin
import nz.pebble.robot.brain.BrainService
import nz.pebble.robot.keeper.KeeperService
import nz.pebble.robot.keeper.SelfOps
import kotlin.concurrent.thread

class DebugCommands : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val paths = Paths(context).ensure()
        val pending = goAsync()
        thread {
            pending.finish()
            try {
                val said = when (intent.action) {
                    "nz.pebble.robot.debug.PIN" -> {
                        AdminPin(paths.pin).set(intent.getStringExtra("pin") ?: "")
                        "pin set"
                    }
                    "nz.pebble.robot.debug.CONFIG" -> {
                        val config = PebbleConfig.fromJson(intent.getStringExtra("json") ?: "{}")
                        PebbleConfig.save(paths.config, config)
                        KeeperService.start(context, KeeperService.ACTION_RELOAD)
                        "config ${config.toJson()}"
                    }
                    "nz.pebble.robot.debug.SEAL" -> SelfOps.withBrainStopped(context, "seal", paths.self.path, intent.getStringExtra("password") ?: "")
                    "nz.pebble.robot.debug.SELF" -> SelfOps.python(context, "status", paths.self.path)
                    "nz.pebble.robot.debug.HANG" -> {
                        context.startService(Intent(context, BrainService::class.java).setAction(BrainService.ACTION_HANG))
                        "asked the brain to hang"
                    }
                    "nz.pebble.robot.debug.ADMIN" -> {
                        context.startActivity(android.content.Intent(context, nz.pebble.robot.ui.AdminActivity::class.java).addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK))
                        "opened the admin screen"
                    }
                    "nz.pebble.robot.debug.MAP" -> {
                        context.startActivity(android.content.Intent(context, nz.pebble.robot.ui.MapActivity::class.java).addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK))
                        "opened the map screen"
                    }
                    "nz.pebble.robot.debug.BODYKEY" -> {
                        if (intent.getBooleanExtra("forget", false)) nz.pebble.robot.link.BodyKey.forget()
                        val hex = intent.getStringExtra("hex").orEmpty()
                        val kept = if (hex.length == 64) nz.pebble.robot.link.BodyKey.keep(ByteArray(32) { hex.substring(it * 2, it * 2 + 2).toInt(16).toByte() }) ?: "kept" else "unchanged"
                        val check = nz.pebble.robot.link.BodyKey.mac("pebble".toByteArray())?.let { nz.pebble.robot.link.LinkProof.hex(it) } ?: "none"
                        "body key $kept; paired ${nz.pebble.robot.link.BodyKey.has()}, in ${nz.pebble.robot.link.BodyKey.level()}, mac of pebble $check"
                    }
                    "nz.pebble.robot.debug.TZ" -> {
                        val dpm = context.getSystemService(android.app.admin.DevicePolicyManager::class.java)
                        val admin = nz.pebble.robot.admin.PebbleAdmin.component(context)
                        dpm.setAutoTimeZoneEnabled(admin, false)
                        val ok = dpm.setTimeZone(admin, intent.getStringExtra("tz") ?: "UTC")
                        "time zone set: $ok"
                    }
                    "nz.pebble.robot.debug.MEASURE" -> {
                        nz.pebble.robot.eyes.Bench.forget(context)
                        nz.pebble.robot.brain.SpeechModels.forgetMeasurements(context)
                        KeeperService.start(context, KeeperService.ACTION_MEASURE_AGAIN)
                        "measuring again"
                    }
                    "nz.pebble.robot.debug.BIRTH" -> {
                        val self = selfFor(context, intent, paths)
                        val birth = nz.pebble.robot.ui.AdminActivity.BIRTH
                        when (intent.getStringExtra("op") ?: "status") {
                            "again" -> {
                                val started = System.nanoTime()
                                val answer = SelfOps.withBrainHeld(context) { SelfOps.admin(context, birth, "again", self.path, intent.getStringExtra("passphrase") ?: "") }
                                "$answer (held for ${Math.round((System.nanoTime() - started) / 1e6)} ms)"
                            }
                            else -> SelfOps.admin(context, birth, "status", self.path)
                        }
                    }
                    "nz.pebble.robot.debug.HOUSE" -> {
                        val self = selfFor(context, intent, paths)
                        val house = nz.pebble.robot.ui.AdminActivity.HOUSE
                        when (intent.getStringExtra("op") ?: "status") {
                            "save" -> {
                                val started = System.nanoTime()
                                val answer = SelfOps.withBrainHeld(context) { SelfOps.admin(context, house, "save", self.path, intent.getStringExtra("passphrase") ?: "", intent.getStringExtra("password") ?: "", intent.getStringExtra("json") ?: "{}") }
                                "$answer (held for ${Math.round((System.nanoTime() - started) / 1e6)} ms)"
                            }
                            "post" -> SelfOps.admin(context, house, "post", self.path, intent.getStringExtra("passphrase") ?: "", intent.getStringExtra("password") ?: "", intent.getStringExtra("json") ?: "{}")
                            "finish" -> SelfOps.admin(context, house, "finish_setup", self.path, intent.getStringExtra("passphrase") ?: "", intent.getStringExtra("tsunami") ?: "")
                            else -> SelfOps.admin(context, house, "status", self.path)
                        }
                    }
                    "nz.pebble.robot.debug.RECEIVE" -> {
                        KeeperService.start(context, KeeperService.ACTION_RECEIVE)
                        "receiver opening"
                    }
                    else -> "unknown"
                }
                Log.i(TAG, "${intent.action}: $said")
            } catch (e: Exception) {
                Log.e(TAG, "${intent.action} failed", e)
            }
        }
    }

    private fun selfFor(context: Context, intent: Intent, paths: Paths): java.io.File =
        intent.getStringExtra("self")?.let { java.io.File(context.filesDir, it) }?.takeIf { it.canonicalPath.startsWith(context.filesDir.canonicalPath) } ?: paths.self

    companion object {
        const val TAG = "PebbleDebug"
    }
}
