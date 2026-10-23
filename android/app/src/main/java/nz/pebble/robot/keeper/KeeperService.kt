package nz.pebble.robot.keeper

import android.app.Notification
import android.app.PendingIntent
import android.app.Service
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.ServiceInfo
import android.os.BatteryManager
import android.os.Build
import android.os.Handler
import android.os.HandlerThread
import android.os.IBinder
import android.os.PowerManager
import android.os.Process
import android.util.Log
import androidx.core.app.ServiceCompat
import nz.pebble.robot.Atomic
import nz.pebble.robot.Paths
import nz.pebble.robot.PebbleApp
import nz.pebble.robot.PebbleConfig
import nz.pebble.robot.R
import nz.pebble.robot.brain.BrainService
import nz.pebble.robot.llm.LlamaChoice
import nz.pebble.robot.llm.LlamaPlan
import nz.pebble.robot.llm.LlamaServer
import nz.pebble.robot.llm.ModelAllow
import nz.pebble.robot.llm.ModelFiles
import nz.pebble.robot.llm.ModelImport
import nz.pebble.robot.admin.Kiosk
import nz.pebble.robot.link.BodyKey
import nz.pebble.robot.link.BodyPairing
import nz.pebble.robot.llm.TalkBench
import nz.pebble.robot.net.Receiver
import nz.pebble.robot.net.SelfUpdate
import nz.pebble.robot.ui.HomeActivity
import nz.pebble.robot.usb.UsbBridge
import org.json.JSONObject
import java.io.File

class KeeperService : Service() {
    private lateinit var paths: Paths
    private lateinit var thread: HandlerThread
    private lateinit var handler: Handler
    private val watchdog = Watchdog()
    private lateinit var main: LlamaServer
    private lateinit var sub: LlamaServer
    private lateinit var receiver: Receiver
    private lateinit var seen: ModelAllow.Seen
    private lateinit var importer: ModelImport
    private lateinit var kiosk: Kiosk
    @Volatile private var pairing = false
    @Volatile private var pairSaid: Any = JSONObject.NULL
    private var usbData = ""
    private var usbWanted: Boolean? = null
    private var usb: UsbBridge? = null
    private var wake: PowerManager.WakeLock? = null
    private var want = Want.RUN
    private var holdUntil = 0L
    private var startedAt = 0L
    private var config = PebbleConfig()
    private var lastAct = ""
    private var plugged = false
    private val heatLevel = HeatLevel()
    private val speed = SpeedWatch()
    private var heat = JSONObject()
    private var slow = false
    private var metricsAt = 0L
    @Volatile private var talkBench: TalkBench? = null
    private var benchKey = ""
    private var benchProblem = ""
    private var benchRetryAt = 0L
    private var benchRetryKey = ""
    private var benchStartedAt = 0L
    private var mainKey = ""

