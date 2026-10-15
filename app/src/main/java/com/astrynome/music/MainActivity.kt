package com.astrynome.music

import android.content.ActivityNotFoundException
import android.content.Intent
import androidx.core.net.toUri
import android.os.Bundle
import android.provider.OpenableColumns
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.ByteArrayOutputStream

class MainActivity : ComponentActivity() {
    private val audioPlayer = AudioPlayer()
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        val store = MusicStore(this)
        setContent { MaterialTheme(colorScheme = darkColorScheme()) { MusicApp(store, audioPlayer) } }
    }
    override fun onStop() { audioPlayer.pause(); super.onStop() }
    override fun onDestroy() { audioPlayer.release(); super.onDestroy() }
}

@Composable
private fun MusicApp(store: MusicStore, player: AudioPlayer) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var entries by remember { mutableStateOf(store.entries()) }
    var tracks by remember { mutableStateOf(store.tracks()) }
    var tab by rememberSaveable { mutableStateOf("Journal") }
    var message by remember { mutableStateOf(if (store.recoveredData) "Certaines données étaient illisibles ; une copie de récupération a été conservée." else "") }
    var analyzing by remember { mutableStateOf(false) }
    var analysis by rememberSaveable { mutableStateOf("") }
    val demo = remember { AudioTrack("Signal de démonstration · 2 secondes", "android.resource://${context.packageName}/${R.raw.demo}") }
    fun addEntry(entry: JournalEntry) { entries = listOf(entry) + entries; store.saveEntries(entries); message = "Ajouté au journal" }
    fun open(url: String) {
        try { context.startActivity(Intent(Intent.ACTION_VIEW, url.toUri())) }
        catch (_: ActivityNotFoundException) { message = "Aucune application ne peut ouvrir ce lien. Installez un navigateur ou YouTube." }
        catch (_: SecurityException) { message = "L'ouverture de ce lien a été refusée par Android." }
    }
    val importer = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri != null) {
            try {
                try { context.contentResolver.takePersistableUriPermission(uri, Intent.FLAG_GRANT_READ_URI_PERMISSION) }
                catch (_: SecurityException) { message = "Accès temporaire : ce fournisseur peut nécessiter un nouvel import au prochain démarrage." }
                val title = context.contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use {
                    if (it.moveToFirst()) it.getString(0) else null
                } ?: "Morceau importé"
                val track = AudioTrack(title.ifBlank { "Morceau importé" }, uri.toString())
                tracks = listOf(track) + tracks.filterNot { it.uri == track.uri }
                store.saveTracks(tracks)
            } catch (_: Exception) { message = "Import impossible : le fichier n'est pas accessible." }
        }
    }
    Scaffold(
        bottomBar = {
            NavigationBar {
                listOf("Journal", "Audio", "Découvrir", "YouTube").forEach { name ->
                    NavigationBarItem(selected = tab == name, onClick = { tab = name },
                        icon = { Text(when (name) { "Journal" -> "♫"; "Audio" -> "▶"; "Découvrir" -> "✦"; else -> "↗" }) },
                        label = { Text(name) }, modifier = Modifier.testTag("nav_$name"))
                }
            }
        }
    ) { padding ->
        Column(Modifier.fillMaxSize().padding(padding).padding(horizontal = 20.dp)) {
            Text("Music", style = MaterialTheme.typography.headlineLarge, modifier = Modifier.padding(top = 12.dp))
            if (message.isNotEmpty()) {
                Text(message, modifier = Modifier.testTag("status_message"), color = MaterialTheme.colorScheme.primary)
                TextButton(onClick = { message = "" }) { Text("Fermer le message") }
            }
            when (tab) {
                "Journal" -> JournalScreen(entries, ::addEntry, { id -> entries = entries.filterNot { it.id == id }; store.saveEntries(entries) }, ::open)
                "Audio" -> AudioScreen(listOf(demo) + tracks, player.status, analyzing, analysis,
                    onImport = { importer.launch(arrayOf("audio/*")) },
                    onPlay = { player.play(context, it) }, onStop = { player.pause() },
                    onJournal = { addEntry(JournalEntry(it.title, "Calme", sourceUri = it.uri)) },
                    onAnalyze = { track ->
                        analyzing = true
                        analysis = ""
                        scope.launch {
                            analysis = withContext(Dispatchers.IO) {
                                runCatching {
                                    val bytes = context.contentResolver.openInputStream(track.uri.toUri())?.use { input ->
                                        val output = ByteArrayOutputStream()
                                        val buffer = ByteArray(8192)
                                        var total = 0
                                        while (true) {
                                            val count = input.read(buffer)
                                            if (count < 0) break
                                            total += count
                                            require(total <= WavAnalyzer.MAX_BYTES) { "Analyse limitée aux WAV de 12 Mio maximum" }
                                            output.write(buffer, 0, count)
                                        }
                                        output.toByteArray()
                                    } ?: error("Fichier inaccessible")
                                    WavAnalyzer.analyze(bytes).description
                                }.getOrElse { it.message ?: "Analyse impossible ; la lecture reste disponible." }
                            }
                            analyzing = false
                        }
                    })
                "Découvrir" -> DiscoverScreen(entries, ::open)
                "YouTube" -> YouTubeScreen(::open, ::addEntry)
            }
        }
    }
}

