package nz.pebble.robot.brain

import com.chaquo.python.PyObject
import nz.pebble.robot.eyes.Eyes
import nz.pebble.robot.eyes.Torch
import nz.pebble.robot.recall.SentenceModel
import nz.pebble.robot.script.ScriptLink

class Bridge(
    private val keys: KeyVault,
    private val sensors: PhoneSensors?,
    private val speech: Speech?,
    private val eyes: Eyes?,
    private val power: Power?,
    private val alarm: Alarm? = null,
    private val lamp: Torch? = null,
    private val sentences: SentenceModel? = null,
    private val heat: () -> String = { "{}" },
    private val scripts: ScriptLink? = null,
) {
    fun keyFile(): String = keys.wrappedFile.path
    fun keyExists(): Boolean = keys.exists()
    fun keyCreate(): Boolean = keys.create()
    fun keyWrap(data: ByteArray): ByteArray = keys.wrap(data)
    fun keyUnwrap(blob: ByteArray): ByteArray = keys.unwrap(blob)
    fun keyDelete() = keys.delete()
    fun keyInfo(): String = keys.info().toString()

    fun battery(): String = sensors?.battery() ?: "{\"percent\": -1}"
    fun temperature(): Double = sensors?.temperature() ?: Double.NaN
    fun light(): Double = sensors?.light() ?: -1.0
    fun motion(): String = sensors?.motion() ?: ""
    fun proximity(): Double = sensors?.proximity() ?: -1.0
    fun pressure(): Double = sensors?.pressure() ?: -1.0
    fun sensorTap(on: Boolean) {
        sensors?.tap(on)
    }
    fun sensorRead(kind: String, from: Long, max: Int): String = sensors?.read(kind, from, max) ?: "{\"kind\": \"$kind\", \"total\": 0, \"rows\": []}"
    fun sensorInfo(): String = sensors?.info() ?: "{}"
    fun alarmSound(on: Boolean): Boolean = alarm?.sound(on) ?: false
    fun alarmSay(text: String): Boolean = alarm?.say(text) ?: false

    fun speak(text: String, whisper: Boolean): Boolean = speech?.speak(text, whisper) ?: false
    fun sayPart(id: String, text: String, last: Boolean, whisper: Boolean): Boolean = speech?.sayPart(id, text, last, whisper) ?: false
    fun stopSpeaking(): Double = speech?.stopSpeaking() ?: 0.0
    fun speechSink(sink: PyObject?) {
        speech?.setSink(sink)
    }
    fun speechConfig(config: String) {
        speech?.configure(config)
    }
    fun earsState(): String = speech?.state()?.toString() ?: "{\"listening\": false}"
    fun listen(on: Boolean) {
        speech?.listen(on)
    }
    fun earsSink(sink: PyObject?) {
        speech?.setEars(sink)
    }
    fun hearingInfo(): String = speech?.info() ?: "{\"available\": false}"
    fun soundTap(on: Boolean) {
        speech?.soundTap(on)
    }
    fun soundRead(from: Long, maxSamples: Int): ByteArray = speech?.soundRead(from, maxSamples) ?: ByteArray(0)
    fun soundInfo(): String = speech?.soundInfo() ?: "{\"running\": false}"
    fun soundScores(from: Long): String = speech?.soundScores(from) ?: "{\"total\": 0, \"rows\": []}"
    fun soundVectors(from: Long): String = speech?.soundVectors(from) ?: "{\"total\": 0, \"rows\": []}"
    fun highBand(from: Long): String = speech?.highBand(from) ?: "{\"total\": 0, \"rows\": [], \"on\": false}"
    fun highBandMoving(on: Boolean) {
        speech?.highBandMoving(on)
    }
    fun micPlan(): String = speech?.micPlan() ?: "{}"
    fun micProbe(options: String): String = speech?.micProbe(options) ?: "{\"problem\": \"no microphone in this process\"}"

    fun eyesSink(sink: PyObject?) {
        eyes?.setSink(sink) ?: throw IllegalStateException("the cameras are not available in this process")
    }
    fun eyesStart(config: String) {
        eyes?.start(config) ?: throw IllegalStateException("the cameras are not available in this process")
    }
    fun eyesStop() {
        eyes?.stop()
    }
    fun eyesUse(camera: String) {
        eyes?.use(camera)
    }
    fun eyesEnable(on: Boolean) {
        eyes?.enable(on)
    }
    fun eyesBusy(on: Boolean) {
        eyes?.busy(on)
    }
    fun eyesMoved() {
        eyes?.moved()
    }
    fun eyesLookClosely(id: Int) {
        eyes?.lookClosely(id)
    }
    fun eyesStatus(): String = eyes?.status() ?: "{}"
    fun eyesPrints(top: Int) {
        eyes?.wantPrints(top)
    }
    fun eyesHold(): String = eyes?.hold() ?: "{}"
    fun eyesEmbed(id: Int, boxes: String, size: Int): String = eyes?.embed(id, boxes, size) ?: "[]"
    fun eyesPropose(id: Int, score: Double): String = eyes?.propose(id, score) ?: "[]"
    fun eyesRelease(id: Int) {
        eyes?.release(id)
    }
    fun eyesMouths(on: Boolean, tailS: Double) {
        eyes?.mouths(on, tailS)
    }
    fun eyesHazardsEvery(seconds: Double) {
        eyes?.hazardsEvery(seconds)
    }
    fun eyesMoving(on: Boolean) {
        eyes?.moving(on)
    }
    fun eyesScanFloor() {
        eyes?.scanFloor()
    }
    fun eyesHead(head: String) {
        eyes?.head(head)
    }
    fun eyesSnapshot(camera: String, maxSide: Int, maxAgeS: Double): ByteArray = eyes?.snapshot(camera, maxSide, maxAgeS) ?: ByteArray(0)
    fun eyesCloseUp(maxSide: Int, zoom: Double): ByteArray = eyes?.closeUp(maxSide, zoom) ?: ByteArray(0)
    fun eyesCloseUpInfo(): String = eyes?.closeUpInfo() ?: "{\"problem\": \"the cameras are not available in this process\"}"

    fun torch(on: Boolean, level: Double, seconds: Double): String = lamp?.set(on, level, seconds)?.toString() ?: "{\"has_torch\": false, \"problem\": \"no torch in this process\"}"
    fun torchInfo(): String = lamp?.info()?.toString() ?: "{\"has_torch\": false}"

    fun powerOff(mode: String): String = power?.powerOff(mode) ?: "none"

    fun phoneHeat(): String = heat()

    fun recallChoice(): String = sentences?.choiceJson()?.toString() ?: NO_SENTENCES
    fun recallEmbed(texts: String, query: Boolean): ByteArray = sentences?.embedJson(texts, query) ?: ByteArray(0)
    fun recallInfo(): String = sentences?.info()?.toString() ?: NO_SENTENCES
    fun recallClose() {
        sentences?.close()
    }

    fun scriptOpen(memoryMb: Int): String = scripts?.open(memoryMb) ?: ""
    fun scriptAsk(handle: String, line: String, waitMs: Int): String = scripts?.ask(handle, line, waitMs.toLong()) ?: ScriptLink.CLOSED
    fun scriptClose(handle: String) {
        scripts?.close(handle)
    }
    fun scriptInfo(): String = scripts?.info() ?: "{\"available\": false}"

    companion object {
        const val NO_SENTENCES = "{\"present\": false, \"rung\": \"missing\", \"standin_now\": true, \"why\": \"no sentence model in this process\"}"
    }
}
