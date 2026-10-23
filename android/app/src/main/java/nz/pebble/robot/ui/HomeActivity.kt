package nz.pebble.robot.ui

import android.annotation.SuppressLint
import android.app.Activity
import android.content.Intent
import android.content.pm.ActivityInfo
import android.graphics.Color
import android.net.Uri
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.view.WindowInsets
import android.view.WindowInsetsController
import android.view.WindowManager
import android.webkit.PermissionRequest
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.FrameLayout
import android.widget.TextView
import nz.pebble.robot.Paths
import nz.pebble.robot.PebbleConfig
import nz.pebble.robot.admin.AdminPin
import nz.pebble.robot.admin.Kiosk
import nz.pebble.robot.keeper.KeeperService
import org.json.JSONObject
import java.io.ByteArrayInputStream
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import kotlin.concurrent.thread

class HomeActivity : Activity() {
    private lateinit var paths: Paths
    private lateinit var kiosk: Kiosk
    private lateinit var web: WebView
    private lateinit var note: TextView
    private lateinit var band: TextView
    private val handler = Handler(Looper.getMainLooper())
    private var faceShown = false
    private var downSince = 0L
    private var taps = ArrayList<Long>()
    private var policiesApplied = false

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        paths = Paths(this).ensure()
        kiosk = Kiosk(this)
        val config = PebbleConfig.load(paths.config)
        requestedOrientation = orientation(config)
        setShowWhenLocked(true)
        setTurnScreenOn(true)
        if (!kiosk.isOwner) window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        web = WebView(this)
        web.setBackgroundColor(Color.BLACK)
        web.settings.apply {
            javaScriptEnabled = true
            mediaPlaybackRequiresUserGesture = false
            allowFileAccess = false
            allowContentAccess = false
            setGeolocationEnabled(false)
            safeBrowsingEnabled = false
            domStorageEnabled = true
            builtInZoomControls = false
            displayZoomControls = false
            setSupportZoom(false)
        }
        web.isVerticalScrollBarEnabled = false
        web.isHorizontalScrollBarEnabled = false
        web.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean = !local(request.url)