@Composable
private fun JournalScreen(entries: List<JournalEntry>, add: (JournalEntry) -> Unit, delete: (String) -> Unit, open: (String) -> Unit) {
    var title by rememberSaveable { mutableStateOf("") }
    var emotion by rememberSaveable { mutableStateOf("Calme") }
    LazyColumn(verticalArrangement = Arrangement.spacedBy(12.dp), modifier = Modifier.testTag("screen_Journal")) {
        item { Text("Mon journal musical", style = MaterialTheme.typography.titleLarge) }
        item { OutlinedTextField(title, { title = it }, label = { Text("Titre du morceau") }, modifier = Modifier.fillMaxWidth().testTag("journal_title"), singleLine = true) }
        item { EmotionPicker(emotion) { emotion = it } }
        item { Button(enabled = title.isNotBlank(), modifier = Modifier.testTag("journal_add"), onClick = { add(JournalEntry(title.trim(), emotion)); title = "" }) { Text("Ajouter au journal") } }
        if (entries.isEmpty()) item { Text("Votre journal est vide. Ajoutez votre premier morceau.") }
        items(entries, key = { it.id }) { entry ->
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(16.dp)) {
                    Text(entry.title, style = MaterialTheme.typography.titleMedium)
                    Text(entry.emotion)
                    entry.sourceUri?.let { source -> if (YouTubeLinks.normalize(source) != null) {
                        TextButton(onClick = { open(source) }) { Text("Ouvrir sur YouTube") }
                    } }
                    TextButton(onClick = { delete(entry.id) }) { Text("Supprimer") }
                }
            }
        }
        item { Spacer(Modifier.height(16.dp)) }
    }
}

@Composable
private fun EmotionPicker(selected: String, choose: (String) -> Unit) {
    Column {
        Text("Comment vous sentez-vous ?")
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            JournalEntry.emotions.take(2).forEach { emotion -> FilterChip(selected == emotion, { choose(emotion) }, label = { Text(emotion) }) }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            JournalEntry.emotions.drop(2).forEach { emotion -> FilterChip(selected == emotion, { choose(emotion) }, label = { Text(emotion) }) }
        }
    }
}

@Composable
private fun AudioScreen(tracks: List<AudioTrack>, status: String, analyzing: Boolean, analysis: String,
    onImport: () -> Unit, onPlay: (AudioTrack) -> Unit, onStop: () -> Unit, onJournal: (AudioTrack) -> Unit, onAnalyze: (AudioTrack) -> Unit) {
    LazyColumn(verticalArrangement = Arrangement.spacedBy(12.dp), modifier = Modifier.testTag("screen_Audio")) {
        item { Text("Bibliothèque audio", style = MaterialTheme.typography.titleLarge) }
        item { Text("Import local via Android. Lecture selon les formats pris en charge par l'appareil. Analyse du signal WAV PCM 16 bits ; aucune détection d'émotion automatique.") }
        item { Button(onClick = onImport) { Text("Importer un fichier audio") } }
        item { Text(status); TextButton(onClick = onStop) { Text("Arrêter la lecture") } }
        if (analyzing) item { Text("Analyse en cours…") }
        if (analysis.isNotBlank()) item { Text(analysis, modifier = Modifier.testTag("audio_analysis")) }
        items(tracks, key = { it.uri }) { track ->
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(16.dp)) {
                    Text(track.title, style = MaterialTheme.typography.titleMedium)
                    Row {
                        TextButton(onClick = { onPlay(track) }) { Text("Lire") }
                        TextButton(enabled = !analyzing, onClick = { onAnalyze(track) }) { Text("Analyser") }
                    }
                    TextButton(onClick = { onJournal(track) }) { Text("Ajouter au journal · Calme") }
                }
            }
        }
        item { Spacer(Modifier.height(16.dp)) }
    }
}

