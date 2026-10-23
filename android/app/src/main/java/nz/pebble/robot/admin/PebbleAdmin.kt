package nz.pebble.robot.admin

import android.app.admin.DeviceAdminReceiver
import android.content.ComponentName
import android.content.Context

class PebbleAdmin : DeviceAdminReceiver() {
    companion object {
        fun component(context: Context): ComponentName = ComponentName(context, PebbleAdmin::class.java)
    }
}
