"""The launcher's text in the six languages the MH3U games use.

Each entry is keyed by the English text exactly as launcher.py passes it to T(). Words in
{braces} are filled in at run time and must stay as they are in every language. A missing
translation falls back to English, and `python launcher.py --selftest` lists any gaps.

Translations other than English are machine-made and may read oddly; the launcher says so
on its Home tab. Corrections are welcome: change the text here and keep the {braces}.
"""

# (code, name shown in the language picker), English first
LANGUAGES = (
    ("en", "English"),
    ("fr", "Français"),
    ("de", "Deutsch"),
    ("it", "Italiano"),
    ("es", "Español"),
    ("ja", "日本語"),
)

STRINGS = {
    # ---- window, Home tab, language picker ----------------------------------------
    "version {v}": {
        "fr": "version {v}",
        "de": "Version {v}",
        "it": "versione {v}",
        "es": "versión {v}",
        "ja": "バージョン {v}",
    },
    "Language:": {
        "fr": "Langue :",
        "de": "Sprache:",
        "it": "Lingua:",
        "es": "Idioma:",
        "ja": "言語：",
    },
    "Translations other than English may be inaccurate.": {
        "fr": "Les traductions autres que l'anglais peuvent être inexactes.",
        "de": "Übersetzungen außer Englisch können ungenau sein.",
        "it": "Le traduzioni diverse dall'inglese potrebbero essere imprecise.",
        "es": "Las traducciones distintas del inglés pueden ser inexactas.",
        "ja": "英語以外の翻訳は不正確な場合があります。",
    },
    "Stop the server before changing the language.": {
        "fr": "Arrêtez le serveur avant de changer de langue.",
        "de": "Stoppe den Server, bevor du die Sprache änderst.",
        "it": "Arresta il server prima di cambiare lingua.",
        "es": "Detén el servidor antes de cambiar el idioma.",
        "ja": "言語を変更する前にサーバーを停止してください。",
    },
    "checking for updates…": {
        "fr": "recherche de mises à jour…",
        "de": "Suche nach Updates…",
        "it": "controllo aggiornamenti…",
        "es": "buscando actualizaciones…",
        "ja": "アップデートを確認中…",
    },
    "Update now": {
        "fr": "Mettre à jour",
        "de": "Jetzt aktualisieren",
        "it": "Aggiorna ora",
        "es": "Actualizar ahora",
        "ja": "今すぐアップデート",
    },
    "Home": {
        "fr": "Accueil",
        "de": "Start",
        "it": "Home",
        "es": "Inicio",
        "ja": "ホーム",
    },
    "What do you want to do?": {
        "fr": "Que voulez-vous faire ?",
        "de": "Was möchtest du tun?",
        "it": "Cosa vuoi fare?",
        "es": "¿Qué quieres hacer?",
        "ja": "何をしますか？",
    },
    "JOIN A GAME": {
        "fr": "REJOINDRE UNE PARTIE",
        "de": "SPIEL BEITRETEN",
        "it": "UNISCITI A UNA PARTITA",
        "es": "UNIRSE A UNA PARTIDA",
        "ja": "ゲームに参加",
    },
    "HOST A SERVER": {
        "fr": "HÉBERGER UN SERVEUR",
        "de": "SERVER HOSTEN",
        "it": "OSPITA UN SERVER",
        "es": "ALOJAR UN SERVIDOR",
        "ja": "サーバーを立てる",
    },
    "JOIN = play on the official server or a friend's.\nHOST = run the server for your friends.": {
        "fr": "REJOINDRE = jouer sur le serveur officiel ou celui d'un ami.\n"
              "HÉBERGER = faire tourner le serveur pour vos amis.",
        "de": "BEITRETEN = auf dem offiziellen Server oder dem eines Freundes spielen.\n"
              "HOSTEN = den Server für deine Freunde betreiben.",
        "it": "UNISCITI = gioca sul server ufficiale o su quello di un amico.\n"
              "OSPITA = avvia il server per i tuoi amici.",
        "es": "UNIRSE = jugar en el servidor oficial o en el de un amigo.\n"
              "ALOJAR = ejecutar el servidor para tus amigos.",
        "ja": "「ゲームに参加」：公式サーバーかフレンドのサーバーで遊びます。\n"
              "「サーバーを立てる」：フレンドのためにサーバーを動かします。",
    },

    # ---- Join tab -------------------------------------------------------------------
    "Join": {
        "fr": "Rejoindre",
        "de": "Beitreten",
        "it": "Unisciti",
        "es": "Unirse",
        "ja": "参加",
    },
    "Where do you want to play?": {
        "fr": "Où voulez-vous jouer ?",
        "de": "Wo möchtest du spielen?",
        "it": "Dove vuoi giocare?",
        "es": "¿Dónde quieres jugar?",
        "ja": "どこで遊びますか？",
    },
    "Official server: checking…": {
        "fr": "Serveur officiel : vérification…",
        "de": "Offizieller Server: wird geprüft…",
        "it": "Server ufficiale: verifica in corso…",
        "es": "Servidor oficial: comprobando…",
        "ja": "公式サーバー：確認中…",
    },
    "A friend's server, IP:": {
        "fr": "Le serveur d'un ami, IP :",
        "de": "Server eines Freundes, IP:",
        "it": "Server di un amico, IP:",
        "es": "Servidor de un amigo, IP:",
        "ja": "フレンドのサーバー、IP：",
    },
    "Ask the host for their Tailscale (100.x), Radmin (26.x), LAN or public IP.": {
        "fr": "Demandez à l'hôte son IP Tailscale (100.x), Radmin (26.x), LAN ou publique.",
        "de": "Frag den Host nach seiner Tailscale- (100.x), Radmin- (26.x), LAN- oder öffentlichen IP.",
        "it": "Chiedi all'host il suo IP Tailscale (100.x), Radmin (26.x), LAN o pubblico.",
        "es": "Pide al anfitrión su IP de Tailscale (100.x), Radmin (26.x), LAN o pública.",
        "ja": "ホストにTailscale（100.x）、Radmin（26.x）、LAN、またはグローバルIPを聞いてください。",
    },
    "Add the official event quests to my game (your own quests are never changed)": {
        "fr": "Ajouter les quêtes d'événement officielles à mon jeu (vos propres quêtes ne sont jamais modifiées)",
        "de": "Die offiziellen Event-Quests zu meinem Spiel hinzufügen (deine eigenen Quests werden nie verändert)",
        "it": "Aggiungi le missioni evento ufficiali al mio gioco (le tue missioni non vengono mai modificate)",
        "es": "Añadir las misiones de evento oficiales a mi juego (tus propias misiones nunca se modifican)",
        "ja": "公式イベントクエストをゲームに追加する（自分のクエストは変更されません）",
    },
    "Save + Play": {
        "fr": "Enregistrer + Jouer",
        "de": "Speichern + Spielen",
        "it": "Salva + Gioca",
        "es": "Guardar + Jugar",
        "ja": "保存してプレイ",
    },
    "Test connection": {
        "fr": "Tester la connexion",
        "de": "Verbindung testen",
        "it": "Prova connessione",
        "es": "Probar conexión",
        "ja": "接続テスト",
    },
    "[MH3U Online] That server isn't in the list anymore; pick one again.": {
        "fr": "[MH3U Online] Ce serveur n'est plus dans la liste ; choisissez-en un autre.",
        "de": "[MH3U Online] Dieser Server ist nicht mehr in der Liste; wähle erneut einen aus.",
        "it": "[MH3U Online] Quel server non è più nell'elenco; scegline di nuovo uno.",
        "es": "[MH3U Online] Ese servidor ya no está en la lista; elige otro.",
        "ja": "[MH3U Online] そのサーバーはリストにありません。もう一度選んでください。",
    },
    "[MH3U Online] ERROR: couldn't look up {name} ({err}). Check your internet connection.": {
        "fr": "[MH3U Online] ERREUR : impossible de trouver {name} ({err}). Vérifiez votre connexion Internet.",
        "de": "[MH3U Online] FEHLER: {name} konnte nicht aufgelöst werden ({err}). Prüfe deine Internetverbindung.",
        "it": "[MH3U Online] ERRORE: impossibile risolvere {name} ({err}). Controlla la connessione a Internet.",
        "es": "[MH3U Online] ERROR: no se pudo resolver {name} ({err}). Comprueba tu conexión a Internet.",
        "ja": "[MH3U Online] エラー：{name} が見つかりません（{err}）。インターネット接続を確認してください。",
    },
    "your friend's server": {
        "fr": "le serveur de votre ami",
        "de": "der Server deines Freundes",
        "it": "il server del tuo amico",
        "es": "el servidor de tu amigo",
        "ja": "フレンドのサーバー",
    },
    "[Test] Type your friend's IP first.": {
        "fr": "[Test] Saisissez d'abord l'IP de votre ami.",
        "de": "[Test] Gib zuerst die IP deines Freundes ein.",
        "it": "[Test] Inserisci prima l'IP del tuo amico.",
        "es": "[Test] Escribe primero la IP de tu amigo.",
        "ja": "[Test] 先にフレンドのIPを入力してください。",
    },
    "[Test] Asking {name} ({ip}) on UDP {port} ...": {
        "fr": "[Test] Interrogation de {name} ({ip}) sur UDP {port}...",
        "de": "[Test] Frage {name} ({ip}) über UDP {port} ab ...",
        "it": "[Test] Interrogo {name} ({ip}) su UDP {port} ...",
        "es": "[Test] Consultando a {name} ({ip}) por UDP {port} ...",
        "ja": "[Test] {name}（{ip}）にUDP {port} で問い合わせ中...",
    },
    "[Test] OK: the server answered and sees you at {addr}. Your connection to it works.": {
        "fr": "[Test] OK : le serveur a répondu et vous voit à l'adresse {addr}. Votre connexion fonctionne.",
        "de": "[Test] OK: Der Server hat geantwortet und sieht dich unter {addr}. Deine Verbindung funktioniert.",
        "it": "[Test] OK: il server ha risposto e ti vede come {addr}. La connessione funziona.",
        "es": "[Test] OK: el servidor respondió y te ve en {addr}. Tu conexión funciona.",
        "ja": "[Test] OK：サーバーが応答し、あなたを {addr} として認識しました。接続は正常です。",
    },
    "[Test] FAILED ({info}). Either the server is down, or something on your side blocks UDP: "
    "a firewall, a VPN, or a school/work network.": {
        "fr": "[Test] ÉCHEC ({info}). Soit le serveur est hors ligne, soit quelque chose de votre côté "
              "bloque l'UDP : un pare-feu, un VPN ou un réseau d'école/de travail.",
        "de": "[Test] FEHLGESCHLAGEN ({info}). Entweder ist der Server offline, oder etwas auf deiner "
              "Seite blockiert UDP: eine Firewall, ein VPN oder ein Schul-/Firmennetz.",
        "it": "[Test] FALLITO ({info}). O il server è offline, oppure qualcosa dalla tua parte blocca "
              "l'UDP: un firewall, una VPN o una rete scolastica/aziendale.",
        "es": "[Test] FALLÓ ({info}). O el servidor está caído, o algo de tu lado bloquea UDP: "
              "un firewall, una VPN o una red escolar/de trabajo.",
        "ja": "[Test] 失敗（{info}）。サーバーが停止しているか、ファイアウォール、VPN、学校や職場の"
              "ネットワークなど、あなたの側でUDPがブロックされています。",
    },
    "[Test] FAILED ({info}). Check that your friend's server is running, that their router forwards "
    "UDP 1223, 1224 and {port} to their PC, and their firewall allows them.": {
        "fr": "[Test] ÉCHEC ({info}). Vérifiez que le serveur de votre ami est lancé, que son routeur "
              "redirige les ports UDP 1223, 1224 et {port} vers son PC, et que son pare-feu les autorise.",
        "de": "[Test] FEHLGESCHLAGEN ({info}). Prüfe, ob der Server deines Freundes läuft, ob sein Router "
              "UDP 1223, 1224 und {port} an seinen PC weiterleitet und ob seine Firewall sie zulässt.",
        "it": "[Test] FALLITO ({info}). Controlla che il server del tuo amico sia avviato, che il suo "
              "router inoltri le porte UDP 1223, 1224 e {port} al suo PC e che il suo firewall le consenta.",
        "es": "[Test] FALLÓ ({info}). Comprueba que el servidor de tu amigo esté en marcha, que su router "
              "redirija UDP 1223, 1224 y {port} a su PC y que su firewall los permita.",
        "ja": "[Test] 失敗（{info}）。フレンドのサーバーが起動しているか、ルーターがUDP 1223、1224、"
              "{port} をそのPCに転送しているか、ファイアウォールで許可されているかを確認してください。",
    },
    "[Test] Server status: {status}": {
        "fr": "[Test] État du serveur : {status}",
        "de": "[Test] Serverstatus: {status}",
        "it": "[Test] Stato del server: {status}",
        "es": "[Test] Estado del servidor: {status}",
        "ja": "[Test] サーバーの状態：{status}",
    },
    "[Test] Status page didn't answer ({err}).": {
        "fr": "[Test] La page d'état n'a pas répondu ({err}).",
        "de": "[Test] Die Statusseite hat nicht geantwortet ({err}).",
        "it": "[Test] La pagina di stato non ha risposto ({err}).",
        "es": "[Test] La página de estado no respondió ({err}).",
        "ja": "[Test] 状態ページが応答しませんでした（{err}）。",
    },
    "[Events] Skipped the event quests ({err}).": {
        "fr": "[Events] Quêtes d'événement ignorées ({err}).",
        "de": "[Events] Event-Quests übersprungen ({err}).",
        "it": "[Events] Missioni evento saltate ({err}).",
        "es": "[Events] Se omitieron las misiones de evento ({err}).",
        "ja": "[Events] イベントクエストをスキップしました（{err}）。",
    },
    "Official server: not available yet.": {
        "fr": "Serveur officiel : pas encore disponible.",
        "de": "Offizieller Server: noch nicht verfügbar.",
        "it": "Server ufficiale: non ancora disponibile.",
        "es": "Servidor oficial: aún no disponible.",
        "ja": "公式サーバー：まだ利用できません。",
    },
    "Official server: couldn't load the server list (offline?).": {
        "fr": "Serveur officiel : impossible de charger la liste des serveurs (hors ligne ?).",
        "de": "Offizieller Server: Serverliste konnte nicht geladen werden (offline?).",
        "it": "Server ufficiale: impossibile caricare l'elenco dei server (offline?).",
        "es": "Servidor oficial: no se pudo cargar la lista de servidores (¿sin conexión?).",
        "ja": "公式サーバー：サーバーリストを読み込めませんでした（オフライン？）。",
    },
    "checking…": {
        "fr": "vérification…",
        "de": "wird geprüft…",
        "it": "verifica…",
        "es": "comprobando…",
        "ja": "確認中…",
    },
    "Official server: {name}": {
        "fr": "Serveur officiel : {name}",
        "de": "Offizieller Server: {name}",
        "it": "Server ufficiale: {name}",
        "es": "Servidor oficial: {name}",
        "ja": "公式サーバー：{name}",
    },
    "not responding": {
        "fr": "ne répond pas",
        "de": "antwortet nicht",
        "it": "non risponde",
        "es": "no responde",
        "ja": "応答なし",
    },

    # ---- server status line -----------------------------------------------------------
    "status unreadable": {
        "fr": "état illisible",
        "de": "Status unlesbar",
        "it": "stato illeggibile",
        "es": "estado ilegible",
        "ja": "状態を読み取れません",
    },
    "1 hunter": {
        "fr": "1 chasseur",
        "de": "1 Jäger",
        "it": "1 cacciatore",
        "es": "1 cazador",
        "ja": "1人",
    },
    "{n} hunters": {
        "fr": "{n} chasseurs",
        "de": "{n} Jäger",
        "it": "{n} cacciatori",
        "es": "{n} cazadores",
        "ja": "{n}人",
    },
    "1 room": {
        "fr": "1 salle",
        "de": "1 Raum",
        "it": "1 stanza",
        "es": "1 sala",
        "ja": "1部屋",
    },
    "{n} rooms": {
        "fr": "{n} salles",
        "de": "{n} Räume",
        "it": "{n} stanze",
        "es": "{n} salas",
        "ja": "{n}部屋",
    },
    "{hunters} online · {rooms}": {
        "fr": "{hunters} en ligne · {rooms}",
        "de": "{hunters} online · {rooms}",
        "it": "{hunters} online · {rooms}",
        "es": "{hunters} en línea · {rooms}",
        "ja": "オンライン {hunters}・{rooms}",
    },

    # ---- event quests -------------------------------------------------------------------
    "[Events] Couldn't get the event quest list ({err}); using the saved copy.": {
        "fr": "[Events] Impossible d'obtenir la liste des quêtes d'événement ({err}) ; utilisation de la copie enregistrée.",
        "de": "[Events] Event-Quest-Liste nicht abrufbar ({err}); die gespeicherte Kopie wird verwendet.",
        "it": "[Events] Impossibile ottenere l'elenco delle missioni evento ({err}); uso la copia salvata.",
        "es": "[Events] No se pudo obtener la lista de misiones de evento ({err}); se usa la copia guardada.",
        "ja": "[Events] イベントクエストのリストを取得できません（{err}）。保存済みのコピーを使います。",
    },
    "[Events] Couldn't download {file} ({err}).": {
        "fr": "[Events] Impossible de télécharger {file} ({err}).",
        "de": "[Events] {file} konnte nicht heruntergeladen werden ({err}).",
        "it": "[Events] Impossibile scaricare {file} ({err}).",
        "es": "[Events] No se pudo descargar {file} ({err}).",
        "ja": "[Events] {file} をダウンロードできません（{err}）。",
    },
    "[Events] Skipped {err}.": {
        "fr": "[Events] Ignoré : {err}.",
        "de": "[Events] Übersprungen: {err}.",
        "it": "[Events] Saltato: {err}.",
        "es": "[Events] Omitido: {err}.",
        "ja": "[Events] スキップ：{err}。",
    },
    "{name}: checksum doesn't match the list": {
        "fr": "{name} : la somme de contrôle ne correspond pas à la liste",
        "de": "{name}: Prüfsumme stimmt nicht mit der Liste überein",
        "it": "{name}: il checksum non corrisponde all'elenco",
        "es": "{name}: la suma de verificación no coincide con la lista",
        "ja": "{name}：チェックサムがリストと一致しません",
    },
    "{name}: not a quest file": {
        "fr": "{name} : n'est pas un fichier de quête",
        "de": "{name}: keine Quest-Datei",
        "it": "{name}: non è un file missione",
        "es": "{name}: no es un archivo de misión",
        "ja": "{name}：クエストファイルではありません",
    },
    "{name}: quest number {no} is outside {range}": {
        "fr": "{name} : le numéro de quête {no} est hors de {range}",
        "de": "{name}: Questnummer {no} liegt außerhalb von {range}",
        "it": "{name}: il numero di missione {no} è fuori da {range}",
        "es": "{name}: el número de misión {no} está fuera de {range}",
        "ja": "{name}：クエスト番号 {no} が範囲外です（{range}）",
    },
    "{name}: too big for a quest slot": {
        "fr": "{name} : trop gros pour un emplacement de quête",
        "de": "{name}: zu groß für einen Quest-Platz",
        "it": "{name}: troppo grande per uno slot missione",
        "es": "{name}: demasiado grande para un espacio de misión",
        "ja": "{name}：クエスト枠に入りきりません",
    },
    "[Events] Cemu is open; close it to update the event quests.": {
        "fr": "[Events] Cemu est ouvert ; fermez-le pour mettre à jour les quêtes d'événement.",
        "de": "[Events] Cemu ist geöffnet; schließe es, um die Event-Quests zu aktualisieren.",
        "it": "[Events] Cemu è aperto; chiudilo per aggiornare le missioni evento.",
        "es": "[Events] Cemu está abierto; ciérralo para actualizar las misiones de evento.",
        "ja": "[Events] Cemuが開いています。イベントクエストを更新するには閉じてください。",
    },
    "[Events] Couldn't update the event quests in {key} ({err}).": {
        "fr": "[Events] Impossible de mettre à jour les quêtes d'événement dans {key} ({err}).",
        "de": "[Events] Event-Quests in {key} konnten nicht aktualisiert werden ({err}).",
        "it": "[Events] Impossibile aggiornare le missioni evento in {key} ({err}).",
        "es": "[Events] No se pudieron actualizar las misiones de evento en {key} ({err}).",
        "ja": "[Events] {key} のイベントクエストを更新できません（{err}）。",
    },
    "[Events] Note: {note}.": {
        "fr": "[Events] Remarque : {note}.",
        "de": "[Events] Hinweis: {note}.",
        "it": "[Events] Nota: {note}.",
        "es": "[Events] Nota: {note}.",
        "ja": "[Events] 注意：{note}。",
    },
    "{name} looks damaged; left alone": {
        "fr": "{name} semble endommagé ; laissé tel quel",
        "de": "{name} scheint beschädigt; unverändert gelassen",
        "it": "{name} sembra danneggiato; lasciato invariato",
        "es": "{name} parece dañado; se deja como está",
        "ja": "{name} が壊れているようです。変更しません",
    },
    "quest {no} is already in your packs (not added by the launcher); left alone": {
        "fr": "la quête {no} est déjà dans vos packs (pas ajoutée par le lanceur) ; laissée telle quelle",
        "de": "Quest {no} ist bereits in deinen Paketen (nicht vom Launcher hinzugefügt); unverändert gelassen",
        "it": "la missione {no} è già nei tuoi pacchetti (non aggiunta dal launcher); lasciata invariata",
        "es": "la misión {no} ya está en tus paquetes (no la añadió el lanzador); se deja como está",
        "ja": "クエスト {no} はすでにパックにあります（ランチャーが追加したものではありません）。変更しません",
    },
    "no free event quest slot for quest {no}": {
        "fr": "aucun emplacement de quête d'événement libre pour la quête {no}",
        "de": "kein freier Event-Quest-Platz für Quest {no}",
        "it": "nessuno slot missione evento libero per la missione {no}",
        "es": "no hay espacio libre de misión de evento para la misión {no}",
        "ja": "クエスト {no} を入れるイベントクエストの空き枠がありません",
    },
    "[Events] Event quests in save {save}: {added} added, {updated} updated, {removed} removed "
    "({n} installed).": {
        "fr": "[Events] Quêtes d'événement dans la sauvegarde {save} : {added} ajoutée(s), "
              "{updated} mise(s) à jour, {removed} retirée(s) ({n} installée(s)).",
        "de": "[Events] Event-Quests im Spielstand {save}: {added} hinzugefügt, {updated} aktualisiert, "
              "{removed} entfernt ({n} installiert).",
        "it": "[Events] Missioni evento nel salvataggio {save}: {added} aggiunte, {updated} aggiornate, "
              "{removed} rimosse ({n} installate).",
        "es": "[Events] Misiones de evento en la partida {save}: {added} añadidas, {updated} actualizadas, "
              "{removed} eliminadas ({n} instaladas).",
        "ja": "[Events] セーブ {save} のイベントクエスト：追加 {added}、更新 {updated}、削除 {removed}"
              "（インストール済み {n}）。",
    },

    # ---- starting the game ----------------------------------------------------------------
    "[MH3U Online] No MH3U game found in this bundle yet.\n"
    "  Cemu will still open, but its game list stays empty until you add\n"
    "  YOUR own legal MH3U dump. Two ways:\n"
    "    1) copy your dump's code/content/meta folders into:\n"
    "         {gamedir}\n"
    "    2) or in Cemu: Options > General Settings > Game Paths > add its folder": {
        "fr": "[MH3U Online] Aucun jeu MH3U trouvé dans ce pack pour l'instant.\n"
              "  Cemu s'ouvrira quand même, mais sa liste de jeux restera vide tant que vous\n"
              "  n'aurez pas ajouté VOTRE propre copie légale de MH3U. Deux façons :\n"
              "    1) copiez les dossiers code/content/meta de votre copie dans :\n"
              "         {gamedir}\n"
              "    2) ou dans Cemu : Options > General Settings > Game Paths > ajoutez son dossier",
        "de": "[MH3U Online] In diesem Paket wurde noch kein MH3U-Spiel gefunden.\n"
              "  Cemu öffnet sich trotzdem, aber die Spieleliste bleibt leer, bis du\n"
              "  DEINEN eigenen legalen MH3U-Dump hinzufügst. Zwei Wege:\n"
              "    1) kopiere die Ordner code/content/meta deines Dumps nach:\n"
              "         {gamedir}\n"
              "    2) oder in Cemu: Options > General Settings > Game Paths > seinen Ordner hinzufügen",
        "it": "[MH3U Online] Nessun gioco MH3U trovato in questo pacchetto.\n"
              "  Cemu si aprirà comunque, ma l'elenco dei giochi resterà vuoto finché non\n"
              "  aggiungi il TUO dump legale di MH3U. Due modi:\n"
              "    1) copia le cartelle code/content/meta del tuo dump in:\n"
              "         {gamedir}\n"
              "    2) oppure in Cemu: Options > General Settings > Game Paths > aggiungi la sua cartella",
        "es": "[MH3U Online] Todavía no hay ningún juego MH3U en este paquete.\n"
              "  Cemu se abrirá igualmente, pero su lista de juegos estará vacía hasta que\n"
              "  añadas TU propia copia legal de MH3U. Dos formas:\n"
              "    1) copia las carpetas code/content/meta de tu copia en:\n"
              "         {gamedir}\n"
              "    2) o en Cemu: Options > General Settings > Game Paths > añade su carpeta",
        "ja": "[MH3U Online] このパックにはまだMH3Uのゲームがありません。\n"
              "  Cemuは起動しますが、あなた自身が正規に吸い出したMH3Uを追加するまで\n"
              "  ゲームリストは空のままです。方法は2つ：\n"
              "    1) 吸い出したデータの code/content/meta フォルダーを次の場所にコピー：\n"
              "         {gamedir}\n"
              "    2) またはCemuの Options > General Settings > Game Paths でそのフォルダーを追加",
    },
    "[MH3U Online] Your Cemu account has no online identity yet — setting one up...": {
        "fr": "[MH3U Online] Votre compte Cemu n'a pas encore d'identité en ligne — création en cours...",
        "de": "[MH3U Online] Dein Cemu-Konto hat noch keine Online-Identität – sie wird eingerichtet ...",
        "it": "[MH3U Online] Il tuo account Cemu non ha ancora un'identità online: la sto creando...",
        "es": "[MH3U Online] Tu cuenta de Cemu aún no tiene identidad en línea; configurándola...",
        "ja": "[MH3U Online] Cemuのアカウントにオンライン用のIDがまだありません。設定しています...",
    },
    "[MH3U Online] First run — creating your unique online identity...": {
        "fr": "[MH3U Online] Premier lancement — création de votre identité en ligne unique...",
        "de": "[MH3U Online] Erster Start – deine eindeutige Online-Identität wird erstellt ...",
        "it": "[MH3U Online] Primo avvio: creo la tua identità online unica...",
        "es": "[MH3U Online] Primer inicio: creando tu identidad en línea única...",
        "ja": "[MH3U Online] 初回起動：あなた専用のオンラインIDを作成しています...",
    },
    "[MH3U Online] Identity ready (NEX PID {pid}).": {
        "fr": "[MH3U Online] Identité prête (NEX PID {pid}).",
        "de": "[MH3U Online] Identität bereit (NEX PID {pid}).",
        "it": "[MH3U Online] Identità pronta (NEX PID {pid}).",
        "es": "[MH3U Online] Identidad lista (NEX PID {pid}).",
        "ja": "[MH3U Online] IDの準備ができました（NEX PID {pid}）。",
    },
    "[MH3U Online] Saved host = {host}": {
        "fr": "[MH3U Online] Hôte enregistré = {host}",
        "de": "[MH3U Online] Gespeicherter Host = {host}",
        "it": "[MH3U Online] Host salvato = {host}",
        "es": "[MH3U Online] Anfitrión guardado = {host}",
        "ja": "[MH3U Online] 保存したホスト = {host}",
    },
    "[MH3U Online] WARNING: no host IP set — enter the host's IP and Save first.": {
        "fr": "[MH3U Online] ATTENTION : aucune IP d'hôte définie — saisissez l'IP de l'hôte et enregistrez d'abord.",
        "de": "[MH3U Online] WARNUNG: keine Host-IP gesetzt – gib zuerst die IP des Hosts ein und speichere.",
        "it": "[MH3U Online] ATTENZIONE: nessun IP host impostato; inserisci prima l'IP dell'host e salva.",
        "es": "[MH3U Online] AVISO: no hay IP de anfitrión; escribe primero la IP del anfitrión y guarda.",
        "ja": "[MH3U Online] 警告：ホストのIPが設定されていません。先にホストのIPを入力して保存してください。",
    },
    "[MH3U Online] (launch suppressed)": {
        "fr": "[MH3U Online] (lancement désactivé)",
        "de": "[MH3U Online] (Start unterdrückt)",
        "it": "[MH3U Online] (avvio disattivato)",
        "es": "[MH3U Online] (inicio desactivado)",
        "ja": "[MH3U Online] （起動は省略）",
    },
    "[MH3U Online] ERROR: {exe} not found next to the launcher.": {
        "fr": "[MH3U Online] ERREUR : {exe} introuvable à côté du lanceur.",
        "de": "[MH3U Online] FEHLER: {exe} nicht neben dem Launcher gefunden.",
        "it": "[MH3U Online] ERRORE: {exe} non trovato accanto al launcher.",
        "es": "[MH3U Online] ERROR: no se encontró {exe} junto al lanzador.",
        "ja": "[MH3U Online] エラー：ランチャーと同じ場所に {exe} がありません。",
    },
    "[MH3U Online] Host = {ip} — launching Cemu...": {
        "fr": "[MH3U Online] Hôte = {ip} — lancement de Cemu...",
        "de": "[MH3U Online] Host = {ip} – Cemu wird gestartet ...",
        "it": "[MH3U Online] Host = {ip}: avvio di Cemu...",
        "es": "[MH3U Online] Anfitrión = {ip}: iniciando Cemu...",
        "ja": "[MH3U Online] ホスト = {ip}：Cemuを起動しています...",
    },
    "[MH3U Online] ERROR launching Cemu: {err}": {
        "fr": "[MH3U Online] ERREUR au lancement de Cemu : {err}",
        "de": "[MH3U Online] FEHLER beim Starten von Cemu: {err}",
        "it": "[MH3U Online] ERRORE durante l'avvio di Cemu: {err}",
        "es": "[MH3U Online] ERROR al iniciar Cemu: {err}",
        "ja": "[MH3U Online] Cemuの起動エラー：{err}",
    },

    # ---- Host tab -------------------------------------------------------------------------
    "Host": {
        "fr": "Héberger",
        "de": "Hosten",
        "it": "Ospita",
        "es": "Alojar",
        "ja": "ホスト",
    },
    "server.exe is missing from this folder.": {
        "fr": "server.exe est absent de ce dossier.",
        "de": "server.exe fehlt in diesem Ordner.",
        "it": "server.exe manca in questa cartella.",
        "es": "Falta server.exe en esta carpeta.",
        "ja": "このフォルダーに server.exe がありません。",
    },
    "The all-in-one bundle ships server.exe next to this launcher.\nIf it's gone (antivirus "
    "quarantine or a partial unzip), re-download\nthe latest bundle from Releases and extract it fully.": {
        "fr": "Le pack complet fournit server.exe à côté de ce lanceur.\nS'il a disparu (quarantaine "
              "antivirus ou extraction partielle), retéléchargez\nle dernier pack depuis Releases et "
              "extrayez-le entièrement.",
        "de": "Das Komplettpaket enthält server.exe neben diesem Launcher.\nFehlt sie (Virenschutz-"
              "Quarantäne oder unvollständig entpackt), lade\ndas neueste Paket unter Releases erneut "
              "herunter und entpacke es vollständig.",
        "it": "Il pacchetto completo include server.exe accanto a questo launcher.\nSe manca (quarantena "
              "dell'antivirus o estrazione parziale), scarica di nuovo\nl'ultimo pacchetto da Releases "
              "ed estrailo completamente.",
        "es": "El paquete completo incluye server.exe junto a este lanzador.\nSi ha desaparecido "
              "(cuarentena del antivirus o descompresión parcial), vuelve a descargar\nel último "
              "paquete desde Releases y extráelo por completo.",
        "ja": "オールインワン版には、このランチャーと同じ場所に server.exe が入っています。\n"
              "ない場合（ウイルス対策による隔離や解凍の失敗）は、Releases から\n"
              "最新版をダウンロードし直して、すべて解凍してください。",
    },
    "Open Releases page": {
        "fr": "Ouvrir la page Releases",
        "de": "Releases-Seite öffnen",
        "it": "Apri la pagina Releases",
        "es": "Abrir la página de Releases",
        "ja": "Releases ページを開く",
    },
    "Which IP will friends connect to?": {
        "fr": "À quelle IP vos amis se connecteront-ils ?",
        "de": "Mit welcher IP verbinden sich deine Freunde?",
        "it": "A quale IP si collegheranno i tuoi amici?",
        "es": "¿A qué IP se conectarán tus amigos?",
        "ja": "フレンドが接続するIPはどれですか？",
    },
    "This PC only — 127.0.0.1": {
        "fr": "Ce PC uniquement — 127.0.0.1",
        "de": "Nur dieser PC – 127.0.0.1",
        "it": "Solo questo PC — 127.0.0.1",
        "es": "Solo este PC — 127.0.0.1",
        "ja": "このPCのみ — 127.0.0.1",
    },
    "or type any IP:": {
        "fr": "ou saisissez une IP :",
        "de": "oder gib eine IP ein:",
        "it": "oppure inserisci un IP:",
        "es": "o escribe cualquier IP:",
        "ja": "またはIPを入力：",
    },
    "Relay hunt traffic through this PC (experimental)": {
        "fr": "Relayer le trafic de chasse via ce PC (expérimental)",
        "de": "Jagd-Datenverkehr über diesen PC weiterleiten (experimentell)",
        "it": "Inoltra il traffico di caccia tramite questo PC (sperimentale)",
        "es": "Retransmitir el tráfico de caza a través de este PC (experimental)",
        "ja": "狩猟の通信をこのPC経由で中継する（試験的）",
    },
    "Friends won't need port forwarding, including on cellular / CGNAT,\nand players won't see each "
    "other's IP addresses. All hunt traffic\nuses your upload, and UDP 27100-27387 must be open too.": {
        "fr": "Vos amis n'auront pas besoin de redirection de ports, même en 4G / CGNAT,\net les joueurs "
              "ne verront pas les adresses IP des autres. Tout le trafic de chasse\nutilise votre débit "
              "montant, et les ports UDP 27100-27387 doivent aussi être ouverts.",
        "de": "Deine Freunde brauchen keine Portweiterleitung, auch nicht im Mobilfunk / CGNAT,\nund "
              "die Spieler sehen die IP-Adressen der anderen nicht. Der gesamte Jagd-Verkehr\nläuft "
              "über deinen Upload, und UDP 27100-27387 muss ebenfalls offen sein.",
        "it": "I tuoi amici non avranno bisogno del port forwarding, anche su rete mobile / CGNAT,\ne i "
              "giocatori non vedranno gli indirizzi IP degli altri. Tutto il traffico di caccia\nusa il "
              "tuo upload, e anche le porte UDP 27100-27387 devono essere aperte.",
        "es": "Tus amigos no necesitarán redirigir puertos, ni siquiera con datos móviles / CGNAT,\ny "
              "los jugadores no verán las IP de los demás. Todo el tráfico de caza\nusa tu subida, y "
              "también deben estar abiertos los puertos UDP 27100-27387.",
        "ja": "フレンドはポート開放が不要になり（モバイル回線やCGNATでも可）、\nプレイヤー同士の"
              "IPアドレスも見えなくなります。狩猟の通信はすべて\nあなたの上り回線を使い、"
              "UDP 27100-27387 の開放も必要です。",
    },
    "Start Server": {
        "fr": "Démarrer le serveur",
        "de": "Server starten",
        "it": "Avvia server",
        "es": "Iniciar servidor",
        "ja": "サーバー起動",
    },
    "Stop Server": {
        "fr": "Arrêter le serveur",
        "de": "Server stoppen",
        "it": "Arresta server",
        "es": "Detener servidor",
        "ja": "サーバー停止",
    },
    "Host + Play": {
        "fr": "Héberger + Jouer",
        "de": "Hosten + Spielen",
        "it": "Ospita + Gioca",
        "es": "Alojar + Jugar",
        "ja": "ホストしてプレイ",
    },
    "[Host] Server already running.": {
        "fr": "[Host] Le serveur tourne déjà.",
        "de": "[Host] Der Server läuft bereits.",
        "it": "[Host] Il server è già avviato.",
        "es": "[Host] El servidor ya está en marcha.",
        "ja": "[Host] サーバーはすでに起動しています。",
    },
    "[Host] ERROR: no server.exe or server.py found.": {
        "fr": "[Host] ERREUR : aucun server.exe ou server.py trouvé.",
        "de": "[Host] FEHLER: keine server.exe oder server.py gefunden.",
        "it": "[Host] ERRORE: nessun server.exe o server.py trovato.",
        "es": "[Host] ERROR: no se encontró server.exe ni server.py.",
        "ja": "[Host] エラー：server.exe も server.py も見つかりません。",
    },
    "Friends connect to:  {ip}": {
        "fr": "Vos amis se connectent à :  {ip}",
        "de": "Freunde verbinden sich mit:  {ip}",
        "it": "Gli amici si collegano a:  {ip}",
        "es": "Tus amigos se conectan a:  {ip}",
        "ja": "フレンドの接続先：  {ip}",
    },
    "[Host] Starting server ({kind}), advertising {ip} ...": {
        "fr": "[Host] Démarrage du serveur ({kind}), adresse annoncée {ip}...",
        "de": "[Host] Server wird gestartet ({kind}), angekündigte Adresse {ip} ...",
        "it": "[Host] Avvio del server ({kind}), indirizzo annunciato {ip} ...",
        "es": "[Host] Iniciando el servidor ({kind}), anunciando {ip} ...",
        "ja": "[Host] サーバーを起動中（{kind}）、公開するIP {ip} ...",
    },
    "[Host] Starting server ({kind}), advertising {ip}, relay ON ...": {
        "fr": "[Host] Démarrage du serveur ({kind}), adresse annoncée {ip}, relais ACTIVÉ...",
        "de": "[Host] Server wird gestartet ({kind}), angekündigte Adresse {ip}, Relay AN ...",
        "it": "[Host] Avvio del server ({kind}), indirizzo annunciato {ip}, relay ATTIVO ...",
        "es": "[Host] Iniciando el servidor ({kind}), anunciando {ip}, relé ACTIVADO ...",
        "ja": "[Host] サーバーを起動中（{kind}）、公開するIP {ip}、中継オン ...",
    },
    "[Host] ERROR starting server: {err}": {
        "fr": "[Host] ERREUR au démarrage du serveur : {err}",
        "de": "[Host] FEHLER beim Starten des Servers: {err}",
        "it": "[Host] ERRORE durante l'avvio del server: {err}",
        "es": "[Host] ERROR al iniciar el servidor: {err}",
        "ja": "[Host] サーバー起動エラー：{err}",
    },
    "[Host] Server stopped.": {
        "fr": "[Host] Serveur arrêté.",
        "de": "[Host] Server gestoppt.",
        "it": "[Host] Server arrestato.",
        "es": "[Host] Servidor detenido.",
        "ja": "[Host] サーバーを停止しました。",
    },
    "[Host] Stopping server ...": {
        "fr": "[Host] Arrêt du serveur...",
        "de": "[Host] Server wird gestoppt ...",
        "it": "[Host] Arresto del server ...",
        "es": "[Host] Deteniendo el servidor ...",
        "ja": "[Host] サーバーを停止中...",
    },
    "[Host] stop error: {err}": {
        "fr": "[Host] erreur d'arrêt : {err}",
        "de": "[Host] Fehler beim Stoppen: {err}",
        "it": "[Host] errore di arresto: {err}",
        "es": "[Host] error al detener: {err}",
        "ja": "[Host] 停止エラー：{err}",
    },

    # ---- updates --------------------------------------------------------------------------
    "Close Cemu and the server before updating.": {
        "fr": "Fermez Cemu et le serveur avant la mise à jour.",
        "de": "Schließe Cemu und den Server vor dem Update.",
        "it": "Chiudi Cemu e il server prima di aggiornare.",
        "es": "Cierra Cemu y el servidor antes de actualizar.",
        "ja": "アップデートの前にCemuとサーバーを閉じてください。",
    },
    "Updating": {
        "fr": "Mise à jour",
        "de": "Aktualisierung",
        "it": "Aggiornamento",
        "es": "Actualizando",
        "ja": "アップデート中",
    },
    "Downloading update {tag} …": {
        "fr": "Téléchargement de la mise à jour {tag}…",
        "de": "Update {tag} wird heruntergeladen …",
        "it": "Download dell'aggiornamento {tag} …",
        "es": "Descargando la actualización {tag} …",
        "ja": "アップデート {tag} をダウンロード中…",
    },
    "Update ready — the launcher will restart.": {
        "fr": "Mise à jour prête — le lanceur va redémarrer.",
        "de": "Update bereit – der Launcher startet neu.",
        "it": "Aggiornamento pronto: il launcher verrà riavviato.",
        "es": "Actualización lista: el lanzador se reiniciará.",
        "ja": "アップデートの準備ができました。ランチャーを再起動します。",
    },
    "Updated to {tag}.": {
        "fr": "Mis à jour vers {tag}.",
        "de": "Auf {tag} aktualisiert.",
        "it": "Aggiornato a {tag}.",
        "es": "Actualizado a {tag}.",
        "ja": "{tag} にアップデートしました。",
    },
    "up to date": {
        "fr": "à jour",
        "de": "aktuell",
        "it": "aggiornato",
        "es": "actualizado",
        "ja": "最新です",
    },
    "Update failed: {err}": {
        "fr": "Échec de la mise à jour : {err}",
        "de": "Update fehlgeschlagen: {err}",
        "it": "Aggiornamento non riuscito: {err}",
        "es": "La actualización falló: {err}",
        "ja": "アップデートに失敗しました：{err}",
    },
    "update check failed — offline?": {
        "fr": "échec de la recherche de mises à jour — hors ligne ?",
        "de": "Update-Prüfung fehlgeschlagen – offline?",
        "it": "controllo aggiornamenti non riuscito: offline?",
        "es": "no se pudo buscar actualizaciones: ¿sin conexión?",
        "ja": "アップデートを確認できません（オフライン？）",
    },
    "Update {tag} available": {
        "fr": "Mise à jour {tag} disponible",
        "de": "Update {tag} verfügbar",
        "it": "Aggiornamento {tag} disponibile",
        "es": "Actualización {tag} disponible",
        "ja": "アップデート {tag} があります",
    },
    "latest is {tag}": {
        "fr": "dernière version : {tag}",
        "de": "neueste Version: {tag}",
        "it": "ultima versione: {tag}",
        "es": "la última es {tag}",
        "ja": "最新は {tag}",
    },
    "  skip (in use): {m}": {
        "fr": "  ignoré (en cours d'utilisation) : {m}",
        "de": "  übersprungen (in Verwendung): {m}",
        "it": "  saltato (in uso): {m}",
        "es": "  omitido (en uso): {m}",
        "ja": "  スキップ（使用中）：{m}",
    },
}
