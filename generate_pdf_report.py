import json
from markdown_pdf import MarkdownPdf
from markdown_pdf.section import Section

markdown_content = """
# Report Architetturale: Estrazione e Archiviazione degli Effetti per la Valutazione del Team (VGC)

## 1. Introduzione e Fattibilità
Sì, è assolutamente possibile determinare in maniera univoca gli effetti di mosse, strumenti e abilità tramite tag strutturati.
Mentre **PokéAPI** fornisce eccellenti dati descrittivi e di classificazione, **Pokémon Showdown** è la risorsa definitiva per la logica competitiva. I file dati di Showdown (`moves.ts`, `abilities.ts`, `items.ts`) contengono nativamente sistemi di **flags** (tag) progettati per far funzionare il simulatore di battaglia, il che li rende perfetti per un motore di valutazione di composizione del team.

## 2. Identificare ed Estrarre gli Effetti (I Tag Nativi)

### 2.1 Approccio tramite Pokémon Showdown (Raccomandato)
I dati di Showdown strutturano gli effetti meccanici tramite dictionary e proprietà.

**Per le Mosse (`data/moves.ts`):**
*   **Oggetto `flags`:** Identifica interazioni meccaniche uniche. Esempi:
    *   `contact: 1` (attiva Rocky Helmet, Rough Skin).
    *   `protect: 1` (bloccabile da Protezione/Individua).
    *   `sound: 1` (bypassa Sostituto, counterabile da Soundproof).
    *   `punch: 1` (potenziata da Iron Fist).
    *   `bullet: 1` (bloccata da Bulletproof).
*   **Oggetto `secondary`:** Definisce gli effetti collaterali (es. probabilità di calo statistiche o alterazioni di stato).
    *   Esempio: `{chance: 10, status: 'frz'}` per Geloraggio.
*   **Proprietà `target`:** Definisce il raggio d'azione. `allAdjacentFoes` (danno spread), `any` (bersaglio singolo).

**Per le Abilità (`data/abilities.ts`):**
Le abilità sono più complesse da taggare automaticamente perché Showdown le gestisce tramite funzioni JavaScript native (`onModifyAtk`, `onStart`, ecc.). Tuttavia, analizzando parole chiave nei loro effetti, è possibile assegnare tag come `weather_setter`, `intimidate_clone`, o `stat_immunity`.

### 2.2 Approccio tramite PokéAPI (Ibrido)
PokéAPI espone per ogni mossa l'oggetto `meta`, che fornisce una categorizzazione utile ma meno granulare per il calcolo danni:
*   `category.name`: Distingue mosse `damage`, `ailment`, `heal`, `force-switch` (es. Roar).
*   `ailment.name`: Identifica lo stato inflitto (es. `paralysis`).
*   `stat_chance` / `healing` / `drain`: Valori interi per calcoli di cura e d'assorbimento.

**Conclusione sull'Estrazione:** Il miglior approccio è utilizzare uno script Python che parsa il JSON di Showdown per i `flags` meccanici, unendoli alle categorie `meta` di PokéAPI.

---

## 3. Store Intelligente nel Database (DB Architecture)

Per sviluppare una feature di **Team Composition Evaluation** fluida ed efficiente in PySide6, il database (es. SQLite o PostgreSQL) deve permettere l'incrocio rapido dei tag.

### Modello Relazionale con Tabelle di Associazione (Molti-a-Molti)
Questo è il design ottimale per interrogazioni complesse (es. "Mostrami tutti i Pokémon nel team vulnerabili alle mosse 'sound'").

1.  **Tabella `Tags` (Dizionario Master)**
    *   `id` (PK, Integer)
    *   `name` (String, es. "contact", "sound", "speed_control", "weather_rain")
    *   `category` (String, es. "mechanic", "utility", "offensive", "defensive")
2.  **Tabella `Moves` (Base)**
    *   `id`, `name`, `type`, `base_power`, `category` (Special/Physical/Status).
3.  **Tabella `Move_Tags` (Join Table)**
    *   `move_id` (FK), `tag_id` (FK)
    *   *Opzionale:* `value` (es. per salvare la probabilità di un effetto secondario, chance = 30).

### Inserimento Intelligente (ETL Pipeline)
Quando scarichi i dati da Showdown, esegui una mappatura euristica.
*   *Se `flags.sound == 1` -> INSERT INTO Move_Tags (move_id, tag_sound_id)*
*   *Se `target == 'allAdjacentFoes'` -> INSERT INTO Move_Tags (move_id, tag_spread_id)*
*   *Se mossa è "Tailwind" o "Icy Wind" -> INSERT INTO Move_Tags (move_id, tag_speed_control_id)*

---

## 4. Architettura della Feature "Valutazione Composizione Team"

Una volta che gli effetti sono "taggati" nel database, il motore di valutazione diventa una serie di regole (Rules Engine) basate su query SQL o manipolazione di array in Python.

### 4.1. Calcolo del "Team Coverage Score"
L'algoritmo analizza i 6 (o 4) Pokémon selezionati e le loro 24 (o 16) mosse:
1.  **Estrazione Profilo Team:**
    Query che unisce tutti i tag presenti nel team. Esempio in Python (SQLAlchemy/Peewee):
    ```python
    team_tags = execute("SELECT t.name FROM Tags t JOIN Move_Tags mt ON t.id = mt.tag_id WHERE mt.move_id IN (lista_mosse_team)")
    ```
2.  **Checklist di Valutazione (Esempi di Regole):**
    *   **Speed Control:** `if 'speed_control' not in team_tags: add_warning("Nessuna forma di controllo velocità (Tailwind/Trick Room/Icy Wind).")`
    *   **Redirect/Support:** `if 'redirect' in team_tags (Follow Me, Rage Powder): add_synergy("Eccellente per proteggere i setup sweeper.")`
    *   **Gestione Protect:** `if non ci sono mosse che bypassano o rompono protect (es. tag 'feint' o abilità 'unseen_fist'): add_tip("Attenzione ai team stall/protect pesanti.")`
    *   **Sinergie Danni Spread:** Se un Pokémon ha Earthquake (`tag: spread_ground`), l'algoritmo controlla se i partner hanno Abilità = Levitate (`tag: ground_immunity`) o tipo Volante. Se no, genera un **Alert Fuoco Amico**.

### 4.2. Visualizzazione in PySide6
Nella UI del *VGC Replay Analyzer*:
*   Usa un `QRadarChart` (Grafico a ragnatela) per mostrare il bilanciamento del team sugli assi: Offensiva, Difensiva, Speed Control, Utility, Synergies.
*   Crea un `QListWidget` popolato con icone rosse (Warning) o verdi (Synergy) generate dalle regole di controllo dei Tag appena elencate.
"""

pdf = MarkdownPdf()
pdf.add_section(Section(markdown_content))
pdf.save("report_valutazione_team_vgc.pdf")
print("PDF generated successfully.")
