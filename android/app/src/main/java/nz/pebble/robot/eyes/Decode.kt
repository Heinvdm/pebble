package nz.pebble.robot.eyes

import kotlin.math.exp
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sqrt

data class Det(val x: Float, val y: Float, val w: Float, val h: Float, val score: Float, val cls: Int = 0, val marks: FloatArray? = null)

object Decode {
    val YUNET_STRIDES = intArrayOf(8, 16, 32)
    val NANODET_STRIDES = intArrayOf(8, 16, 32)
    const val NANODET_SIZE = 416
    const val NANODET_BINS = 8
    const val NANODET_CLASSES = 80
    const val PERSON = 0

    fun iou(a: Det, b: Det): Float {
        val x0 = max(a.x, b.x)
        val y0 = max(a.y, b.y)
        val x1 = min(a.x + a.w, b.x + b.w)
        val y1 = min(a.y + a.h, b.y + b.h)
        val inner = max(0f, x1 - x0) * max(0f, y1 - y0)
        val union = a.w * a.h + b.w * b.h - inner
        return if (union > 0f) inner / union else 0f
    }

    fun nms(found: List<Det>, overlap: Float, perClass: Boolean = false, limit: Int = Int.MAX_VALUE): List<Det> {
        val order = found.sortedByDescending { it.score }
        val kept = ArrayList<Det>()
        for (candidate in order) {
            if (kept.size >= limit) break
            if (kept.none { (!perClass || it.cls == candidate.cls) && iou(it, candidate) > overlap }) kept += candidate
        }
        return kept
    }

    fun yunet(cls: List<FloatArray>, obj: List<FloatArray>, bbox: List<FloatArray>, padW: Int, padH: Int, threshold: Float, overlap: Float = 0.3f, topK: Int = 50, kps: List<FloatArray>? = null): List<Det> {
        val found = ArrayList<Det>()
        for ((i, stride) in YUNET_STRIDES.withIndex()) {
            val cols = padW / stride
            val rows = padH / stride
            val c = cls[i]
            val o = obj[i]
            val b = bbox[i]
            val k = kps?.getOrNull(i)
            for (r in 0 until rows) {
                for (col in 0 until cols) {
                    val idx = r * cols + col
                    if (idx >= c.size) break
                    val score = sqrt(c[idx].coerceIn(0f, 1f) * o[idx].coerceIn(0f, 1f))
                    if (score < threshold) continue
                    val cx = (col + b[idx * 4]) * stride
                    val cy = (r + b[idx * 4 + 1]) * stride
                    val w = exp(b[idx * 4 + 2]) * stride
                    val h = exp(b[idx * 4 + 3]) * stride
                    val marks = if (k != null && k.size >= (idx + 1) * 10) FloatArray(10) { j -> ((if (j % 2 == 0) col else r) + k[idx * 10 + j]) * stride } else null
                    found += Det(cx - w / 2f, cy - h / 2f, w, h, score, marks = marks)
                }
            }
        }
        return nms(found, overlap, limit = topK)
    }

    fun nanodet(scores: Map<Int, FloatArray>, boxes: Map<Int, FloatArray>, rw: Int, rh: Int, personScore: Float, thingScore: Float, overlap: Float = 0.5f): List<Det> {
        val floor = min(personScore, thingScore)
        val found = ArrayList<Det>()
        val probs = FloatArray(NANODET_BINS)
        for (stride in NANODET_STRIDES) {
            val side = NANODET_SIZE / stride
            val n = side * side
            val s = scores[n] ?: continue
            val b = boxes[n] ?: continue
            for (i in 0 until n) {
                var best = 0
                var top = s[i * NANODET_CLASSES]
                for (k in 1 until NANODET_CLASSES) {
                    val v = s[i * NANODET_CLASSES + k]
                    if (v > top) {
                        top = v
                        best = k
                    }
                }
                if (top <= floor) continue
                if (top < (if (best == PERSON) personScore else thingScore)) continue
                val cx = (i % side) * stride + 0.5f * (stride - 1)
                val cy = (i / side) * stride + 0.5f * (stride - 1)
                val d = FloatArray(4)
                for (side4 in 0 until 4) {
                    val base = i * 4 * NANODET_BINS + side4 * NANODET_BINS
                    var peak = Float.NEGATIVE_INFINITY
                    for (k in 0 until NANODET_BINS) peak = max(peak, b[base + k])
                    var sum = 0f
                    for (k in 0 until NANODET_BINS) {
                        probs[k] = exp(b[base + k] - peak)
                        sum += probs[k]
                    }
                    var expected = 0f
                    for (k in 0 until NANODET_BINS) expected += probs[k] / sum * k
                    d[side4] = expected * stride
                }
                val x1 = (cx - d[0]).coerceIn(0f, rw.toFloat())
                val y1 = (cy - d[1]).coerceIn(0f, rh.toFloat())
                val x2 = (cx + d[2]).coerceIn(0f, rw.toFloat())
                val y2 = (cy + d[3]).coerceIn(0f, rh.toFloat())
                found += Det(x1, y1, x2 - x1, y2 - y1, top, best)
            }
        }
        return nms(found, overlap, perClass = true)
    }

    fun yoloe(out: FloatArray, channels: Int, anchors: Int, classes: Int, score: Float, overlap: Float = 0.6f): List<Det> {
        val found = ArrayList<Det>()
        val count = min(classes, channels - 4)
        for (n in 0 until anchors) {
            var best = 0
            var top = out[4 * anchors + n]
            for (k in 1 until count) {
                val v = out[(4 + k) * anchors + n]
                if (v > top) {
                    top = v
                    best = k
                }
            }
            if (top <= score) continue
            val cx = out[n]
            val cy = out[anchors + n]
            val w = out[2 * anchors + n]
            val h = out[3 * anchors + n]
            found += Det(cx - w / 2f, cy - h / 2f, w, h, top, best)
        }
        return nms(found, overlap)
    }
}
