package nz.pebble.robot.brain

import android.content.Context
import android.net.nsd.NsdManager
import android.net.nsd.NsdServiceInfo
import android.util.Log
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicReference

object Discover {
    const val TAG = "PebbleDiscover"
    const val SERVICE = "_pebble._tcp."

    fun find(context: Context, timeoutMs: Long): String? {
        val nsd = context.getSystemService(NsdManager::class.java) ?: return null
        val found = AtomicReference<String?>(null)
        val done = CountDownLatch(1)
        val listener = object : NsdManager.DiscoveryListener {
            override fun onStartDiscoveryFailed(serviceType: String?, errorCode: Int) {
                Log.w(TAG, "discovery failed to start: $errorCode")
                done.countDown()
            }

            override fun onStopDiscoveryFailed(serviceType: String?, errorCode: Int) = Unit
            override fun onDiscoveryStarted(serviceType: String?) = Unit
            override fun onDiscoveryStopped(serviceType: String?) = Unit
            override fun onServiceLost(serviceInfo: NsdServiceInfo?) = Unit

            override fun onServiceFound(serviceInfo: NsdServiceInfo) {
                @Suppress("DEPRECATION")
                nsd.resolveService(serviceInfo, object : NsdManager.ResolveListener {
                    override fun onResolveFailed(serviceInfo: NsdServiceInfo?, errorCode: Int) {
                        Log.w(TAG, "could not resolve ${serviceInfo?.serviceName}: $errorCode")
                    }

                    override fun onServiceResolved(serviceInfo: NsdServiceInfo) {
                        @Suppress("DEPRECATION")
                        val address = serviceInfo.host?.hostAddress
                        if (address != null && found.compareAndSet(null, address)) done.countDown()
                    }
                })
            }
        }
        try {
            nsd.discoverServices(SERVICE, NsdManager.PROTOCOL_DNS_SD, listener)
            done.await(timeoutMs, TimeUnit.MILLISECONDS)
        } catch (e: Exception) {
            Log.w(TAG, "discovery failed", e)
        } finally {
            try {
                nsd.stopServiceDiscovery(listener)
            } catch (e: Exception) {
                Log.d(TAG, "discovery was not running")
            }
        }
        return found.get()
    }
}
