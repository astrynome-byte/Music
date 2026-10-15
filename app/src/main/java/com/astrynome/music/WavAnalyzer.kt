package com.astrynome.music

import java.nio.ByteBuffer
import java.nio.ByteOrder
import kotlin.math.sqrt

/** Real signal measurements for uncompressed RIFF/WAVE PCM16, up to 12 MiB. */
data class AudioFeatures(val seconds: Double, val rms: Double, val zeroCrossingRate: Double) {
    val description: String get() = "Durée : %.1f s · Énergie RMS : %.3f · Passages par zéro : %.3f".format(seconds, rms, zeroCrossingRate)
}

object WavAnalyzer {
    const val MAX_BYTES = 12 * 1024 * 1024
    fun analyze(bytes: ByteArray): AudioFeatures {
        require(bytes.size <= MAX_BYTES) { "Analyse limitée aux WAV de 12 Mio maximum" }
        require(bytes.size >= 12 && String(bytes, 0, 4, Charsets.US_ASCII) == "RIFF" &&
            String(bytes, 8, 4, Charsets.US_ASCII) == "WAVE") { "Analyse disponible pour les fichiers WAV PCM 16 bits uniquement" }
        val buffer = ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN)
        var offset = 12
        var channels = 0
        var rate = 0
        var dataOffset = -1
        var dataLength = 0
        while (offset <= bytes.size - 8) {
            val id = String(bytes, offset, 4, Charsets.US_ASCII)
            val length = buffer.getInt(offset + 4).toLong() and 0xffffffffL
            require(length <= bytes.size - offset - 8) { "Fichier WAV tronqué" }
            if (id == "fmt ") {
                require(length >= 16 && buffer.getShort(offset + 8).toInt() == 1 &&
                    buffer.getShort(offset + 22).toInt() == 16) { "Format requis : WAV PCM 16 bits" }
                channels = buffer.getShort(offset + 10).toInt()
                rate = buffer.getInt(offset + 12)
                require(channels in 1..8 && rate in 8000..192000) { "Format audio invalide" }
                require(buffer.getShort(offset + 20).toInt() == channels * 2) { "Alignement WAV invalide" }
            }
            if (id == "data") { dataOffset = offset + 8; dataLength = length.toInt() }
            offset = (offset + 8L + length + length % 2).coerceAtMost(bytes.size.toLong()).toInt()
        }
        require(channels > 0 && rate > 0 && dataOffset >= 0 && dataLength >= channels * 2 && dataLength % (channels * 2) == 0) { "Données audio WAV manquantes ou incomplètes" }
        val frames = dataLength / (channels * 2)
        var squares = 0.0
        var crossings = 0
        var previous = 0.0
        // Mix channels before measuring; never count boundaries between channels.
        repeat(frames) { frame ->
            var sample = 0.0
            repeat(channels) { channel ->
                sample += buffer.getShort(dataOffset + (frame * channels + channel) * 2) / 32768.0
            }
            sample /= channels
            squares += sample * sample
            if (frame > 0 && (sample >= 0) != (previous >= 0)) crossings++
            previous = sample
        }
        return AudioFeatures(frames.toDouble() / rate, sqrt(squares / frames), crossings.toDouble() / maxOf(1, frames - 1))
    }
}
