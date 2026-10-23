package nz.pebble.robot.admin

import android.app.Activity
import android.app.KeyguardManager
import android.content.Context
import android.content.pm.PackageManager
import android.hardware.biometrics.BiometricManager
import android.hardware.biometrics.BiometricPrompt
import android.os.Build
import android.os.CancellationSignal
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyPermanentlyInvalidatedException
import android.security.keystore.KeyProperties
import android.util.Log
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey

class OwnerFinger(private val context: Context) {

    fun possible(): String? {
        if (!context.packageManager.hasSystemFeature(PackageManager.FEATURE_FINGERPRINT) && Build.VERSION.SDK_INT < 30) return "this phone has no fingerprint reader"
        if (!context.getSystemService(KeyguardManager::class.java).isDeviceSecure) {
            return "Android only keeps fingerprints behind a screen lock (PIN, pattern or password), and Pebble runs without one so it can start by itself after a restart"
        }
        if (Build.VERSION.SDK_INT >= 30) {
            val can = context.getSystemService(BiometricManager::class.java).canAuthenticate(BiometricManager.Authenticators.BIOMETRIC_STRONG)
            if (can != BiometricManager.BIOMETRIC_SUCCESS) return "this phone has no strong fingerprint set up in Android settings"
        }
        return null
    }

    fun enabled(): Boolean = try {
        store().containsAlias(ALIAS)
    } catch (e: Exception) {
        false
    }

    fun enable(): String? {
        possible()?.let { return it }
        return try {
            val builder = KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .setUserAuthenticationRequired(true)
                .setInvalidatedByBiometricEnrollment(true)
            if (Build.VERSION.SDK_INT >= 30) builder.setUserAuthenticationParameters(0, KeyProperties.AUTH_BIOMETRIC_STRONG)
            val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
            generator.init(builder.build())
            generator.generateKey()
            null
        } catch (e: Exception) {
            Log.w(TAG, "could not make the fingerprint key", e)
            "the fingerprint could not be switched on: ${e.message}"
        }
    }

    fun disable() {
        try {
            store().deleteEntry(ALIAS)
        } catch (e: Exception) {
            Log.d(TAG, "no fingerprint key to delete")
        }
    }

    fun ask(activity: Activity, title: String, ok: () -> Unit, fallback: (String) -> Unit) {
        if (!enabled()) {
            fallback("")
            return
        }
        val cipher = try {
            Cipher.getInstance("AES/GCM/NoPadding").apply { init(Cipher.ENCRYPT_MODE, store().getKey(ALIAS, null) as SecretKey) }
        } catch (e: KeyPermanentlyInvalidatedException) {
            disable()
            fallback("A fingerprint was added or removed in Android settings, so fingerprints no longer open Pebble. Enter the PIN, then switch the fingerprint on again.")
            return
        } catch (e: Exception) {
            fallback("The fingerprint is not available: ${e.message}")
            return
        }
        val executor = activity.mainExecutor
        val prompt = BiometricPrompt.Builder(activity)
            .setTitle(title)
            .setSubtitle("Owner only")
            .setNegativeButton("Use the PIN", executor) { _, _ -> fallback("") }
            .build()
        prompt.authenticate(BiometricPrompt.CryptoObject(cipher), CancellationSignal(), executor, object : BiometricPrompt.AuthenticationCallback() {
            override fun onAuthenticationSucceeded(result: BiometricPrompt.AuthenticationResult) {
                val proved = try {
                    result.cryptoObject?.cipher?.doFinal(CHALLENGE) != null
                } catch (e: Exception) {
                    false
                }
                if (proved) ok() else fallback("The fingerprint check did not finish. Enter the PIN.")
            }

            override fun onAuthenticationError(errorCode: Int, errString: CharSequence) {
                if (errorCode != BiometricPrompt.BIOMETRIC_ERROR_USER_CANCELED && errorCode != BiometricPrompt.BIOMETRIC_ERROR_CANCELED) fallback(errString.toString())
            }
        })
    }

    private fun store(): KeyStore = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }

    companion object {
        const val TAG = "PebbleFinger"
        const val ALIAS = "pebble-owner-finger"
        private val CHALLENGE = "pebble owner".toByteArray()
    }
}