@Composable
private fun DiscoverScreen(entries: List<JournalEntry>, open: (String) -> Unit) {
    var emotion by rememberSaveable { mutableStateOf(entries.firstOrNull()?.emotion ?: "Calme") }
    LazyColumn(verticalArrangement = Arrangement.spacedBy(12.dp), modifier = Modifier.testTag("screen_Découvrir")) {
        item { Text("Recommandations", style = MaterialTheme.typography.titleLarge) }
        item { Text("Suggestions locales par humeur. Ce sont des pistes d'écoute, pas des résultats d'une API ni un diagnostic émotionnel.") }
        item { Text("Profil du journal : ${entries.size} morceau(x)") }
        if (entries.isNotEmpty()) item { Text(JournalEntry.emotions.joinToString(" · ") { e -> "$e : ${entries.count { it.emotion == e }}" }) }
        item { EmotionPicker(emotion) { emotion = it } }
        items(RecommendationEngine.recommend(emotion)) { item ->
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(16.dp)) {
                    Text(item.title, style = MaterialTheme.typography.titleMedium)
                    Text(item.reason)
                    TextButton(onClick = { open(YouTubeLinks.search(item.query, music = true)) }) { Text("Chercher sur YouTube Music") }
                }
            }
        }
    }
}

@Composable
private fun YouTubeScreen(open: (String) -> Unit, add: (JournalEntry) -> Unit) {
    var query by rememberSaveable { mutableStateOf("") }
    var link by rememberSaveable { mutableStateOf("") }
    var title by rememberSaveable { mutableStateOf("") }
    var emotion by rememberSaveable { mutableStateOf("Calme") }
    val normalized = YouTubeLinks.normalize(link)
    LazyColumn(verticalArrangement = Arrangement.spacedBy(12.dp), modifier = Modifier.testTag("screen_YouTube")) {
        item { Text("YouTube et YouTube Music", style = MaterialTheme.typography.titleLarge) }
        item { Text("Mode liens externes : recherche et ouverture dans l'application ou le navigateur. Connexion Google, playlists privées et lecture intégrée ne sont pas activées. Aucun téléchargement YouTube.") }
        item { OutlinedTextField(query, { query = it }, label = { Text("Rechercher un artiste ou un morceau") }, modifier = Modifier.fillMaxWidth()) }
        item {
            Row {
                TextButton(enabled = query.isNotBlank(), onClick = { open(YouTubeLinks.search(query.trim())) }) { Text("YouTube") }
                TextButton(enabled = query.isNotBlank(), onClick = { open(YouTubeLinks.search(query.trim(), true)) }) { Text("YouTube Music") }
            }
        }
        item { OutlinedTextField(link, { link = it }, label = { Text("Lien d'une vidéo YouTube") }, isError = link.isNotBlank() && normalized == null, modifier = Modifier.fillMaxWidth().testTag("youtube_link")) }
        if (link.isNotBlank() && normalized == null) item { Text("Utilisez un lien HTTPS youtube.com/watch?v=…, music.youtube.com/watch?v=… ou youtu.be/… valide.") }
        item { OutlinedTextField(title, { title = it }, label = { Text("Titre pour le journal") }, modifier = Modifier.fillMaxWidth()) }
        item { EmotionPicker(emotion) { emotion = it } }
        item { Button(enabled = normalized != null, onClick = { normalized?.let { open(it) } }) { Text("Ouvrir la vidéo") } }
        item { Button(enabled = normalized != null && title.isNotBlank(), onClick = { normalized?.let { add(JournalEntry(title.trim(), emotion, sourceUri = it)); title = ""; link = "" } }) { Text("Enregistrer dans le journal") } }
        item { Spacer(Modifier.height(16.dp)) }
    }
}
