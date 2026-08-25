---
name: pyqt6-flawless-vgc-dark-ui
description: "Architettura avanzata, design system e pattern operativi per interfacce PyQt6 dark, minimali, ottimizzate per tool di analisi con palette Ciano/Rosa/Verde pastello."
---

# PyQt6 Advanced Architecture & Dark UI/UX Standard

Questa skill definisce l'architettura rigorosa e i canoni estetici per sviluppare GUI PyQt6 ad alte prestazioni, con un focus specifico sull'uso di una palette cromatica pastello ad alto contrasto su sfondi dark, ideale per interfacce complesse (es. Replay Analyzer).

## 1. Architettura del Codice (Pattern MVVM / Unidirectional Data Flow)

La manutenibilità richiede un disaccoppiamento totale. Le Viste non devono contenere logica di business.

*   **Model-View-ViewModel (MVVM)**: 
    *   **View**: Solo classi PyQt (`QWidget`, `QMainWindow`). Definiscono layout e interazioni (QSS, segnali UI).
    *   **ViewModel**: Eredita da `QObject`. Gestisce lo stato e la logica di presentazione. Usa `@pyqtProperty`, `@pyqtSlot` e `pyqtSignal` per notificare cambiamenti di stato.
*   **Gestione dello Stato**: Approccio reattivo tramite segnali.
*   **Asset e Stringhe**: Qualsiasi stringa, icona o colore hardcodato in una View è un errore. Devono risiedere in file di configurazione (`config/strings.py`, `config/theme.py`).

## 2. Design System: Dark Mode & Pastel Palette

L'interfaccia deve mantenere sfondi molto scuri per far risaltare la gerarchia cromatica pastello specifica.

### 2.1. Palette Colori Rigida
*   **Sfondi Dark (Base)**:
    *   `$BG_APP`: `#0B0F19` (Sfondo finestra principale, molto profondo).
    *   `$BG_SURFACE`: `#111827` (Pannelli, background di default per i form).
    *   `$BG_SURFACE_ELEVATED`: `#1F2937` (Card in primo piano, menu a tendina, dialoghi).
*   **Colori Funzionali e di Dominio**:
    *   `$PRIMARY` (Ciano pastello - `#B6FAF5`): Colore dominante. Usa per: titoli principali, pulsanti in stato normale, bordi delle sezioni principali, Giocatore 2 (Replay Analyzer), bersagli delle azioni.
    *   `$SECONDARY` (Rosa pastello - `#FAB7F0`): Contrasto vivo. Usa per: hover dei pulsanti, nomi degli attori nei log, testo per informazioni specifiche (es. strumenti/oggetti nel replay).
    *   `$TERTIARY` (Verde pastello/scuro - `#467A77`): Stato solido. Usa per: click/pressed dei bottoni, selezioni in liste/tabelle, outline di elementi attivi, Giocatore 1 (Replay Analyzer).
*   **Testi Neutri**:
    *   `$TEXT_PRIMARY`: `#F3F4F6` (Testo base, mai bianco puro).
    *   `$TEXT_MUTED`: `#9CA3AF` (Etichette, descrizioni secondarie).

### 2.2. Tipografia e Spaziatura
*   **Font**: Utilizza font moderni (Geist, Inter). Pesi: 400 (Body), 600 (Titoli).
*   **Spaziatura (Grid 8pt System)**: Margini e padding multipli di 8. `setContentsMargins(24, 24, 24, 24)` per container.

## 3. Pattern Operativi PyQt6

### 3.1. Inizializzazione e HiDPI Scaling
Forza il rendering vettoriale su schermi high-res prima di istanziare `QApplication`:

```python
import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

def bootstrap_app():
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setStyle("Fusion") 
    return app