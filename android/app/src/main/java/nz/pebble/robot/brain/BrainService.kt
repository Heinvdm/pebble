package nz.pebble.robot.brain

import android.app.Notification
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import android.os.Process
import android.util.Log
import androidx.core.app.ServiceCompat
import androidx.lifecycle.LifecycleService
import com.chaquo.python.PyException
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import nz.pebble.robot.Atomic
import nz.pebble.robot.Paths
import nz.pebble.robot.PebbleApp
import nz.pebble.robot.PebbleConfig
import nz.pebble.robot.R
import nz.pebble.robot.eyes.Eyes
import nz.pebble.robot.ui.HomeActivity
import org.json.JSONObject
import kotlin.concurrent.thread

class BrainService : LifecycleService() {
    private lateinit var paths: Paths
    private var eyes: Eyes? = null
    private var speech: Speech? = null
    private var sensors: PhoneSensors? = null
    private var alarm: Alarm? = null
    private var torch: nz.pebble.robot.eyes.Torch? = null
    private var sentences: nz.pebble.robot.recall.SentenceModel? = null
    private var scripts: nz.pebble.robot.script.ScriptLink? = null
    private var wake: PowerManager.WakeLock? = null
    private var running: Thread? = null
    @Volatile private var types = 0
    @Volatile private var stopRequested = false

    override fun onCreate() {
        super.onCreate()
        paths = Paths(this).ensure()
        types = goForeground()
    }

    override fun onBind(intent: Intent): IBinder? {
        super.onBind(intent)
        return null
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        super.onStartCommand(intent, flags, startId)
        when (intent?.action) {
            ACTION_STOP -> stopBrain()
            ACTION_HANG -> hangForTest()
            else -> startBrain()
        }
        return START_STICKY
    }

    private fun goForeground(): Int {
        val open = PendingIntent.getActivity(this, 0, Intent(this, HomeActivity::class.java), PendingIntent.FLAG_IMMUTABLE)
        val note = Notification.Builder(this, PebbleApp.CHANNEL)
            .setSmallIcon(R.drawable.ic_pebble)
            .setContentTitle("Pebble is awake")
            .setContentText("Seeing and hearing on this phone only")
            .setContentIntent(open)
            .setOngoing(true)
            .build()
        val wanted = ServiceInfo.FOREGROUND_SERVICE_TYPE_CAMERA or ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE or special()
        return try {
            ServiceCompat.startForeground(this, NOTE_ID, note, wanted)
            wanted
        } catch (e: Exception) {
            Log.w(TAG, "camera and microphone could not be claimed now; Pebble runs without them until it is restarted on screen", e)
            ServiceCompat.startForeground(this, NOTE_ID, note, special())
            try {
                Atomic.write(java.io.File(paths.run, nz.pebble.robot.ui.HomeActivity.DEGRADED), "1".toByteArray())
            } catch (ignored: Exception) {
                Log.d(TAG, "could not mark the brain as running without camera")
            }
            special()
        }
    }

    private fun special(): Int = if (Build.VERSION.SDK_INT >= 34) ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE else 0

    @Synchronized
    private fun startBrain() {
        if (running != null) return
        paths.exit.delete()
        running = thread(name = "pebble-brain") { live() }
    }

