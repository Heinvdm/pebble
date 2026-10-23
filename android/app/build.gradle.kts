import java.net.URI
import java.security.MessageDigest
import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("com.chaquo.python")
}

val brainDir = rootProject.file("../brain/pebble")
val brainOut = layout.buildDirectory.dir("generated/pebble/python")
val modelsOut = layout.buildDirectory.dir("generated/pebble/assets")
val vectorsOut = layout.buildDirectory.dir("generated/pebble/testres")
val vectorAssetsOut = layout.buildDirectory.dir("generated/pebble/testassets")
val llamaLibs = rootProject.file("llama/out/jniLibs")
val signing: File = (System.getenv("PEBBLE_SIGNING_PROPERTIES")?.takeIf { it.isNotBlank() }?.let { File(it) }
    ?: File(System.getProperty("user.home"), ".pebble/signing/keystore.properties"))
val sherpaVersion = "1.13.8"
val sherpaSha256 = "b22c3fc1b6a45666d28892bb2f7694beeb77a8362d7ebd77c1a5431ec9435471"
val sherpaAar = rootProject.file("libs/sherpa-onnx-static-link-onnxruntime-$sherpaVersion.aar")
val depthModel = rootProject.file("models/depth_anything_v2_small_fp16.onnx")
val depthUrl = "https://huggingface.co/onnx-community/depth-anything-v2-small/resolve/4472b7362082ad9968fee890ca0f1e5aca36b93d/onnx/model_fp16.onnx"
val depthSha256 = "2df6223f206b5164e21f664ace61dabeb9bb6a49b8b5a3e00510b4807d0f5b04"
val turnModel = rootProject.file("models/smart-turn-v3.2-cpu.onnx")
val turnUrl = "https://huggingface.co/pipecat-ai/smart-turn-v3/resolve/f766f81d3cfdf7737ac64aad813d91bbfd56bf93/smart-turn-v3.2-cpu.onnx"
val turnSha256 = "2bb026316b14a660486a75b1733cd3fbab8c2fd0314dc9af7be49f8cca967e4f"
val recallBase = "https://huggingface.co/Snowflake/snowflake-arctic-embed-xs/resolve/d8c86521100d3556476a063fc2342036d45c106f"
val recallModel = rootProject.file("models/arctic_embed_xs_int8.onnx")
val recallModelSha256 = "e6aa5e656466a73d7c3111e9a3378bd13e5b93af30eaac2b3f13fd56692589a1"
val recallVocab = rootProject.file("models/arctic_embed_xs_vocab.txt")
val recallVocabSha256 = "07eced375cec144d27c900241f3e339478dec958f92fddbc551f295c992038a3"

fun sha256Of(file: File): String {
    val digest = MessageDigest.getInstance("SHA-256")
    file.inputStream().use { input ->
        val buffer = ByteArray(1 shl 20)
        while (true) {
            val n = input.read(buffer)
            if (n < 0) break
            digest.update(buffer, 0, n)
        }
    }
    return digest.digest().joinToString("") { "%02x".format(it) }
}

fun fetchPinned(url: String, sha256: String, target: File, what: String) {
    if (target.exists() && sha256Of(target) == sha256) return
    target.parentFile.mkdirs()
    val part = File(target.path + ".part")
    URI(url).toURL().openStream().use { input -> part.outputStream().use { input.copyTo(it) } }
    check(sha256Of(part) == sha256) { "the downloaded $what does not match its pinned SHA-256" }
    target.delete()
    check(part.renameTo(target)) { "could not keep the $what" }
}

val fetchSherpa by tasks.registering {
    outputs.file(sherpaAar)
    doLast {
        fetchPinned("https://github.com/k2-fsa/sherpa-onnx/releases/download/v$sherpaVersion/sherpa-onnx-static-link-onnxruntime-$sherpaVersion.aar", sherpaSha256, sherpaAar, "sherpa-onnx AAR")
    }
}

val fetchDepth by tasks.registering {
    outputs.file(depthModel)
    doLast {
        fetchPinned(depthUrl, depthSha256, depthModel, "fp16 depth model")
    }
}

val fetchTurn by tasks.registering {
    outputs.file(turnModel)
    onlyIf { (findProperty("pebble.turnModel") as String?) != "off" }
    doLast {
        fetchPinned(turnUrl, turnSha256, turnModel, "end-of-turn model")
    }
}

val fetchRecall by tasks.registering {
    outputs.files(recallModel, recallVocab)
    onlyIf { (findProperty("pebble.recallModel") as String?) != "off" }
    doLast {
        fetchPinned("$recallBase/onnx/model_int8.onnx", recallModelSha256, recallModel, "sentence model")
        fetchPinned("$recallBase/vocab.txt", recallVocabSha256, recallVocab, "sentence model's word list")
    }
}

val syncBrain by tasks.registering(Sync::class) {
    from(brainDir) {
        exclude("**/__pycache__/**", "**/*.pyc", "web/vendor/**", "eyes/models/**", "hearing/models/*.onnx", "hearing/models/samples/**", "speech/models/**/*.onnx", "speech/models/**/*.wav", "speech/models/**/*.bin", "self/recall/models/**")
    }
    from(File(brainDir, "eyes/models")) {
        include("objects_vocab.json", "hazards_vocab.json")
        into("eyes/models")
    }
    into(brainOut.map { it.dir("pebble") })
}

val syncVectors by tasks.registering(Sync::class) {
    from(File(brainDir, "script/vectors")) {
        include("*.json")
    }
    into(vectorsOut.map { it.dir("script/vectors") })
}

