package com.astrynome.music

import org.junit.Assert.*
import org.junit.Test
import java.nio.ByteBuffer
import java.nio.ByteOrder

class FeatureTest {
    private fun wave(samples: ShortArray, channels: Int = 1): ByteArray {
        val b = ByteBuffer.allocate(44 + samples.size * 2).order(ByteOrder.LITTLE_ENDIAN)
        b.put("RIFF".toByteArray()).putInt(36 + samples.size * 2).put("WAVEfmt ".toByteArray())
        b.putInt(16).putShort(1).putShort(channels.toShort()).putInt(8000).putInt(8000 * channels * 2)
        b.putShort((channels * 2).toShort()).putShort(16).put("data".toByteArray()).putInt(samples.size * 2)
        samples.forEach { b.putShort(it) }
        return b.array()
    }
    @Test fun measuresKnownSignal() {
        val features = WavAnalyzer.analyze(wave(ShortArray(8000) { if (it % 2 == 0) 16384 else -16384 }))
        assertEquals(1.0, features.seconds, 0.00001)
        assertEquals(0.5, features.rms, 0.00001)
        assertEquals(1.0, features.zeroCrossingRate, 0.00001)
    }
    @Test fun downmixesStereoWithoutArtificialCrossings() {
        val features = WavAnalyzer.analyze(wave(shortArrayOf(1000, -1000, 1000, -1000), 2))
        assertEquals(0.0, features.rms, 0.0)
        assertEquals(0.0, features.zeroCrossingRate, 0.0)
        assertEquals(2.0 / 8000, features.seconds, 0.00001)
    }
    @Test(expected = IllegalArgumentException::class)
    fun rejectsTruncatedWave() { WavAnalyzer.analyze(wave(shortArrayOf(1, 2)).dropLast(1).toByteArray()) }
    @Test(expected = IllegalArgumentException::class)
    fun unsupportedFormatHasExplicitFallback() { WavAnalyzer.analyze("not a supported audio file".toByteArray()) }
    @Test fun canonicalizesYouTubeAndMusicLinks() {
        val expected = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        assertEquals(expected, YouTubeLinks.normalize("https://youtu.be/dQw4w9WgXcQ?t=3"))
        assertEquals(expected, YouTubeLinks.normalize("https://music.youtube.com/watch?v=dQw4w9WgXcQ&list=anything"))
        assertEquals(expected, YouTubeLinks.normalize("https://www.youtube.com/shorts/dQw4w9WgXcQ"))
    }
    @Test fun rejectsSpoofedHostsAndSchemes() {
        listOf("https://youtube.com.evil.test/watch?v=dQw4w9WgXcQ", "javascript:alert(1)",
            "https://evil.test@youtube.com/watch?v=dQw4w9WgXcQ", "http://youtu.be/dQw4w9WgXcQ",
            "https://youtu.be/short", "https://youtube.com:444/watch?v=dQw4w9WgXcQ").forEach {
            assertNull(it, YouTubeLinks.normalize(it))
        }
    }
    @Test fun encodesSearchQueries() {
        assertEquals("https://music.youtube.com/search?q=jazz+%26+soul", YouTubeLinks.search("jazz & soul", true))
    }
    @Test fun recommendationsFollowSelectedMood() {
        val calm = RecommendationEngine.recommend("Calme")
        val energetic = RecommendationEngine.recommend("Énergique")
        assertEquals(3, calm.size)
        assertNotEquals(calm.map { it.title }, energetic.map { it.title })
        assertTrue(energetic.all { it.reason.contains("Énergique") })
    }
}
