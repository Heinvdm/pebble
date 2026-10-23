package nz.pebble.robot.ui

import android.annotation.SuppressLint
import android.app.Activity
import android.graphics.Color
import android.net.Uri
import android.os.Bundle
import android.view.Gravity
import android.view.ViewGroup
import android.view.WindowManager
import android.webkit.PermissionRequest
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.TextView
import nz.pebble.robot.Paths
import nz.pebble.robot.PebbleConfig
import java.io.ByteArrayInputStream

class MapActivity : Activity() {
    private lateinit var web: WebView
    private lateinit var note: TextView

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
        requestedOrientation = HomeActivity.orientation(PebbleConfig.load(Paths(this).config))
        web = WebView(this)
        web.setBackgroundColor(Color.rgb(16, 20, 28))
        web.settings.apply {
            javaScriptEnabled = true
            allowFileAccess = false
            allowContentAccess = false
            setGeolocationEnabled(false)
            safeBrowsingEnabled = false
            builtInZoomControls = true
            displayZoomControls = false
            setSupportZoom(true)
            useWideViewPort = true
            loadWithOverviewMode = true
        }
        web.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean = !allowed(request.url)

            override fun shouldInterceptRequest(view: WebView, request: WebResourceRequest): WebResourceResponse? {
                if (allowed(request.url)) return null
                return WebResourceResponse("text/plain", "utf-8", 403, "Forbidden", emptyMap(), ByteArrayInputStream(ByteArray(0)))
            }

            override fun onReceivedError(view: WebView, request: WebResourceRequest, error: WebResourceError) {
                if (request.isForMainFrame) show(NOT_RUNNING)
            }

            override fun onReceivedHttpError(view: WebView, request: WebResourceRequest, errorResponse: WebResourceResponse) {
                if (request.isForMainFrame) show(if (errorResponse.statusCode == 404) NO_MAP else NOT_RUNNING)
            }

            override fun onPageFinished(view: WebView, url: String) {
                if (note.text.isEmpty()) note.visibility = TextView.GONE
            }
        }
        web.webChromeClient = object : WebChromeClient() {
            override fun onPermissionRequest(request: PermissionRequest) = request.deny()
        }
        note = TextView(this).apply {
            setTextColor(Color.rgb(200, 210, 225))
            textSize = 18f
            gravity = Gravity.CENTER
            setBackgroundColor(Color.rgb(16, 20, 28))
        }
        val bar = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setBackgroundColor(Color.rgb(16, 20, 28))
            addView(Button(this@MapActivity).apply {
                text = "Again"
                isAllCaps = false
                setOnClickListener { load() }
            })
            addView(Button(this@MapActivity).apply {
                text = "Close"
                isAllCaps = false
                setOnClickListener { finish() }
            })
        }
        val frame = FrameLayout(this)
        frame.addView(web, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
        frame.addView(note, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
        val root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        root.addView(bar, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT))
        root.addView(frame, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f))
        setContentView(root)
        load()
    }

    private fun load() {
        note.text = ""
        note.visibility = TextView.GONE
        web.loadUrl("http://127.0.0.1:${PebbleConfig.SCREEN_PORT}/map")
    }

    private fun show(text: String) {
        note.text = text
        note.visibility = TextView.VISIBLE
    }

    override fun onDestroy() {
        web.destroy()
        super.onDestroy()
    }

    companion object {
        const val NOT_RUNNING = "The map shows while Pebble's brain is running."
        const val NO_MAP = "Pebble has no map yet."

        fun allowed(uri: Uri): Boolean = uri.scheme == "http" && (uri.host == "127.0.0.1" || uri.host == "localhost") && uri.port == PebbleConfig.SCREEN_PORT && (uri.path ?: "").let { it == "/map" || it.startsWith("/map.") || it.startsWith("/map/") }
    }
}