val syncVectorAssets by tasks.registering(Sync::class) {
    from(File(brainDir, "script/vectors")) {
        include("*.json")
    }
    into(vectorAssetsOut.map { it.dir("vectors") })
}

val syncModels by tasks.registering(Sync::class) {
    dependsOn(fetchDepth, fetchTurn, fetchRecall)
    from(turnModel) {
        into("turn")
    }
    from(listOf(recallModel, recallVocab)) {
        into("recall")
    }
    from(File(brainDir, "eyes/models")) {
        include("face_detection_yunet_2023mar.onnx", "object_detection_nanodet_2022nov.onnx", "objects.onnx", "objects_vocab.json", "hazards.onnx", "hazards_vocab.json", "rtmpose_t_body7_256x192.onnx", "prints.onnx", "prints.json", "face_landmarks_detector.tflite", "*LICENSE*")
        into("models")
    }
    from(depthModel) {
        into("models")
    }
    from(File(brainDir, "hearing/models")) {
        include("yamnet.onnx", "YAMNET_LICENSE")
        into("models")
    }
    from((findProperty("pebble.speechModels") as String?)?.let { File(it) } ?: File(brainDir, "speech/models")) {
        include("**/*.onnx", "**/*.txt", "**/*.vocab", "**/speech.json", "**/*LICENSE*", "tests/*.wav")
        into("speech")
    }
    from(File(brainDir, "eyes/models/samples")) {
        include("*.jpg")
        into("samples")
    }
    into(modelsOut)
}

android {
    namespace = "nz.pebble.robot"
    compileSdk = 35

    defaultConfig {
        applicationId = "nz.pebble.robot"
        minSdk = 29
        targetSdk = 35
        val code = (findProperty("pebble.versionCode") as String?)?.toIntOrNull()?.takeIf { it > 0 } ?: 1
        versionCode = code
        versionName = (findProperty("pebble.versionName") as String?)?.takeIf { it.isNotBlank() } ?: "0.1.${code - 1}"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        ndk {
            abiFilters += (findProperty("pebble.abis") as String? ?: "arm64-v8a,x86_64").split(",").map { it.trim() }.filter { it.isNotEmpty() }
        }
    }

    signingConfigs {
        create("owner") {
            if (signing.exists()) {
                val props = Properties().apply { signing.inputStream().use { load(it) } }
                val named = File(props.getProperty("storeFile") ?: "")
                storeFile = if (named.isAbsolute) named else File(signing.parentFile, named.path)
                storePassword = props.getProperty("storePassword")
                keyAlias = props.getProperty("keyAlias")
                keyPassword = props.getProperty("keyPassword")
            }
        }
    }

    buildTypes {
        getByName("debug") {
            isDebuggable = true
        }
        getByName("release") {
            isDebuggable = false
            isMinifyEnabled = false
            signingConfig = if (signing.exists()) {
                signingConfigs.getByName("owner")
            } else {
                logger.warn("WARNING: no release signing key found (set PEBBLE_SIGNING_PROPERTIES or make ~/.pebble/signing/keystore.properties, see SETUP.md); the release APK is signed with the DEBUG key")
                signingConfigs.getByName("debug")
            }
        }
    }

    sourceSets {
        getByName("main") {
            jniLibs.srcDir(llamaLibs)
            assets.srcDir(modelsOut)
        }
        getByName("test") {
            resources.srcDir(vectorsOut)
        }
        getByName("androidTest") {
            assets.srcDir(vectorAssetsOut)
        }
    }

    packaging {
        jniLibs {
            useLegacyPackaging = true
            pickFirsts += listOf("**/libc++_shared.so")
            excludes += listOf("lib/x86/**", "lib/armeabi-v7a/**")
        }
    }

    androidResources {
        noCompress += listOf("onnx", "tflite")
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    buildFeatures {
        buildConfig = true
    }

    testOptions {
        unitTests.isReturnDefaultValues = true
    }
}

chaquopy {
    defaultConfig {
        version = "3.13"
        pip {
            install("cryptography==42.0.8")
            install("numpy==1.26.2")
        }
        extractPackages("pebble")
    }
    sourceSets {
        getByName("main") {
            srcDir(brainOut)
        }
    }
}

tasks.named("preBuild") {
    dependsOn(syncBrain, syncModels)
}

tasks.configureEach {
    if (name.startsWith("process") && name.endsWith("UnitTestJavaRes")) dependsOn(syncVectors)
    if (name.contains("AndroidTest") && name.contains("Assets")) dependsOn(syncVectorAssets)
    if (name.contains("PythonSources") || name.contains("PythonRequirements")) dependsOn(syncBrain)
    if (name.contains("Assets") || name.contains("Python")) dependsOn(syncModels)
}

tasks.withType<Test>().configureEach {
    dependsOn(fetchRecall)
    systemProperty("pebble.recallVocab", recallVocab.absolutePath)
}

dependencies {
    implementation("androidx.core:core-ktx:1.15.0")
    implementation("androidx.lifecycle:lifecycle-service:2.8.7")
    implementation("androidx.camera:camera-core:1.5.1")
    implementation("androidx.camera:camera-camera2:1.5.1")
    implementation("androidx.camera:camera-lifecycle:1.5.1")
    implementation("com.microsoft.onnxruntime:onnxruntime-android:1.30.0")
    implementation("org.opencv:opencv:4.12.0")
    implementation("com.github.mik3y:usb-serial-for-android:3.11.0")
    implementation(files(sherpaAar).builtBy(fetchSherpa))

    testImplementation("junit:junit:4.13.2")
    testImplementation("org.json:json:20250517")
    androidTestImplementation("androidx.test:runner:1.6.2")
    androidTestImplementation("androidx.test.ext:junit:1.2.1")
}
