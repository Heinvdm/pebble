package nz.pebble.robot.ui

import android.app.Activity
import android.app.AlertDialog
import android.text.InputType
import android.widget.EditText
import android.widget.Toast
import nz.pebble.robot.Paths
import nz.pebble.robot.admin.AdminPin
import nz.pebble.robot.admin.OwnerFinger
import kotlin.concurrent.thread

object OwnerGate {
    fun check(activity: Activity, title: String, allowFinger: Boolean = true, ok: () -> Unit) {
        val finger = OwnerFinger(activity)
        if (allowFinger && finger.enabled()) {
            finger.ask(activity, title, ok) { why ->
                if (why.isNotEmpty()) Toast.makeText(activity, why, Toast.LENGTH_LONG).show()
                askPin(activity, title, ok)
            }
        } else {
            askPin(activity, title, ok)
        }
    }

    fun askPin(activity: Activity, title: String, ok: () -> Unit) {
        val pin = AdminPin(Paths(activity).pin)
        val field = EditText(activity).apply {
            inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_VARIATION_PASSWORD
            hint = "Admin PIN"
        }
        AlertDialog.Builder(activity)
            .setTitle(title)
            .setView(field)
            .setPositiveButton("OK") { _, _ ->
                val typed = field.text.toString()
                thread {
                    val result = pin.check(typed)
                    activity.runOnUiThread {
                        if (result.ok) ok() else Toast.makeText(activity, result.message, Toast.LENGTH_LONG).show()
                    }
                }
            }
            .setNegativeButton("Cancel", null)
            .show()
    }
}
