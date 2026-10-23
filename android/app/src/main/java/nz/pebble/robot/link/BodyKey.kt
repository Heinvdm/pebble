package nz.pebble.robot.link

import android.os.Build
import android.security.keystore.KeyInfo
import android.security.keystore.KeyProperties
import android.security.keystore.KeyProtection
import android.util.Log
import java.security.KeyStore
import javax.crypto.Mac
import javax.crypto.SecretKey
import javax.crypto.SecretKeyFactory
import javax.crypto.spec.SecretKeySpec

object BodyKey {
    const val TAG = "PebbleBodyKey"
    const val ALIAS = "pebble-body-link"
    const val PROVIDER = "AndroidKeyStore"
    const val ALGORITHM = "HmacSHA256"

    private val lock = Any()

    private fun store(): KeyStore = KeyStore.getInstance(PROVIDER).apply { load(null) }

    @JvmStatic
    fun has(): Boolean = synchronized(lock) {
        try {
            store().containsAlias(ALIAS)
        } catch (e: Exception) {
            Log.w(TAG, "the keystore could not be read", e)
            false
        }
    }

    @JvmStatic
    fun mac(message: ByteArray): ByteArray? = synchronized(lock) {
        try {
            val key = store().getKey(ALIAS, null) as? SecretKey ?: return null
            Mac.getInstance(ALGORITHM).apply { init(key) }.doFinal(message)
        } catch (e: Exception) {
            Log.w(TAG, "the body key could not be used", e)
            null
        }
    }

    fun keep(raw: ByteArray): String? = synchronized(lock) {
        val keystore = try {
            store()
        } catch (e: Exception) {
            return "the phone's keystore could not be opened: ${e.message}"
        }
        if (keystore.containsAlias(ALIAS)) keystore.deleteEntry(ALIAS)
        val entry = KeyStore.SecretKeyEntry(SecretKeySpec(raw, ALGORITHM))
        for (strongbox in listOf(true, false)) {
            if (strongbox && Build.VERSION.SDK_INT < 28) continue
            try {
                val protection = KeyProtection.Builder(KeyProperties.PURPOSE_SIGN or KeyProperties.PURPOSE_VERIFY)
                    .apply { if (strongbox) setIsStrongBoxBacked(true) }
                    .build()
                keystore.setEntry(ALIAS, entry, protection)
                return null
            } catch (e: Exception) {
                Log.w(TAG, if (strongbox) "StrongBox refused the body key; using the trusted environment" else "the keystore refused the body key", e)
                if (keystore.containsAlias(ALIAS)) keystore.deleteEntry(ALIAS)
            }
        }
        "the phone's keystore would not keep the body key"
    }

    fun forget() = synchronized(lock) {
        try {
            val keystore = store()
            if (keystore.containsAlias(ALIAS)) keystore.deleteEntry(ALIAS)
        } catch (e: Exception) {
            Log.w(TAG, "the body key could not be removed", e)
        }
    }

    fun level(): String? = synchronized(lock) {
        try {
            val key = store().getKey(ALIAS, null) as? SecretKey ?: return null
            if (Build.VERSION.SDK_INT < 31) return "secure hardware"
            val info = SecretKeyFactory.getInstance(key.algorithm, PROVIDER).getKeySpec(key, KeyInfo::class.java) as KeyInfo
            when (info.securityLevel) {
                KeyProperties.SECURITY_LEVEL_STRONGBOX -> "StrongBox"
                KeyProperties.SECURITY_LEVEL_TRUSTED_ENVIRONMENT -> "the trusted environment"
                KeyProperties.SECURITY_LEVEL_SOFTWARE -> "software"
                else -> "unknown"
            }
        } catch (e: Exception) {
            null
        }
    }
}