    private fun live() {
        wake = getSystemService(PowerManager::class.java).newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "pebble:brain").apply {
            setReferenceCounted(false)
            acquire()
        }
        val config = PebbleConfig.load(paths.config)
        var code = 1
        var why = ""
        try {
            if (!Python.isStarted()) Python.start(AndroidPlatform(this))
            if (stopRequested) throw IllegalStateException("stopped before it started")
            val keys = KeyVault(this, paths.wrappedKey)
            sensors = PhoneSensors(this).also { it.start() }
            val canSee = types and ServiceInfo.FOREGROUND_SERVICE_TYPE_CAMERA != 0
            val canHear = types and ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE != 0
            speech = Speech(this).also {
                it.micAllowed = canHear
                it.useTestSound(testAudio(config.testAudio))
                it.start()
                Companion.speech = it
            }
            val pace = java.io.File(paths.run, nz.pebble.robot.keeper.PaceFile.NAME)
            val light = nz.pebble.robot.eyes.Torch(this) { nz.pebble.robot.keeper.PaceFile.read(pace)?.optString("level") == nz.pebble.robot.keeper.HeatLevel.HOT }.also { torch = it }
            eyes = if (canSee) Eyes(this, this, config.reverse, light).also { it.useTestImage(config.testImage) } else null
            alarm = Alarm(this).also { it.start() }
            val seeing = eyes
            val hearing = speech
            val recall = try {
                nz.pebble.robot.recall.SentenceModel.forPhone(
                    this,
                    pace,
                    { seeing?.status()?.let { JSONObject(it) }?.let { it.optBoolean("ready") && !it.isNull("open") } ?: false },
                    { hearing?.state()?.optString("ears", "none") ?: "none" },
                ).also {
                    sentences = it
                    Companion.sentences = it
                    it.start()
                }
            } catch (e: Exception) {
                Log.w(TAG, "the memory search's sentence model could not be set up; the brain uses its stand-in", e)
                null
            }
            val programs = nz.pebble.robot.script.ScriptLink(this).also { scripts = it }
            val bridge = Bridge(keys, sensors, speech, eyes, Power(this, paths), alarm, light, recall, { nz.pebble.robot.keeper.PaceFile.forBrain(this, pace).toString() }, programs)
            val host = when {
                config.link != PebbleConfig.LINK_WIFI -> null
                config.host != PebbleConfig.AUTO -> config.host
                else -> Discover.find(this, DISCOVER_MS)
            }
            try {
                Atomic.write(java.io.File(paths.run, LINK_FILE), JSONObject().put("link", config.link).put("host", config.host).put("port", config.port).put("found", host ?: JSONObject.NULL).put("at", System.currentTimeMillis()).toString().toByteArray())
            } catch (e: Exception) {
                Log.d(TAG, "could not note the link's address")
            }
            val args = config.brainArgs(paths.self, overlaidProfile(), host)
            Log.i(TAG, "starting the brain: $args")
            Companion.bridge = bridge
            val result = Python.getInstance().getModule("pebble.android.main")
                .callAttr("run", args.toTypedArray(), bridge, paths.heartbeat.path, paths.brainLog.path)
            code = result.toInt()
        } catch (e: PyException) {
            why = e.message ?: "the brain stopped with an error"
            Log.e(TAG, "the brain failed", e)
        } catch (e: Throwable) {
            why = e.message ?: e.javaClass.simpleName
            Log.e(TAG, "the brain could not start", e)
        }
        try {
            Atomic.write(paths.exit, JSONObject().put("code", code).put("at", System.currentTimeMillis()).put("why", why).put("pid", Process.myPid()).toString().toByteArray())
        } catch (e: Exception) {
            Log.e(TAG, "could not record how the brain stopped", e)
        }
        Log.i(TAG, "the brain stopped with code $code")
        Companion.bridge = null
        Companion.sentences = null
        sentences?.close()
        scripts?.closeAll()
        eyes?.shutdown()
        torch?.shutdown()
        speech?.shutdown()
        alarm?.shutdown()
        sensors?.stop()
        wake?.release()
        ServiceCompat.stopForeground(this, ServiceCompat.STOP_FOREGROUND_REMOVE)
        stopSelf()
        Process.killProcess(Process.myPid())
    }

    private fun overlaidProfile(): java.io.File? {
        if (!paths.profileOverlay.exists()) return null
        return try {
            val base = Python.getInstance().getModule("pebble.body.profile").callAttr("resolve_profile", "android", "body").toString()
            val merged = nz.pebble.robot.link.ProfileOverlay.merge(JSONObject(java.io.File(base).readText()), JSONObject(paths.profileOverlay.readText()))
            Atomic.write(paths.profileMerged, merged.toString(2).toByteArray())
            paths.profileMerged
        } catch (e: Exception) {
            Log.w(TAG, "the body profile's overlay could not be used; using the profile inside the app", e)
            null
        }
    }

    private fun testAudio(name: String): Sound? {
        if (name.isEmpty()) return null
        return try {
            val file = java.io.File(paths.external, name)
            val bytes = if (file.exists()) file.readBytes() else assets.open("speech/tests/$name").use { it.readBytes() }
            Wav.read(bytes)
        } catch (e: Exception) {
            Log.w(TAG, "the test sound $name could not be read", e)
            null
        }
    }

    private fun stopBrain() {
        stopRequested = true
        if (running == null) {
            stopSelf()
            Process.killProcess(Process.myPid())
            return
        }
        thread(name = "pebble-brain-stop") {
            if (!Python.isStarted()) return@thread
            try {
                Python.getInstance().getModule("pebble.android.main").callAttr("stop")
            } catch (e: Throwable) {
                Log.w(TAG, "the brain did not take the stop", e)
            }
        }
    }

    private fun hangForTest() {
        if (!nz.pebble.robot.BuildConfig.DEBUG || running == null) return
        thread(name = "pebble-brain-hang") {
            Python.getInstance().getModule("pebble.android.testing").callAttr("hang", 600)
        }
    }

    companion object {
        const val TAG = "PebbleBrain"
        const val NOTE_ID = 2
        const val ACTION_STOP = "nz.pebble.robot.STOP_BRAIN"
        const val ACTION_HANG = "nz.pebble.robot.HANG_BRAIN"
        const val DISCOVER_MS = 8_000L
        const val LINK_FILE = "link.json"
        @Volatile var bridge: Bridge? = null
        @Volatile var speech: Speech? = null
        @Volatile var sentences: nz.pebble.robot.recall.SentenceModel? = null

        fun start(context: Context) {
            context.startForegroundService(Intent(context, BrainService::class.java))
        }

        fun stop(context: Context) {
            context.startService(Intent(context, BrainService::class.java).setAction(ACTION_STOP))
        }
    }
}
