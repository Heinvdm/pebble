package nz.pebble.robot

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import android.os.Process

class PebbleApp : Application() {
    override fun onCreate() {
        super.onCreate()
        if (Process.isIsolated()) return
        val channel = NotificationChannel(CHANNEL, getString(R.string.channel_name), NotificationManager.IMPORTANCE_MIN)
        channel.setShowBadge(false)
        getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
    }

    companion object {
        const val CHANNEL = "pebble"
    }
}