    private val power = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            plugged = intent.action == Intent.ACTION_POWER_CONNECTED
            handler.post { tick() }
        }
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        paths = Paths(this).ensure()
        goForeground()
        wake = getSystemService(PowerManager::class.java).newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "pebble:keeper").apply {
            setReferenceCounted(false)
            acquire()
        }
        main = LlamaServer(this, "main", File(paths.logs, "llama-main.log"))
        sub = LlamaServer(this, "sub", File(paths.logs, "llama-sub.log"))
        seen = ModelAllow.Seen(paths.modelsSeen)
        importer = ModelImport(paths.modelDrop, paths.models, seen)
        kiosk = Kiosk(this)
        receiver = Receiver(paths, cacheDir, seen) { apk -> SelfUpdate.install(this, apk) }
        thread = HandlerThread("pebble-keeper").also { it.start() }
        handler = Handler(thread.looper)
        val filter = IntentFilter().apply {
            addAction(Intent.ACTION_POWER_CONNECTED)
            addAction(Intent.ACTION_POWER_DISCONNECTED)
        }
        registerReceiver(power, filter)
        plugged = charging()
        handler.post(loop)
    }

    private fun goForeground() {
        val open = PendingIntent.getActivity(this, 0, Intent(this, HomeActivity::class.java), PendingIntent.FLAG_IMMUTABLE)
        val note = Notification.Builder(this, PebbleApp.CHANNEL)
            .setSmallIcon(R.drawable.ic_pebble)
            .setContentTitle("Pebble keeps itself running")
            .setContentText("Models, watchdog and the link to the body")
            .setContentIntent(open)
            .setOngoing(true)
            .build()
        val types = ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE or (if (Build.VERSION.SDK_INT >= 34) ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE else 0)
        ServiceCompat.startForeground(this, NOTE_ID, note, types)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_PAUSE -> handler.post {
                want = Want.PAUSE
                tick()
            }
            ACTION_RESUME -> handler.post {
                watchdog.planned()
                want = Want.RUN
                tick()
            }
            ACTION_RELEASE -> handler.post {
                if (want == Want.HOLD) {
                    watchdog.planned()
                    want = Want.RUN
                }
                tick()
            }
            ACTION_HOLD -> handler.post {
                if (want != Want.PAUSE) {
                    want = Want.HOLD
                    holdUntil = System.currentTimeMillis() + HOLD_MS
                }
                tick()
            }
            ACTION_RELOAD -> handler.post { reload() }
            ACTION_MEASURE_AGAIN -> handler.post {
                stopBench()
                benchRetryAt = 0L
                main.choice.forget()
                sub.choice.forget()
                nz.pebble.robot.recall.SentenceModel.forget(this)
                speed.clear()
                reload()
            }
            ACTION_RESTART_BRAIN -> handler.postDelayed({
                watchdog.planned()
                if (brainPid() != null) BrainService.stop(this)
                tick()
            }, intent.getLongExtra(EXTRA_AFTER_MS, 0L).coerceIn(0L, MAX_AFTER_MS))
            ACTION_RECEIVE -> handler.post {
                receiver.open(intent.getIntExtra(EXTRA_MINUTES, 15))
                writeStatus()
            }
            ACTION_CLOSE_RECEIVER -> handler.post {
                receiver.close()
                writeStatus()
            }
            ACTION_PAIR_BODY -> handler.post { pairBody() }
            ACTION_FORGET_BODY_KEY -> handler.post {
                BodyKey.forget()
                pairSaid = JSONObject().put("ok", true).put("at", System.currentTimeMillis()).put("message", "The phone forgot the body key. Pebble will not drive the body until it is paired again.")
                watchdog.planned()
                if (brainPid() != null) BrainService.stop(this)
                writeStatus()
            }
            else -> handler.post { tick() }
        }
        return START_STICKY
    }

    private fun reload() {
        watchdog.planned()
        stopBench()
        main.stop()
        sub.stop()
        usb?.stop()
        usb = null
        if (brainPid() != null) BrainService.stop(this)
        tick()
    }

    private val loop = object : Runnable {
        override fun run() {
            try {
                tick()
            } catch (e: Exception) {
                Log.e(TAG, "keeper tick failed", e)
            }
            handler.postDelayed(this, TICK_MS)
        }
    }

    private fun charging(): Boolean {
        val intent = registerReceiver(null, IntentFilter(Intent.ACTION_BATTERY_CHANGED)) ?: return false
        return intent.getIntExtra(BatteryManager.EXTRA_PLUGGED, 0) != 0
    }

    private fun brainPid(): Int? = BrainProcess.pid(this, paths.heartbeat)

    private fun readExit(): Pair<Int?, Long> = try {
        if (paths.exit.exists()) JSONObject(paths.exit.readText()).let { (if (it.has("code")) it.getInt("code") else null) to it.optLong("at", 0L) } else null to 0L
    } catch (e: Exception) {
        null to 0L
    }

    private fun heartbeat(): Long = try {
        if (paths.heartbeat.exists()) (paths.heartbeat.readText().trim().split(" ").first().toDouble() * 1000).toLong() else 0L
    } catch (e: Exception) {
        0L
    }

    private fun tick() {
        config = PebbleConfig.load(paths.config)
        val now = System.currentTimeMillis()
        if (want == Want.HOLD && now >= holdUntil) {
            Log.w(TAG, "a hold on the brain ran out; starting it again")
            watchdog.planned()
            want = Want.RUN
        }
        plugged = charging()
        val resting = paths.rest.exists()
        tickPace()
        importer.tick(now)
        tickModels(resting)
        tickUsb()
        tickLock(now)
        receiver.tick()
        val pid = brainPid()
        val (code, at) = readExit()
        val act = watchdog.decide(Seen(now, want, pid != null, startedAt, heartbeat(), code, at, plugged, resting))
        when (act) {
            is Act.Start -> {
                if (resting) paths.rest.delete()
                Log.i(TAG, "brain: ${act.why}")
                try {
                    BrainService.start(this)
                    startedAt = now
                } catch (e: Exception) {
                    Log.e(TAG, "could not start the brain", e)
                }
            }
            is Act.Kill -> {
                Log.w(TAG, "brain: ${act.why}")
                pid?.let { Process.killProcess(it) }
            }
            is Act.Stop -> {
                Log.i(TAG, "brain: ${act.why}")
                BrainService.stop(this)
            }
            is Act.Rest -> {
                Log.w(TAG, "brain: ${act.why}")
                main.stop()
                sub.stop()
            }
            is Act.Wait, Act.Nothing -> Unit
        }
        if (act !is Act.Nothing) lastAct = watchdog.lastWhy
        writeStatus()
    }

    private fun tickModels(resting: Boolean) {
        if (!config.usesModels() || resting || want == Want.PAUSE) {
            val why = when {
                resting -> "resting until it is charging"
                want == Want.PAUSE -> "paused"
                else -> "the scripted mind needs no model"
            }
            stopBench()
            main.tick(null, why)
            sub.tick(null, why)
            return
        }
        val (mainThreads, subThreads) = LlamaPlan.plan(LlamaServer.maxFreqs())
        val (total, available) = LlamaServer.memory(this)
        val mainFile = File(paths.models, config.mainModel)
        val subFile = File(paths.models, config.subModel)
        val names = ModelImport.gguf(paths.models).filter { seen.allowed(it) }.map { it.name }
        val dropNames = paths.modelDrop.list()?.toList() ?: emptyList()
        val now = System.currentTimeMillis()
        val strays = listOfNotNull(paths.external, paths.external.parentFile).flatMap { dir -> dir.listFiles { f -> f.isFile && f.name.lowercase().endsWith(".gguf") }?.toList().orEmpty() }
        fun planFor(server: LlamaServer, role: String, file: File, port: Int, rungs: List<LlamaPlan.Rung>, threads: Pair<Int, String?>, jinja: Boolean, also: Long, reserve: Long, projector: File?, drafter: File?, keyDrafter: File?, batch: Int): Planned {
            val label = if (role == "main") "the main model" else "the small model"
            if (!file.exists()) {
                importer.refusal(file.name)?.let { return Planned(null, "$label's file ${file.name} was not moved in: ${it.why}", if (it.unknown) ModelFiles.UNKNOWN else "") }
                if (importer.waiting(file.name)) return Planned(null, "$label's file ${file.name} is being checked and moved into Pebble's own storage", ModelFiles.COPYING)
            }
            ModelFiles.hold(file, paths.modelDrop, dropNames, strays, now, label)?.let { return Planned(null, it.why, it.kind) }
            if (!seen.allowed(file)) {
                return if (seen.checked(file)) Planned(null, "$label's file ${file.name} was refused: ${ModelImport.NOT_KNOWN}", ModelFiles.UNKNOWN)
                else Planned(null, "$label's file ${file.name} is being checked", ModelFiles.COPYING)
            }
            server.current(file, projector, drafter, batch, port)?.let { return Planned(it, "", "") }
            val key = server.key(file, projector, keyDrafter)
            val pick = LlamaPlan.pick(file.name, rungs, server.choice.step(key) ?: 0, file.length() + (projector?.length() ?: 0L) + (drafter?.length() ?: 0L), server.kv(file), total, available, also, reserve, batch)
            val rung = pick.rung ?: return Planned(null, pick.fit.why, pick.fit.kind)
            if (!pick.fit.ok) return Planned(null, pick.fit.why, pick.fit.kind)
            return Planned(LlamaPlan.server(role, port, file, threads, jinja, projector, rung, pick.step, key, batch, drafter), "", "")
        }
        val projector = LlamaPlan.projector(names, config.mainProjector, config.mainModel)?.let { File(paths.models, it) }
        val drafterFile = LlamaPlan.drafter(names, config.mainDrafter, config.mainModel)?.let { File(paths.models, it) }
        val settled = mainFile.exists() && seen.allowed(mainFile) && !ModelFiles.copying(mainFile, now) && projector?.let { ModelFiles.copying(it, now) } != true && drafterFile?.let { ModelFiles.copying(it, now) } != true
        mainKey = if (settled) main.key(mainFile, projector, drafterFile) else ""
        talkBench?.takeIf { it.done }?.let { finishBench(it) }
        val drafterState = main.choice.drafter(mainKey)
        val subFloor = if (config.sub && subFile.exists()) LlamaPlan.need(subFile.length(), sub.kv(subFile), LlamaPlan.SUB_RUNGS.last()) else 0L
        val benchMayStart = benchRetryKey != mainKey || now >= benchRetryAt
        if (talkBench == null && config.bench && mainKey.isNotEmpty() && main.choice.bench(mainKey) == null && benchMayStart && main.kind != ModelFiles.BAD_FILE) {
            val runs = main.running && main.planned?.key == mainKey
            if (runs || planFor(main, "main", mainFile, BENCH_PORT, LlamaPlan.MAIN_RUNGS, mainThreads, true, 0L, subFloor, projector, null, drafterFile, LlamaPlan.BATCH).server != null) startBench(mainKey, drafterFile)
        }
        val tune = talkBench?.takeIf { !it.done && benchKey == mainKey }?.wanted
        val batch = tune?.batch ?: main.choice.batch(mainKey) ?: LlamaPlan.BATCH
        val drafter = drafterFile?.takeIf { drafterState != LlamaChoice.DRAFTER_FAILED && (if (tune != null) tune.drafter else drafterState != LlamaChoice.DRAFTER_OFF) && !ModelFiles.copying(it, now) }
        val port = if (tune != null) BENCH_PORT else LlamaPlan.MAIN_PORT
        val usable = projector?.takeIf { !ModelFiles.copying(it, now) }
        val mainPlanned = planFor(main, "main", mainFile, port, LlamaPlan.MAIN_RUNGS, mainThreads, true, 0L, subFloor, usable, drafter, drafterFile, batch)
        val mainPlan = mainPlanned.server
        benchProblem = if (tune != null && mainPlan == null) mainPlanned.why else ""
        main.tick(mainPlan, if (tune != null && mainPlan != null) "measuring" else mainPlanned.why, mainPlanned.kind)
        if (config.sub) {
            val mainNeed = mainPlan?.let { LlamaPlan.needOf(it, main.kv(it.model)) } ?: 0L
            val subPlanned = planFor(sub, "sub", subFile, LlamaPlan.SUB_PORT, LlamaPlan.SUB_RUNGS, subThreads, false, mainNeed, 0L, null, null, null, LlamaPlan.BATCH)
            sub.tick(subPlanned.server, subPlanned.why, subPlanned.kind)
        } else {
            sub.tick(null, "the small model is switched off")
        }
        watchSpeed()
    }

    private fun startBench(key: String, drafterFile: File?) {
        val bench = TalkBench(
            BENCH_PORT,
            { drafterFile != null && main.choice.drafter(key) != LlamaChoice.DRAFTER_FAILED },
            config.benchHotS,
            object : TalkBench.Control {
                override fun use(tune: TalkBench.Tune) {
                    handler.post { tick() }
                }

                override fun state(tune: TalkBench.Tune): String = when {
                    tune.drafter && main.choice.drafter(key) == LlamaChoice.DRAFTER_FAILED -> "failed"
                    main.kind == ModelFiles.BAD_FILE || main.kind == ModelFiles.NO_PROGRAM -> "failed"
                    benchProblem.isNotEmpty() && !benchProblem.contains("tried again later") -> "failed"
                    else -> main.stateFor(BENCH_PORT, tune.batch, tune.drafter)
                }
            },
            { heat },
            {
                JSONObject()
                    .put("main_rss", main.rss() ?: JSONObject.NULL)
                    .put("sub_rss", sub.rss() ?: JSONObject.NULL)
                    .put("free", LlamaServer.memory(this).second)
            },
        )
        talkBench = bench
        benchKey = key
        benchStartedAt = System.currentTimeMillis()
        Log.i(TAG, "measuring how fast the main model talks on this phone")
        bench.start()
    }

    private fun stopBench() {
        talkBench?.stop()
        talkBench = null
    }

    private fun finishBench(bench: TalkBench) {
        talkBench = null
        val result = bench.result ?: return
        val measured = result.optJSONObject("cool")?.let { cool -> cool.keys().asSequence().any { cool.optJSONObject(it)?.has("first_ms") == true } } == true
        if (!measured) {
            benchRetryAt = System.currentTimeMillis() + BENCH_RETRY_MS
            benchRetryKey = benchKey
            Log.w(TAG, "the talk bench measured nothing; it tries again in ${BENCH_RETRY_MS / 60_000} minutes: $result")
            handler.post { tick() }
            return
        }
        val drafter = result.optString("drafter").takeIf { it in listOf(LlamaChoice.DRAFTER_ON, LlamaChoice.DRAFTER_OFF, LlamaChoice.DRAFTER_FAILED) }
        main.choice.keepBench(benchKey, result.optInt("batch", LlamaPlan.BATCH), drafter, result)
        if (!result.optBoolean("memory_ok", true)) {
            val step = main.choice.step(benchKey) ?: main.planned?.step ?: 0
            main.choice.keep(benchKey, step + 1, "less than ${LlamaPlan.gb(LlamaPlan.FREE_WITH_BOTH)} stayed free with both models running")
        }
        speed.clear()
        handler.post { tick() }
    }

    private fun watchSpeed() {
        val now = System.currentTimeMillis()
        if (talkBench != null || now - metricsAt < METRICS_MS) return
        metricsAt = now
        speed.add(now, main.metrics())
        slow = speed.slow(main.choice.bench(mainKey)?.optDouble("write_tps")?.takeIf { !it.isNaN() })
    }

    private fun tickPace() {
        val (headroom, status) = Thermal.read(this)
        val level = heatLevel.update(System.currentTimeMillis(), headroom, status)
        heat = JSONObject()
            .put("headroom", if (headroom.isNaN()) -1.0 else Math.round(headroom * 100) / 100.0)
            .put("status", status)
            .put("level", level)
        try {
            PaceFile.write(File(paths.run, PaceFile.NAME), heat, slow)
        } catch (e: Exception) {
            Log.w(TAG, "could not write the pace", e)
        }
    }

    private fun tickUsb() {
        if (config.link == PebbleConfig.LINK_USB) {
            val bridge = usb ?: UsbBridge(this, PebbleConfig.USB_PORT).also {
                it.start()
                usb = it
            }
            bridge.tick()
        } else if (usb != null && !pairing) {
            usb?.stop()
            usb = null
        }
    }

    private fun tickLock(now: Long) {
        try {
            kiosk.enforceAdb(now)
            if (kiosk.kioskPauseOver(now)) {
                Log.i(TAG, "the kiosk pause is over; locking the phone again")
                startActivity(Intent(this, HomeActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_REORDER_TO_FRONT))
            }
            val wanted = config.link == PebbleConfig.LINK_USB || kiosk.adbOpen(now) || pairing
            if (wanted != usbWanted) {
                usbWanted = wanted
                usbData = kiosk.usbData(wanted)
            }
        } catch (e: Exception) {
            Log.w(TAG, "could not keep the phone locked down", e)
        }
    }

    private fun pairBody() {
        if (pairing) return
        pairing = true
        usbWanted = null
        tickLock(System.currentTimeMillis())
        pairSaid = JSONObject().put("ok", false).put("busy", true).put("at", System.currentTimeMillis()).put("message", "Pairing with the body over the USB cable...")
        writeStatus()
        val temporary = usb == null
        val bridge = usb ?: UsbBridge(this, PebbleConfig.USB_PORT).also { it.start() }
        if (temporary) usb = bridge
        Thread({
            val result = try {
                var waited = 0
                while (!bridge.opened() && waited < PAIR_OPEN_MS) {
                    bridge.tick()
                    if (bridge.opened()) break
                    Thread.sleep(500)
                    waited += 500
                }
                val channel = bridge.channel()
                if (channel == null) {
                    BodyPairing.Result(false, "the body is not reachable over the USB cable: ${bridge.problem.ifEmpty { "plug the phone into the ESP32's USB port and switch the body on" }}")
                } else {
                    try {
                        BodyPairing.pair(channel, { BodyKey.keep(it) }, { BodyKey.mac(it) })
                    } finally {
                        bridge.release()
                    }
                }
            } catch (e: Exception) {
                Log.w(TAG, "pairing failed", e)
                BodyPairing.Result(false, "pairing failed: ${e.message}")
            }
            handler.post {
                pairing = false
                usbWanted = null
                if (temporary && config.link != PebbleConfig.LINK_USB) {
                    bridge.stop()
                    if (usb === bridge) usb = null
                }
                pairSaid = JSONObject().put("ok", result.ok).put("at", System.currentTimeMillis()).put("message", if (result.ok) result.message else "Not paired: ${result.message}.")
                Log.i(TAG, "pairing: ${result.message}")
                if (result.ok) {
                    watchdog.planned()
                    if (brainPid() != null) BrainService.stop(this)
                }
                tick()
            }
        }, "pebble-pair").start()
    }

    private fun benchStatus(): Any {
        val bench = talkBench
        val now = System.currentTimeMillis()
        if (bench != null) {
            return JSONObject()
                .put("measuring", bench.phase)
                .put("step", TalkBench.step(bench.phase))
                .put("steps", TalkBench.STEPS)
                .put("what", TalkBench.plain(bench.phase))
                .put("for_s", (now - benchStartedAt) / 1000)
                .put("problem", benchProblem)
        }
        main.choice.bench(mainKey)?.let { return it }
        if (config.bench && mainKey.isNotEmpty() && benchRetryKey == mainKey && now < benchRetryAt && (main.kind.isEmpty() || main.kind == ModelFiles.STOPPED)) return JSONObject().put("again_in_s", (benchRetryAt - now) / 1000)
        return JSONObject.NULL
    }

    private fun writeStatus() {
        val (code, at) = readExit()
        val beat = heartbeat()
        val status = JSONObject()
            .put("at", System.currentTimeMillis())
            .put("brain", JSONObject()
                .put("want", want.name.lowercase())
                .put("alive", brainPid() != null)
                .put("started_at", startedAt)
                .put("heartbeat_at", beat)
                .put("last_exit", code ?: JSONObject.NULL)
                .put("last_exit_at", at)
                .put("restarts", watchdog.restarts)
                .put("why", watchdog.lastWhy))
            .put("models", JSONObject().put("main", main.status().put("bench", benchStatus())).put("sub", sub.status()))
            .put("heat", heat)
            .put("speed", speed.json(main.choice.bench(mainKey)?.optDouble("write_tps")?.takeIf { !it.isNaN() }))
            .put("usb", usb?.status() ?: JSONObject.NULL)
            .put("receiver", receiver.status())
            .put("models_in", JSONObject()
                .put("checking", importer.busy)
                .put("refused", org.json.JSONArray(importer.refusals().map { JSONObject().put("name", it.name).put("why", it.why) })))
            .put("body_key", JSONObject()
                .put("paired", BodyKey.has())
                .put("level", BodyKey.level() ?: JSONObject.NULL)
                .put("pairing", pairing)
                .put("said", pairSaid))
            .put("lock", JSONObject()
                .put("adb_until", kiosk.adbAllowedUntil())
                .put("adb_open", kiosk.adbOpen(System.currentTimeMillis()))
                .put("debug", nz.pebble.robot.BuildConfig.DEBUG)
                .put("usb_data", usbData))
            .put("charging", plugged)
            .put("resting", paths.rest.exists())
            .put("config", config.toJson())
        try {
            Atomic.write(File(paths.run, "status.json"), status.toString().toByteArray())
        } catch (e: Exception) {
            Log.w(TAG, "could not write the status", e)
        }
    }

    override fun onDestroy() {
        stopBench()
        handler.removeCallbacksAndMessages(null)
        try {
            unregisterReceiver(power)
        } catch (e: Exception) {
            Log.d(TAG, "power receiver was not registered")
        }
        main.stop()
        sub.stop()
        usb?.stop()
        receiver.close()
        thread.quitSafely()
        wake?.release()
        super.onDestroy()
    }

    companion object {
        const val TAG = "PebbleKeeper"
        const val NOTE_ID = 1
        const val TICK_MS = 5_000L
        const val BENCH_PORT = 8090
        const val BENCH_RETRY_MS = 30 * 60_000L
        const val METRICS_MS = 60_000L
        const val ACTION_PAUSE = "nz.pebble.robot.PAUSE"
        const val ACTION_RESUME = "nz.pebble.robot.RESUME"
        const val ACTION_RELOAD = "nz.pebble.robot.RELOAD"
        const val ACTION_MEASURE_AGAIN = "nz.pebble.robot.MEASURE_AGAIN"
        const val ACTION_RECEIVE = "nz.pebble.robot.RECEIVE"
        const val ACTION_RESTART_BRAIN = "nz.pebble.robot.RESTART_BRAIN"
        const val ACTION_HOLD = "nz.pebble.robot.HOLD_BRAIN"
        const val ACTION_RELEASE = "nz.pebble.robot.RELEASE_BRAIN"
        const val EXTRA_AFTER_MS = "after_ms"
        const val HOLD_MS = 120_000L
        const val MAX_AFTER_MS = 10 * 60_000L
        const val ACTION_CLOSE_RECEIVER = "nz.pebble.robot.CLOSE_RECEIVER"
        const val EXTRA_MINUTES = "minutes"
        const val ACTION_PAIR_BODY = "nz.pebble.robot.PAIR_BODY"
        const val ACTION_FORGET_BODY_KEY = "nz.pebble.robot.FORGET_BODY_KEY"
        const val PAIR_OPEN_MS = 8_000

        fun start(context: Context, action: String? = null, extras: Intent.() -> Unit = {}) {
            val intent = Intent(context, KeeperService::class.java)
            if (action != null) intent.action = action
            intent.extras()
            context.startForegroundService(intent)
        }
    }
}

class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        try {
            KeeperService.start(context)
        } catch (e: Exception) {
            Log.e(KeeperService.TAG, "could not start after ${intent.action}", e)
        }
        if (intent.action == Intent.ACTION_MY_PACKAGE_REPLACED) {
            context.startActivity(Intent(context, HomeActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        }
    }
}

private class Planned(val server: LlamaPlan.Server?, val why: String, val kind: String)
