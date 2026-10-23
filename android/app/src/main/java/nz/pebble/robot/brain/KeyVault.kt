package nz.pebble.robot.brain

import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyInfo
import android.security.keystore.KeyProperties
import android.security.keystore.StrongBoxUnavailableException
import android.util.Log
import org.json.JSONObject
import java.io.File
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.SecretKeyFactory
import javax.crypto.spec.GCMParameterSpec

class KeyVault(private val context: Context, val wrappedFile: File) {
    private val lock = Any()

    private fun store(): KeyStore = KeyStore.getInstance(PROVIDER).apply { load(null) }

    private fun key(): SecretKey? = store().getKey(ALIAS, null) as? SecretKey

    fun exists(): Boolean = synchronized(lock) { store().containsAlias(ALIAS) }

    fun create(): Boolean = synchronized(lock) {
        val keystore = store()
        if (keystore.containsAlias(ALIAS)) keystore.deleteEntry(ALIAS)
        val strongbox = Build.VERSION.SDK_INT >= 28 && context.packageManager.hasSystemFeature(PackageManager.FEATURE_STRONGBOX_KEYSTORE)
        if (strongbox) {
            try {
                generate(true)
                return true
            } catch (e: StrongBoxUnavailableException) {
                Log.w(TAG, "StrongBox refused the key; using the phone's trusted environment instead", e)
            } catch (e: Exception) {
                Log.w(TAG, "StrongBox key failed; using the phone's trusted environment instead", e)
            }
        }
        generate(false)
        false
    }

    private fun generate(strongbox: Boolean) {
        val spec = KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
            .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
            .setKeySize(256)
            .setUserAuthenticationRequired(false)
            .setRandomizedEncryptionRequired(true)
            .apply { if (strongbox) setIsStrongBoxBacked(true) }
            .build()
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, PROVIDER)
        generator.init(spec)
        generator.generateKey()
    }

    fun wrap(data: ByteArray): ByteArray = synchronized(lock) {
        val secret = key() ?: throw IllegalStateException("there is no keystore key to wrap with")
        val cipher = Cipher.getInstance(TRANSFORM)
        cipher.init(Cipher.ENCRYPT_MODE, secret)
        cipher.updateAAD(AAD)
        val iv = cipher.iv
        val sealed = cipher.doFinal(data)
        byteArrayOf(VERSION, iv.size.toByte()) + iv + sealed
    }

    fun unwrap(blob: ByteArray): ByteArray = synchronized(lock) {
        val secret = key() ?: throw IllegalStateException("there is no keystore key to unwrap with")
        val parts = Blob.parse(blob)
        val cipher = Cipher.getInstance(TRANSFORM)
        cipher.init(Cipher.DECRYPT_MODE, secret, GCMParameterSpec(128, parts.iv))
        cipher.updateAAD(AAD)
        cipher.doFinal(parts.sealed)
    }

    fun delete() = synchronized(lock) {
        val keystore = store()
        if (keystore.containsAlias(ALIAS)) keystore.deleteEntry(ALIAS)
    }

    fun info(): JSONObject = synchronized(lock) {
        val out = JSONObject().put("exists", false).put("alias", ALIAS).put("file", wrappedFile.path).put("wrapped", wrappedFile.exists())
        val secret = key() ?: return out
        out.put("exists", true)
        try {
            val info = SecretKeyFactory.getInstance(secret.algorithm, PROVIDER).getKeySpec(secret, KeyInfo::class.java) as KeyInfo
            if (Build.VERSION.SDK_INT >= 31) {
                val level = info.securityLevel
                out.put("level", when (level) {
                    KeyProperties.SECURITY_LEVEL_STRONGBOX -> "strongbox"
                    KeyProperties.SECURITY_LEVEL_TRUSTED_ENVIRONMENT -> "trusted environment"
                    KeyProperties.SECURITY_LEVEL_SOFTWARE -> "software"
                    else -> "unknown"
                })
                out.put("strongbox", level == KeyProperties.SECURITY_LEVEL_STRONGBOX)
                out.put("secure", level == KeyProperties.SECURITY_LEVEL_STRONGBOX || level == KeyProperties.SECURITY_LEVEL_TRUSTED_ENVIRONMENT)
            } else {
                @Suppress("DEPRECATION")
                out.put("secure", info.isInsideSecureHardware)
            }
            out.put("needs_unlock", info.isUserAuthenticationRequired)
        } catch (e: Exception) {
            out.put("problem", e.message ?: e.javaClass.simpleName)
        }
        out
    }

    object Blob {
        data class Parts(val iv: ByteArray, val sealed: ByteArray)

        fun parse(blob: ByteArray): Parts {
            require(blob.size > 2 && blob[0] == VERSION) { "the wrapped key has an unknown format" }
            val ivLength = blob[1].toInt() and 0xFF
            require(ivLength in 12..16 && blob.size > 2 + ivLength + 16) { "the wrapped key is cut short" }
            return Parts(blob.copyOfRange(2, 2 + ivLength), blob.copyOfRange(2 + ivLength, blob.size))
        }
    }

    companion object {
        const val TAG = "PebbleKeys"
        const val PROVIDER = "AndroidKeyStore"
        const val ALIAS = "pebble-device-key-wrap"
        const val TRANSFORM = "AES/GCM/NoPadding"
        const val VERSION: Byte = 1
        val AAD = "pebble-device-key v1".toByteArray()
    }
}