            override fun shouldInterceptRequest(view: WebView, request: WebResourceRequest): WebResourceResponse? {
                if (local(request.url)) return null
                return WebResourceResponse("text/plain", "utf-8", 403, "Forbidden", emptyMap(), ByteArrayInputStream(ByteArray(0)))
            }
        }
        web.webChromeClient = object : WebChromeClient() {
            override fun onPermissionRequest(request: PermissionRequest) = request.deny()
        }
        note = TextView(this).apply {
            setTextColor(Color.rgb(200, 210, 225))
            textSize = 18f
            gravity = Gravity.CENTER
            setBackgroundColor(Color.BLACK)
            text = "Pebble is waking up..."
        }
        band = TextView(this).apply {
            setTextColor(Color.rgb(150, 160, 175))
            textSize = 15f
            gravity = Gravity.CENTER
            maxLines = 3
            val side = (32 * resources.displayMetrics.density).toInt()
            setPadding(side, 0, side, (10 * resources.displayMetrics.density).toInt())
            visibility = View.GONE
            isClickable = false
            isFocusable = false
        }
        val root = FrameLayout(this)
        root.addView(web, FrameLayout.LayoutParams(FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.MATCH_PARENT))
        root.addView(band, FrameLayout.LayoutParams(FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.WRAP_CONTENT, Gravity.BOTTOM))
        root.addView(note, FrameLayout.LayoutParams(FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.MATCH_PARENT))
        setContentView(root)
        web.post { android.util.Log.i("PebbleHome", "the face is drawn with hardware acceleration: ${web.isHardwareAccelerated}") }
        hideBars()
        KeeperService.start(this)
        if (intent?.action == "android.hardware.usb.action.USB_DEVICE_ATTACHED") KeeperService.start(this)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        KeeperService.start(this)
    }

    private fun local(uri: Uri): Boolean = uri.scheme == "http" && (uri.host == "127.0.0.1" || uri.host == "localhost") && uri.port == PebbleConfig.SCREEN_PORT

    private fun hideBars() {
        window.insetsController?.let {
            it.hide(WindowInsets.Type.statusBars() or WindowInsets.Type.navigationBars())
            it.systemBarsBehavior = WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
        }
    }

    override fun onResume() {
        super.onResume()
        hideBars()
        if (!policiesApplied) {
            policiesApplied = true
            kiosk.applyPolicies()
        }
        if (File(paths.run, DEGRADED).exists()) {
            File(paths.run, DEGRADED).delete()
            KeeperService.start(this, KeeperService.ACTION_RESTART_BRAIN)
        }
        if (!AdminPin(paths.pin).isSet()) {
            startActivity(Intent(this, AdminActivity::class.java).putExtra(AdminActivity.EXTRA_SETUP, true))
            return
        }
        if (!kioskPaused()) kiosk.enter(this)
        KeeperService.start(this)
        handler.post(poll)
    }

    override fun onPause() {
        handler.removeCallbacks(poll)
        super.onPause()
    }

    private fun kioskPaused(): Boolean = File(paths.run, KIOSK_PAUSE).let { it.exists() && (it.readText().trim().toLongOrNull() ?: 0L) > System.currentTimeMillis() }

    private val poll = object : Runnable {
        override fun run() {
            thread {
                val up = faceUp()
                val status = readStatus()
                runOnUiThread { show(up, status) }
            }
            handler.postDelayed(this, POLL_MS)
        }
    }

    private fun faceUp(): Boolean = try {
        val c = URL("http://127.0.0.1:${PebbleConfig.SCREEN_PORT}/health").openConnection() as HttpURLConnection
        c.connectTimeout = 800
        c.readTimeout = 1500
        val ok = c.responseCode == 200
        c.disconnect()
        ok
    } catch (e: Exception) {
        false
    }

    private fun readStatus(): JSONObject? = try {
        JSONObject(File(paths.run, "status.json").readText())
    } catch (e: Exception) {
        null
    }

    private fun show(up: Boolean, status: JSONObject?) {
        val now = System.currentTimeMillis()
        val said = if (up) FaceNote.text(status, now) else null
        if (said == null) {
            band.visibility = View.GONE
        } else {
            if (band.text.toString() != said) band.text = said
            band.visibility = View.VISIBLE
            val step = (now / BAND_STEP_MS) % BAND_SPOTS
            val reach = BAND_DRIFT_DP * resources.displayMetrics.density
            band.translationX = ((step % 3) - 1) * reach
            band.translationY = -(step / 3) * reach
        }
        if (up) {
            downSince = 0L
            if (!faceShown) {
                web.loadUrl("http://127.0.0.1:${PebbleConfig.SCREEN_PORT}/")
                faceShown = true
            }
            note.visibility = View.GONE
            return
        }
        if (downSince == 0L) downSince = now
        if (!faceShown || now - downSince > DOWN_NOTE_MS) {
            note.visibility = View.VISIBLE
            val brain = status?.optJSONObject("brain")
            val why = brain?.optString("why").orEmpty()
            note.text = if (why.isEmpty()) "Pebble is waking up..." else "Pebble is waking up...\n\n$why"
        }
    }

    override fun dispatchTouchEvent(event: MotionEvent): Boolean {
        if (event.actionMasked == MotionEvent.ACTION_DOWN) {
            val corner = CORNER_DP * resources.displayMetrics.density
            if (event.x < corner && event.y < corner) {
                val now = System.currentTimeMillis()
                taps.add(now)
                taps.removeAll { now - it > TAP_WINDOW_MS }
                if (taps.size >= TAPS) {
                    taps.clear()
                    OwnerGate.check(this, "Open Pebble's admin screen") {
                        startActivity(Intent(this, AdminActivity::class.java))
                    }
                }
            }
        }
        return super.dispatchTouchEvent(event)
    }

    @Deprecated("Deprecated in Java")
    override fun onBackPressed() = Unit

    companion object {
        fun orientation(config: PebbleConfig): Int = if (config.reverse) ActivityInfo.SCREEN_ORIENTATION_REVERSE_LANDSCAPE else ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE

        const val POLL_MS = 2_000L
        const val DOWN_NOTE_MS = 10_000L
        const val CORNER_DP = 72
        const val TAPS = 5
        const val TAP_WINDOW_MS = 3_000L
        const val KIOSK_PAUSE = "kiosk-paused-until"
        const val DEGRADED = "brain-without-camera"
        const val BAND_STEP_MS = 20_000L
        const val BAND_SPOTS = 6L
        const val BAND_DRIFT_DP = 6f
    }
}
