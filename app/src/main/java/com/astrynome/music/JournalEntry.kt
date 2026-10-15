package com.astrynome.music

import java.util.UUID

data class JournalEntry(
    val title: String,
    val emotion: String,
    val id: String = UUID.randomUUID().toString(),
    val sourceUri: String? = null
) {
    init {
        require(title.isNotBlank()) { "Le titre est obligatoire" }
        require(emotion in emotions) { "Émotion inconnue" }
    }
    companion object {
        val emotions = listOf("Calme", "Joyeux", "Mélancolique", "Énergique")
    }
}

data class AudioTrack(val title: String, val uri: String)
data class Recommendation(val title: String, val query: String, val reason: String)

object RecommendationEngine {
    fun recommend(emotion: String): List<Recommendation> {
        val genres = when (emotion) {
            "Énergique" -> listOf("Afrobeat", "Électro", "Funk")
            "Joyeux" -> listOf("Afropop", "Disco", "Soul")
            "Mélancolique" -> listOf("Piano", "Jazz doux", "Acoustique")
            else -> listOf("Ambient", "Lo-fi", "Jazz")
        }
        return genres.map { Recommendation(it, "$it musique", "Sélection locale pour une humeur : $emotion") }
    }
}

object YouTubeLinks {
    fun normalize(input: String): String? = runCatching {
        val uri = java.net.URI(input.trim())
        if (uri.scheme != "https" || uri.rawUserInfo != null || uri.port != -1) return null
        val host = uri.host?.lowercase() ?: return null
        if (host !in setOf("youtube.com", "www.youtube.com", "music.youtube.com", "m.youtube.com", "youtu.be")) return null
        val parameters = uri.rawQuery.orEmpty().split('&').mapNotNull {
            val parts = it.split('=', limit = 2)
            if (parts.size == 2) parts[0] to parts[1] else null
        }.toMap()
        val id = if (host == "youtu.be") uri.path.trim('/').takeIf { '/' !in it }
        else if (uri.path == "/watch") parameters["v"]
        else if (uri.path.startsWith("/shorts/")) uri.path.removePrefix("/shorts/").trim('/')
        else null
        if (id == null || !id.matches(Regex("[A-Za-z0-9_-]{11}"))) return null
        "https://www.youtube.com/watch?v=$id"
    }.getOrNull()

    fun search(query: String, music: Boolean = false): String {
        val encoded = java.net.URLEncoder.encode(query, "UTF-8")
        return if (music) "https://music.youtube.com/search?q=$encoded"
        else "https://www.youtube.com/results?search_query=$encoded"
    }
}
