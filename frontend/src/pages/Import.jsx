import React, { useEffect, useMemo, useRef, useState } from 'react'
import { useHilfe } from '../HilfeContext'
import { haushaltsbuchApi, importPdfApi, kontenApi } from '../api'
import { auswaehlbareKonten } from '../kontoAuswahl'
import Modal from '../components/Modal'
import { useConfirm } from '../components/useConfirm'
import { EyeIcon } from '../components/icons'

function fmt(n) {
  return new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' }).format(n)
}

// Abstimmung der Datei gegen ihre eigenen Kontostaende (siehe
// CsvProfilParser._saldo_pruefen). PDF-Auszuege liefern keinen Saldo, dann
// bleibt die Anzeige weg.
function saldoText(p) {
  if (!p || !p.modus || p.modus === 'keiner' || p.stimmt === null) return null
  if (p.modus === 'zeile') {
    return p.stimmt
      ? { ok: true, text: `Saldo-Kette geprüft: ${p.uebergaenge} Übergänge ohne Bruch` }
      : { ok: false, text: `Saldo-Kette gebrochen (${p.anzahl_brueche}×, erstmals ${p.brueche?.[0] || '?'})` }
  }
  return p.stimmt
    ? { ok: true, text: 'Saldo stimmt: Anfangsbestand + Summe = Endbestand' }
    : { ok: false, text: `Saldo weicht um ${fmt(p.abweichung ?? 0)} ab` }
}

// Spiegelt _betrag_aehnlich im Backend (import_pdf.py): Beträge innerhalb der
// Toleranz, aber nur bei gleichem Vorzeichen.
function betragAehnlich(a, b, spanne) {
  if (!spanne) return false
  if ((a < 0) !== (b < 0)) return false
  return Math.abs(a - b) <= spanne
}

// Gruppiert das Archiv nach dem Jahr des Auszugs-Zeitraums, nicht nach dem
// Importzeitpunkt: ein im Januar hochgeladener Dezember-Auszug gehoert
// fachlich ins Vorjahr. Jahre absteigend, innerhalb absteigend nach Beginn
// des Zeitraums. Ein Auszug mit Zeitraum ueber die Jahresgrenze steht genau
// einmal in der Liste (im Jahr seines Beginns) - doppelt angezeigt waeren
// Zeilenzahl und Loeschen mehrdeutig.
const OHNE_ZEITRAUM = 'Ohne Zeitraum'

// zeitraum_von/bis sind min/max Buchungsdatum und bleiben bei 0 geparsten
// Zeilen leer (siehe ParseResult im Backend). Solche Auszuege bekommen eine
// eigene Gruppe am Ende, statt still nach Importdatum in ein Jahr zu rutschen,
// in das sie vielleicht nicht gehoeren.
function gruppenJahr(a) {
  return a.zeitraum_von ? a.zeitraum_von.slice(0, 4) : OHNE_ZEITRAUM
}

function nachJahrGruppieren(auszuege) {
  const gruppen = new Map()
  for (const a of auszuege) {
    const jahr = gruppenJahr(a)
    if (!gruppen.has(jahr)) gruppen.set(jahr, [])
    gruppen.get(jahr).push(a)
  }
  for (const liste of gruppen.values()) {
    liste.sort((x, y) =>
      (y.zeitraum_von || '').localeCompare(x.zeitraum_von || '')
      || (y.importiert_am || '').localeCompare(x.importiert_am || '')
      || y.id - x.id)
  }
  return [...gruppen.entries()]
    .sort(([a], [b]) => {
      if (a === OHNE_ZEITRAUM) return 1
      if (b === OHNE_ZEITRAUM) return -1
      return b.localeCompare(a)
    })
    .map(([jahr, liste]) => ({ jahr, liste }))
}

export default function Import() {
  const { openHilfe } = useHilfe()
  const [konten, setKonten] = useState([])
  const [kontoId, setKontoId] = useState('')
  const [datei, setDatei] = useState(null)
  const [vorschau, setVorschau] = useState(null)
  const [ausgewaehlt, setAusgewaehlt] = useState(new Set())
  const [loading, setLoading] = useState(false)
  const [committing, setCommitting] = useState(false)
  const [ergebnis, setErgebnis] = useState(null)
  const [fehler, setFehler] = useState(null)
  const [abgleichVorschlaege, setAbgleichVorschlaege] = useState([])
  const [verknuepfenLaden, setVerknuepfenLaden] = useState(null)
  const [expandiert, setExpandiert] = useState(new Set())
  const [gewaehlteTreffer, setGewaehlteTreffer] = useState({}) // import_hash → booking_id
  const [auffrischen, setAuffrischen] = useState(false)
  // Der Auszugszeitraum, den der Benutzer bestaetigt. Nur bei CSV abgefragt:
  // daraus ergibt sich, welche PDF-Zeilen spaeter gesperrt sind. Vorbelegt aus
  // min/max der Buchungsdaten, aber bewusst aenderbar - die Datei sagt nicht,
  // welchen Zeitraum der Auszug abdeckt.
  const [zeitraum, setZeitraum] = useState({ von: '', bis: '' })
  // CSV-Import: das Profil ist hier der Parser. `maske` haelt den
  // Erkennungsvorschlag, solange die Zuordnung noch bestaetigt werden muss;
  // `profilId` das Profil, mit dem Vorschau und Commit arbeiten.
  const [maske, setMaske] = useState(null)
  const [profilId, setProfilId] = useState(null)
  const [profilLaden, setProfilLaden] = useState(false)
  // Archiv der bereits importierten Auszuege zum gewaehlten Konto
  const [auszuege, setAuszuege] = useState([])
  const [auszugAnsicht, setAuszugAnsicht] = useState(null)
  const [tabelle, setTabelle] = useState(null)
  const [tabelleFehler, setTabelleFehler] = useState(null)
  // Format und Zeitraum eines archivierten Auszugs richtigstellen. Beides
  // traegt die Zeitraum-Sperre und ist beim Altbestand geraten: das Format aus
  // der Dateiendung, der Zeitraum aus min/max der Buchungsdaten.
  const [auszugBearbeitet, setAuszugBearbeitet] = useState(null)
  const [auszugSpeichern, setAuszugSpeichern] = useState(false)
  const fileRef = useRef()
  const { confirm, dialog } = useConfirm()
  const auszugJahre = useMemo(() => nachJahrGruppieren(auszuege), [auszuege])
  // Zugeklappte Jahre, nicht aufgeklappte: so bleibt alles offen, solange
  // niemand etwas zuklappt - auch ein Jahr, das erst nach einem Import
  // dazukommt.
  const [zugeklappteJahre, setZugeklappteJahre] = useState(() => new Set())
  function jahrUmschalten(jahr) {
    const zuklappen = !zugeklappteJahre.has(jahr)
    setZugeklappteJahre(alt => {
      const neu = new Set(alt)
      if (zuklappen) neu.add(jahr)
      else neu.delete(jahr)
      return neu
    })
    // Ein offenes Bearbeiten-Formular in diesem Jahr waere sonst nur
    // ausgeblendet und seine Eingaben beim naechsten Aufklappen noch da.
    if (zuklappen && auszugBearbeitet) {
      const a = auszuege.find(x => x.id === auszugBearbeitet.id)
      if (a && gruppenJahr(a) === jahr) setAuszugBearbeitet(null)
    }
  }

  useEffect(() => {
    kontenApi.list(false).then(r => setKonten(r.data))
  }, [])

  // Die Tabelle erst holen, wenn ein Auszug wirklich angesehen wird - nicht
  // schon beim Aufbau der Archivliste, in der 25 Auszuege stehen koennen.
  useEffect(() => {
    setTabelle(null)
    setTabelleFehler(null)
    const a = auszugAnsicht
    if (!a || a.dateiname.toLowerCase().endsWith('.pdf')) return
    let aktuell = true
    importPdfApi.auszugTabelle(a.id)
      .then(r => { if (aktuell) setTabelle(r.data) })
      .catch(e => {
        if (aktuell) setTabelleFehler(e.response?.data?.detail ?? 'Die Datei liess sich nicht als Tabelle lesen.')
      })
    // Auszug gewechselt, waehrend die vorige Antwort noch unterwegs war: dann
    // darf sie nicht mehr in den Zustand.
    return () => { aktuell = false }
  }, [auszugAnsicht])

  // Bewusst ohne useEffect auf kontoId: das Archiv haengt allein an der
  // Kontoauswahl, und die aendert sich nur durch einen Klick im Formular.
  const ladeAuszuege = (id) => {
    if (!id) { setAuszuege([]); return }
    importPdfApi.auszuege(+id).then(r => setAuszuege(r.data)).catch(() => setAuszuege([]))
  }

  const zeigeVorschau = async (mitProfil = profilId) => {
    if (!kontoId || !datei) return
    setLoading(true)
    setFehler(null)
    setVorschau(null)
    setErgebnis(null)
    setAusgewaehlt(new Set())
    try {
      const r = await importPdfApi.vorschau(+kontoId, datei, mitProfil)
      setVorschau(r.data)
      setMaske(null)
      // Bei CSV den Zeitraum aus den Buchungsdaten vorbelegen. Er ist damit
      // immer zu eng - faengt der Auszug am 1. an und die erste Buchung am 3.,
      // fehlen zwei Tage. Der Kasten sagt das und bittet um die Korrektur.
      if (r.data.format === 'csv') {
        const tage = r.data.buchungen.map(b => b.datum).filter(Boolean).sort()
        setZeitraum({ von: tage[0] ?? '', bis: tage[tage.length - 1] ?? '' })
      } else {
        setZeitraum({ von: '', bis: '' })
      }
      // Standardmäßig alle Nicht-Duplikate angehakt. Zeilen, die zusammen eine
      // vorhandene Sammelbuchung ergeben, bleiben aus: sie einzeln zu
      // importieren zählt denselben Betrag ein zweites Mal. Gesperrte Zeilen
      // ebenso - die kann der Server gar nicht importieren.
      const inGruppe = new Set((r.data.sammelauftraege ?? []).flatMap(g => g.hashes))
      setAusgewaehlt(new Set(
        r.data.buchungen
          .filter(b => !b.duplikat && !b.gesperrt && !b.duplikat_verdacht && !inGruppe.has(b.import_hash))
          .map(b => b.import_hash)
      ))
    } catch (e) {
      const d = e.response?.data?.detail
      // 409 mit Vorschlag: die Datei ist lesbar, nur ihre Spalten sind noch
      // nicht zugeordnet. Kein Fehler, sondern die Zuordnungsmaske.
      if (e.response?.status === 409 && d?.profil_fehlt) {
        setMaske({
          name: d.profil?.name || '',
          struktur: d.struktur || {},
          zuordnung: { ...(d.profil?.zuordnung || d.zuordnung || {}) },
          kopf: d.kopf || [],
          felder: d.felder || [],
          probe: d.probe || [],
          zeilen_gesamt: d.zeilen_gesamt ?? 0,
          kopfzeilen_text: d.kopfzeilen_text || [],
          vorhandenes_profil: d.profil || null,
          quote: d.quote ?? 0,
        })
      } else {
        setFehler(typeof d === 'string' ? d : (d?.fehler ?? 'Fehler beim Parsen'))
      }
    } finally {
      setLoading(false)
    }
  }

  // Beim Dateiwechsel ein eventuell gesetztes Profil vergessen: die naechste
  // Datei kann von einer anderen Bank sein, und ein falsches Profil liest sie
  // still falsch statt den Dienst zu verweigern.
  const dateiGewaehlt = (f) => {
    setDatei(f)
    setProfilId(null)
    setMaske(null)
    resetErgebnisse()
  }

  const maskeFeldSetzen = (feld, spalte) => {
    setMaske(m => {
      const zuordnung = { ...m.zuordnung }
      if (spalte) zuordnung[feld] = spalte
      else delete zuordnung[feld]
      return { ...m, zuordnung }
    })
  }

  const profilSpeichern = async () => {
    setProfilLaden(true)
    setFehler(null)
    try {
      const daten = {
        name: maske.name?.trim() || 'Unbenannt',
        struktur: maske.struktur,
        zuordnung: maske.zuordnung,
        kopf_signatur: maske.kopf,
        aktiv: true,
      }
      const r = maske.vorhandenes_profil
        ? await importPdfApi.csvProfilAendern(maske.vorhandenes_profil.id, daten)
        : await importPdfApi.csvProfilAnlegen(daten)
      setProfilId(r.data.id)
      await zeigeVorschau(r.data.id)
    } catch (e) {
      const d = e.response?.data?.detail
      setFehler(typeof d === 'string' ? d : 'Profil konnte nicht gespeichert werden')
    } finally {
      setProfilLaden(false)
    }
  }

  const commit = async () => {
    const hatTreffer = Object.keys(gewaehlteTreffer).length > 0
    const hatAuffrischen = auffrischen && (vorschau?.duplikate ?? 0) > 0
    // Nichts zu uebernehmen und auch nichts uebernehmbar: dann ist der Lauf
    // reines Archivieren und darf trotzdem laufen (Zeitraum-Sperre).
    const nurArchiv = vorschau?.importierbar === 0
    if (!kontoId || !datei) return
    if (ausgewaehlt.size === 0 && !hatTreffer && !hatAuffrischen && !nurArchiv) return
    if (vorschau?.format === 'csv' && zeitraum.von && zeitraum.bis && zeitraum.von > zeitraum.bis) {
      setFehler('Der bestätigte Auszugszeitraum endet vor seinem Anfang.')
      return
    }
    setCommitting(true)
    setFehler(null)
    try {
      const r = await importPdfApi.commit(
        +kontoId, datei, [...ausgewaehlt], gewaehlteTreffer, auffrischen, profilId,
        vorschau?.format === 'csv' ? zeitraum : null,
      )
      setErgebnis(r.data)
      setAbgleichVorschlaege(r.data.abgleich_vorschlaege || [])
      setVorschau(null)
      setAusgewaehlt(new Set())
      setGewaehlteTreffer({})
      setAuffrischen(false)
      setDatei(null)
      if (fileRef.current) fileRef.current.value = ''
      // Der Commit hat das PDF archiviert (oder einen vorhandenen Eintrag
      // wiederverwendet) - Liste nachziehen.
      ladeAuszuege(kontoId)
    } catch (e) {
      setFehler(e.response?.data?.detail ?? 'Fehler beim Import')
    } finally {
      setCommitting(false)
    }
  }

  const auszugBearbeitenStarten = (a) => {
    setFehler(null)
    setAuszugBearbeitet({
      id: a.id,
      von: a.zeitraum_von ?? '',
      bis: a.zeitraum_bis ?? '',
      format: a.format ?? '',
    })
  }

  const auszugSichern = async () => {
    const b = auszugBearbeitet
    if (!b) return
    if (b.von && b.bis && b.von > b.bis) {
      setFehler('Der Zeitraum endet vor seinem Anfang.')
      return
    }
    setAuszugSpeichern(true)
    setFehler(null)
    try {
      await importPdfApi.auszugAendern(b.id, {
        zeitraum_von: b.von || null,
        zeitraum_bis: b.bis || null,
        format: b.format,
      })
      setAuszugBearbeitet(null)
      ladeAuszuege(kontoId)
    } catch (e) {
      setFehler(e.response?.data?.detail ?? 'Der Auszug liess sich nicht ändern.')
    } finally {
      setAuszugSpeichern(false)
    }
  }

  const auszugLoeschen = async (a) => {
    const frage = a.anzahl_buchungen > 0
      ? `Auszug „${a.dateiname}“ aus dem Archiv löschen? Die importierten Buchungen bleiben erhalten, sie verlieren nur den Verweis auf diesen Auszug.`
      : `Auszug „${a.dateiname}“ aus dem Archiv löschen?`
    if (!await confirm(frage)) return
    await importPdfApi.auszugLoeschen(a.id)
    if (auszugAnsicht?.id === a.id) setAuszugAnsicht(null)
    ladeAuszuege(kontoId)
  }

  const toggleRow = (hash) => {
    setAusgewaehlt(prev => {
      const next = new Set(prev)
      next.has(hash) ? next.delete(hash) : next.add(hash)
      return next
    })
  }

  const toggleExpandiert = (hash, e) => {
    e.stopPropagation()
    setExpandiert(prev => {
      const next = new Set(prev)
      next.has(hash) ? next.delete(hash) : next.add(hash)
      return next
    })
  }

  const waehleNaheBuchung = (importHash, buchungId, e) => {
    e.stopPropagation()
    setGewaehlteTreffer(prev => {
      const istBereitsGewählt = prev[importHash] === buchungId
      const next = { ...prev }
      if (istBereitsGewählt) {
        delete next[importHash]
        // Auswahl aufheben → PDF-Eintrag wieder zum Import vormerken
        setAusgewaehlt(p => { const s = new Set(p); s.add(importHash); return s })
      } else {
        next[importHash] = buchungId
        // Treffer gewählt → PDF-Eintrag nicht importieren
        setAusgewaehlt(p => { const s = new Set(p); s.delete(importHash); return s })
      }
      return next
    })
  }

  const toggleAlle = () => {
    if (!vorschau) return
    const inGruppe = new Set((vorschau.sammelauftraege ?? []).flatMap(g => g.hashes))
    const waehlbar = vorschau.buchungen
      .filter(b => !b.duplikat && !b.gesperrt && !b.duplikat_verdacht && !inGruppe.has(b.import_hash))
      .map(b => b.import_hash)
    const alleAn = waehlbar.every(h => ausgewaehlt.has(h))
    setAusgewaehlt(alleAn ? new Set() : new Set(waehlbar))
  }

  // Der Vorschlag kommt fertig aus dem Backend: nur dort ist bekannt, welche
  // Buchung schon eine andere Zeile derselben Datei belegt, und nur dort laesst
  // sich die Zuordnung eins zu eins halten. Zweimal 50 Euro am selben Tag
  // bekommen so zwei verschiedene Buchungen und nicht beide dieselbe.
  const autoTreffer = () => {
    if (!vorschau) return 0
    const vorschlag = vorschau.treffer_vorschlag ?? {}
    const neueGewählt = { ...gewaehlteTreffer }
    const neueAusgewaehlt = new Set(ausgewaehlt)
    let anzahl = 0
    for (const [hash, buchungId] of Object.entries(vorschlag)) {
      if (neueGewählt[hash]) continue
      neueGewählt[hash] = buchungId
      neueAusgewaehlt.delete(hash)
      anzahl++
    }
    setGewaehlteTreffer(neueGewählt)
    setAusgewaehlt(neueAusgewaehlt)
    return anzahl
  }

  // Zugeordnete Zeilen mit einem Hinweis, nach Grund getrennt. Ein verschobenes
  // Datum und eine Rateentscheidung sind zwei verschiedene Dinge und gehoeren
  // nicht in denselben Topf.
  const hinweisZeilen = () => {
    const h = vorschau?.treffer_hinweise ?? {}
    const offen = Object.entries(h).filter(([hash]) => gewaehlteTreffer[hash])
    return {
      datum: offen.filter(([, w]) => w.abstand > 0),
      mehrere: offen.filter(([, w]) => w.mehrere),
    }
  }

  const resetErgebnisse = () => {
    setVorschau(null)
    setErgebnis(null)
    setFehler(null)
    setAusgewaehlt(new Set())
    setExpandiert(new Set())
    setGewaehlteTreffer({})
    setAuffrischen(false)
    setAbgleichVorschlaege([])
  }

  const verknuepfen = async (buchungId, eintragId) => {
    setVerknuepfenLaden(eintragId)
    try {
      await haushaltsbuchApi.verknuepfen(eintragId, buchungId)
      setAbgleichVorschlaege(prev =>
        prev
          .map(v => v.buchung_id === buchungId
            ? { ...v, kandidaten: v.kandidaten.filter(k => k.id !== eintragId) }
            : v)
          .filter(v => v.kandidaten.length > 0)
      )
    } catch (e) {
      setFehler(e.response?.data?.detail ?? 'Fehler beim Verknüpfen')
    } finally {
      setVerknuepfenLaden(null)
    }
  }

  const reset = () => {
    resetErgebnisse()
    setDatei(null)
    if (fileRef.current) fileRef.current.value = ''
  }

  // Zeilen, die zu einer vorhandenen Sammelbuchung gehoeren. Einzeln anhaken
  // laesst sie sich weiter, "alle auswaehlen" fasst sie aber nicht an.
  const gruppenHashes = new Set((vorschau?.sammelauftraege ?? []).flatMap(g => g.hashes))
  const waehlbar = vorschau
    ? vorschau.buchungen.filter(b => !b.duplikat && !b.duplikat_verdacht && !gruppenHashes.has(b.import_hash))
    : []
  const alleAn = waehlbar.length > 0 && waehlbar.every(b => ausgewaehlt.has(b.import_hash))
  const teilweiseAn = !alleAn && waehlbar.some(b => ausgewaehlt.has(b.import_hash))

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h2 className="text-xl font-bold">Kontoauszug importieren</h2>
        <button type="button" onClick={() => openHilfe('pdf-import')} className="text-sm text-blue-600 hover:underline">Hilfe dazu</button>
      </div>

      {/* Upload-Formular */}
      <div className="card space-y-3">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div>
            <label className="label">Konto*</label>
            <select className="input" value={kontoId} onChange={e => { setKontoId(e.target.value); resetErgebnisse(); ladeAuszuege(e.target.value) }}>
              <option value="">– wählen –</option>
              {auswaehlbareKonten(konten, kontoId).map(k => (
                <option key={k.id} value={k.id}>{k.name} ({k.bank || k.typ}){k.aktiv ? '' : ' – inaktiv'}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">Datei* (PDF oder CSV)</label>
            <input
              ref={fileRef}
              type="file"
              accept=".pdf,.csv,.txt,application/pdf,text/csv"
              className="input py-1.5"
              onChange={e => dateiGewaehlt(e.target.files[0] || null)}
            />
          </div>
        </div>
        <div className="flex gap-2">
          {/* Nicht onClick={zeigeVorschau}: React reicht dann das Klick-
              Ereignis als `mitProfil` durch, und das Formular schickt
              profil_id=[object Object] - der Server antwortet mit 422. */}
          <button
            className="btn-primary"
            onClick={() => zeigeVorschau()}
            disabled={!kontoId || !datei || loading}
          >
            {loading ? 'Analysiere…' : 'Vorschau anzeigen'}
          </button>
          {vorschau && (() => {
            const nichts = ausgewaehlt.size === 0
              && Object.keys(gewaehlteTreffer).length === 0
              && !(auffrischen && vorschau.duplikate > 0)
            // Ein vollstaendig gedeckter Auszug ist der Normalfall der
            // Zeitraum-Sperre, kein Fehlgriff: dann bleibt nichts zu
            // uebernehmen, aber das Archiv will die Datei trotzdem. Der Commit
            // legt sie ohnehin ab, der Knopf sagt hier nur was er tut.
            const nurArchiv = nichts && vorschau.importierbar === 0
            return (
              <button
                className={nurArchiv ? 'btn-secondary' : 'btn-primary bg-green-600 hover:bg-green-700'}
                onClick={commit}
                disabled={committing || (nichts && !nurArchiv)}
                title={nurArchiv
                  ? 'Keine Zeile ist importierbar – die Datei wird nur ins Archiv gelegt'
                  : undefined}
              >
                {committing ? 'Übernehme…' : (nurArchiv ? 'Nur archivieren' : [
                  ausgewaehlt.size > 0 && `${ausgewaehlt.size} Buchungen importieren`,
                  Object.keys(gewaehlteTreffer).length > 0 && `${Object.keys(gewaehlteTreffer).length} Treffer verknüpfen`,
                  auffrischen && vorschau.duplikate > 0 && `${vorschau.duplikate} Duplikate auffrischen`,
                ].filter(Boolean).join(' · ') || 'Übernehmen')}
              </button>
            )
          })()}
        </div>
      </div>

      {/* Fehler */}
      {fehler && <div className="card border-red-200 bg-red-50 text-red-700 text-sm">{fehler}</div>}

      {/* Ergebnis */}
      {ergebnis && (() => {
        const ab = ergebnis.konto_abstimmung
        const schief = ab?.differenz != null && Math.abs(ab.differenz) >= 0.005
        return (
          <div className={`card ${schief ? 'border-red-300 bg-red-50' : 'border-green-200 bg-green-50'}`}>
            <p className={`font-medium ${schief ? 'text-red-800' : 'text-green-800'}`}>
              Import abgeschlossen: {ergebnis.importiert} neue Buchungen · {ergebnis.duplikate} Duplikate übersprungen
              {ergebnis.verknuepft > 0 && ` · ${ergebnis.verknuepft} Treffer verknüpft`}
              {ergebnis.gebucht_gesetzt > 0 && ` · ${ergebnis.gebucht_gesetzt} auf "gebucht" gesetzt`}
              {ergebnis.aufgefrischt > 0 && ` · ${ergebnis.aufgefrischt} Duplikate aufgefrischt`}
              {ergebnis.datum_korrigiert > 0 && ` · ${ergebnis.datum_korrigiert}× Datum auf das Bankdatum korrigiert`}
            </p>
            {/* Nachrechnen gegen die Bank, nicht gegen die eigene Erwartung. */}
            {ab?.differenz != null && (
              <p className={`text-sm mt-1 ${schief ? 'text-red-800' : 'text-green-700'}`}>
                {schief
                  ? `Achtung: Das Konto steht am ${ab.enddatum} bei ${fmt(ab.stand_danach)}, die Bank sagt ${fmt(ab.bank_saldo)} – ${fmt(ab.differenz)} Differenz.`
                  : `Kontostand am ${ab.enddatum}: ${fmt(ab.stand_danach)} – stimmt mit der Bank.`}
              </p>
            )}
          </div>
        )
      })()}

      {/* Abgleich-Vorschläge: importierte Buchungen <-> offene Haushaltsbuch-Einträge */}
      {abgleichVorschlaege.length > 0 && (
        <div className="card border-blue-200 bg-blue-50 space-y-3">
          <p className="text-blue-800 font-medium">
            {abgleichVorschlaege.length} importierte Buchung(en) passen evtl. zu offenen Haushaltsbuch-Einträgen
          </p>
          {abgleichVorschlaege.map(v => (
            <div key={v.buchung_id} className="space-y-1">
              <p className="text-sm text-gray-600">
                Buchung: <span className="font-medium">{v.buchung_empfaenger || '–'}</span> · {v.buchung_datum} · {fmt(v.buchung_betrag)}
              </p>
              <ul className="space-y-1">
                {v.kandidaten.map(k => (
                  <li key={k.id} className="flex items-center justify-between bg-white rounded px-3 py-1.5 text-sm">
                    <span>
                      {k.geschaeft?.name || 'Ohne Geschäft'} · {k.datum} · {fmt(-k.betrag_gesamt)}
                      {k.notiz && <span className="text-gray-400"> · {k.notiz}</span>}
                    </span>
                    <button
                      className="text-blue-600 hover:underline text-xs disabled:opacity-50"
                      disabled={verknuepfenLaden === k.id}
                      onClick={() => verknuepfen(v.buchung_id, k.id)}
                    >
                      {verknuepfenLaden === k.id ? 'Verknüpfe…' : 'Verknüpfen'}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}

      {/* Zuordnungsmaske fuer CSV-Dateien ohne Profil. Beim PDF ist das Layout
          der Parser, bei CSV diese Zuordnung - deshalb wird sie hier einmal
          bestaetigt und dann als Profil wiedererkannt. */}
      {maske && (
        <div className="card space-y-4 border-amber-300 bg-amber-50">
          <div>
            <p className="font-medium text-amber-900">
              {maske.vorhandenes_profil
                ? `Format weicht vom Profil „${maske.vorhandenes_profil.name}“ ab – Zuordnung prüfen`
                : 'Neues CSV-Format – Spalten einmal zuordnen'}
            </p>
            <p className="text-sm text-gray-600">
              {maske.zeilen_gesamt} Datenzeilen · Kodierung {maske.struktur.kodierung}
              {' · '}Trennzeichen „{maske.struktur.trennzeichen === '\t' ? 'Tabulator' : maske.struktur.trennzeichen}“
              {' · '}Datum {maske.struktur.datum_format}
              {' · '}Dezimaltrenner „{maske.struktur.dezimal}“
              {maske.vorhandenes_profil && ` · Spaltenübereinstimmung ${Math.round((maske.quote || 0) * 100)} %`}
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div>
              <label className="label">Name der Bank*</label>
              <input
                className="input"
                value={maske.name}
                placeholder="z. B. Postbank Giro"
                onChange={e => setMaske(m => ({ ...m, name: e.target.value }))}
              />
            </div>
            <div>
              <label className="label">Betragsform</label>
              <select
                className="input"
                value={maske.struktur.betrag_modus || 'betrag'}
                onChange={e => setMaske(m => ({ ...m, struktur: { ...m.struktur, betrag_modus: e.target.value } }))}
              >
                <option value="betrag">Eine Spalte mit Vorzeichen</option>
                <option value="soll_haben">Getrennte Soll-/Haben-Spalten</option>
              </select>
            </div>
            <div>
              <label className="label">Kontostand in der Datei</label>
              <select
                className="input"
                value={maske.struktur.saldo_modus || 'keiner'}
                onChange={e => setMaske(m => ({ ...m, struktur: { ...m.struktur, saldo_modus: e.target.value } }))}
              >
                <option value="zeile">An jeder Buchungszeile</option>
                <option value="datei">Im Kopf und Fuß der Datei</option>
                <option value="keiner">Nicht enthalten</option>
              </select>
            </div>
          </div>

          {/* Pro Zielfeld eine Spalte der Datei. Die Automatik hat schon
              gewaehlt; hier wird nur noch korrigiert. */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-x-4 gap-y-2">
            {maske.felder
              .filter(f => {
                if (maske.struktur.betrag_modus === 'soll_haben') return f.feld !== 'betrag'
                return f.feld !== 'soll' && f.feld !== 'haben'
              })
              .map(f => {
                const wert = maske.zuordnung[f.feld]
                return (
                  <div key={f.feld}>
                    <label className="label">{f.beschriftung}</label>
                    <select
                      className="input"
                      value={Array.isArray(wert) ? (wert[0] || '') : (wert || '')}
                      onChange={e => maskeFeldSetzen(f.feld, e.target.value)}
                    >
                      <option value="">– nicht vorhanden –</option>
                      {maske.kopf.filter(Boolean).map((spalte, i) => (
                        <option key={`${spalte}-${i}`} value={spalte}>{spalte}</option>
                      ))}
                    </select>
                  </div>
                )
              })}
          </div>

          {maske.vorhandenes_profil
            && maske.zuordnung.empfaenger !== maske.vorhandenes_profil.zuordnung?.empfaenger && (
            <p className="text-sm text-red-700">
              Die Empfängerspalte weicht vom gespeicherten Profil ab. Sie geht in den
              Import-Hash ein: nach dieser Änderung erscheinen bereits importierte
              Buchungen nicht mehr als Duplikat, sondern nur noch als Verdacht.
            </p>
          )}

          {/* Probe: die ersten Zeilen in den zugeordneten Spalten. Zeigt auf
              einen Blick, ob Datum und Betrag in der richtigen Spalte stehen. */}
          {maske.probe.length > 0 && (
            <div className="card p-0 overflow-x-auto bg-white">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-gray-500 border-b bg-gray-50 uppercase tracking-wide">
                    {Object.entries(maske.zuordnung).map(([feld, spalte]) => (
                      <th key={feld} className="px-3 py-2 whitespace-nowrap">
                        {maske.felder.find(f => f.feld === feld)?.beschriftung || feld}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {maske.probe.map((zeile, i) => (
                    <tr key={i} className="border-b last:border-0">
                      {Object.values(maske.zuordnung).map((spalte, j) => (
                        <td key={j} className="px-3 py-1.5 max-w-xs truncate">
                          {zeile[Array.isArray(spalte) ? spalte[0] : spalte] || '–'}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <div className="flex gap-2">
            <button
              className="btn-primary"
              disabled={profilLaden || !maske.name?.trim() || !maske.zuordnung.datum}
              onClick={profilSpeichern}
            >
              {profilLaden ? 'Speichere…' : (maske.vorhandenes_profil ? 'Profil aktualisieren und Vorschau' : 'Profil speichern und Vorschau')}
            </button>
            <button className="btn-secondary" onClick={() => setMaske(null)}>Abbrechen</button>
          </div>
        </div>
      )}

      {/* Vorschau-Tabelle */}
      {vorschau && (
        <div className="space-y-2">
          {/* Auszugszeitraum bestaetigen - nur bei CSV. Die Datei sagt nicht,
              welchen Zeitraum sie abdeckt: die Profile lesen nur Spalten und
              Saldo-Marken, keinen Zeitraum aus dem Kopf. Vorbelegt ist deshalb
              min/max der Buchungsdaten, und das ist immer zu eng. Aus diesem
              Zeitraum ergibt sich, welche PDF-Zeilen spaeter gesperrt sind. */}
          {vorschau.format === 'csv' && (
            <div className="card border-amber-300 bg-amber-50 space-y-2">
              <div className="flex flex-wrap items-end gap-3">
                <div>
                  <label className="label text-amber-900" htmlFor="zeitraum-von">Zeitraum des Auszugs – von</label>
                  <input
                    id="zeitraum-von"
                    type="date"
                    className="input"
                    value={zeitraum.von}
                    onChange={e => setZeitraum(z => ({ ...z, von: e.target.value }))}
                  />
                </div>
                <div>
                  <label className="label text-amber-900" htmlFor="zeitraum-bis">bis</label>
                  <input
                    id="zeitraum-bis"
                    type="date"
                    className="input"
                    value={zeitraum.bis}
                    onChange={e => setZeitraum(z => ({ ...z, bis: e.target.value }))}
                  />
                </div>
                {zeitraum.von && zeitraum.bis && zeitraum.von > zeitraum.bis && (
                  <span className="text-sm text-red-700 font-medium">Der Zeitraum endet vor seinem Anfang.</span>
                )}
              </div>
              <p className="text-xs text-amber-900">
                Vorbelegt aus den Buchungsdaten der Datei. Bitte auf den echten Auszugszeitraum korrigieren:
                daraus ergibt sich, welche Zeilen eines später hochgeladenen PDF-Auszugs gesperrt sind.
                Bleiben die Felder leer, wird der Zeitraum abgeleitet und als ungeprüft vermerkt.
              </p>
            </div>
          )}

          {/* Zeitraum-Sperre: was in diesem Lauf nicht mehr importiert werden
              kann, und warum. Steht ueber der Liste, damit die abgeblendeten
              Zeilen darunter nicht wie ein Fehler aussehen. */}
          {vorschau.gedeckt > 0 && (
            <div className="card border-amber-300 bg-amber-50 space-y-1 text-sm text-amber-900">
              <p>
                <strong>
                  {vorschau.gedeckt === 1
                    ? 'Eine Zeile liegt in einem Zeitraum, den ein CSV-Auszug abdeckt.'
                    : `${vorschau.gedeckt} Zeilen liegen in einem Zeitraum, den ein CSV-Auszug abdeckt.`}
                </strong>{' '}
                {vorschau.gesperrt > 0
                  ? `${vorschau.gesperrt === 1 ? 'Sie ist' : `${vorschau.gesperrt} davon sind`} gesperrt: ${vorschau.gesperrt === 1 ? 'sie hat' : 'sie haben'} eine Gegenbuchung und ${vorschau.gesperrt === 1 ? 'lässt' : 'lassen'} sich nur verknüpfen oder überspringen, nicht importieren.`
                  : 'Keine davon ist gesperrt – es gibt zu keiner eine Gegenbuchung, also kann nichts doppelt gezählt werden.'}
              </p>
              {vorschau.gedeckt > vorschau.gesperrt && vorschau.gesperrt > 0 && (
                <p className="text-xs">
                  {vorschau.gedeckt - vorschau.gesperrt === 1
                    ? 'Eine gedeckte Zeile bleibt importierbar, weil im Konto keine passende Buchung steht'
                    : `${vorschau.gedeckt - vorschau.gesperrt} gedeckte Zeilen bleiben importierbar, weil im Konto keine passende Buchung steht`}
                  {' – so füllt sich eine Lücke eines abgeschnittenen CSV-Exports.'}
                </p>
              )}
              <ul className="text-xs space-y-0.5">
                {vorschau.csv_deckung.map(d => (
                  <li key={d.auszug_id}>
                    <span className="font-mono">{d.von} – {d.bis}</span>{' '}
                    <span className="text-amber-800">{d.dateiname}</span>{' '}
                    {!d.bestaetigt && (
                      <span className="badge bg-gray-100 text-gray-700" title="Aus min/max der Buchungsdaten abgeleitet, nicht bestätigt – der Bereich ist damit eher zu eng">
                        Zeitraum abgeleitet
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="flex items-center gap-4 text-sm text-gray-600">
            <span>Bank: <strong>{vorschau.bank}</strong></span>
            {vorschau.konto_hinweis && <span>Konto: <span className="font-mono">{vorschau.konto_hinweis}</span></span>}
            <span className="text-green-700 font-medium">{ausgewaehlt.size} ausgewählt</span>
            <span className="text-gray-400">{vorschau.duplikate} Duplikate</span>
            {vorschau.gesperrt > 0 && <span className="text-amber-700 font-medium">{vorschau.gesperrt} gesperrt</span>}
            {vorschau.verdaechtigt > 0 && <span className="text-orange-600">{vorschau.verdaechtigt} Verdacht</span>}
            {vorschau.aehnlich > 0 && <span className="text-amber-600">{vorschau.aehnlich} ähnlich</span>}
            {(() => {
              const s = saldoText(vorschau.saldo_pruefung)
              return s && (
                <span className={s.ok ? 'text-green-700' : 'text-red-700 font-medium'}>
                  {s.ok ? '✓ ' : '⚠ '}{s.text}
                </span>
              )
            })()}
            <button type="button" onClick={() => openHilfe('import-abgleich')} className="text-xs text-blue-600 hover:underline">Was bedeutet das?</button>
            {waehlbar.length > 0 && (
              <button className="text-blue-600 hover:underline text-xs" onClick={toggleAlle}>
                {alleAn ? 'Alle abwählen' : 'Alle auswählen'}
              </button>
            )}
            {Object.keys(vorschau.treffer_vorschlag ?? {}).some(h => !gewaehlteTreffer[h]) && (
              <button className="btn-secondary btn-sm h-9 text-purple-700" onClick={autoTreffer}>
                ⚡ {Object.keys(vorschau.treffer_vorschlag).filter(h => !gewaehlteTreffer[h]).length} Zeilen
                vorhandenen Buchungen zuordnen
              </button>
            )}
            {vorschau.duplikate > 0 && (
              <label className="btn-secondary btn-sm cursor-pointer select-none">
                <input
                  type="checkbox"
                  className="haken"
                  checked={auffrischen}
                  onChange={e => setAuffrischen(e.target.checked)}
                />
                Duplikate mit den Werten der Datei auffrischen
              </label>
            )}
          </div>

          {/* Die Zuordnung schreibt in vorhandene Buchungen - auch das Datum.
              Was sie dabei verschiebt oder nur vermutet, muss sichtbar sein,
              sonst wandert eine Buchung still auf ein anderes Datum. */}
          {(() => {
            const h = hinweisZeilen()
            if (!h.datum.length && !h.mehrere.length) return null
            return (
              <div className="rounded border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900 space-y-1">
                {h.datum.length > 0 && (
                  <div>
                    <strong>{h.datum.length} Buchungen werden auf das Bankdatum verschoben</strong>{' '}
                    (um {Math.min(...h.datum.map(([, w]) => w.abstand))}–
                    {Math.max(...h.datum.map(([, w]) => w.abstand))} Tage). Das ist die Korrektur
                    falsch erfasster Daten – bitte stichprobenweise aufklappen und ansehen.
                  </div>
                )}
                {h.mehrere.length > 0 && (
                  <div>
                    <strong>{h.mehrere.length} Zuordnungen sind geraten</strong>: es standen
                    mehrere gleich gute Buchungen zur Wahl. Welche genommen wird, entscheidet
                    sonst die Reihenfolge.
                  </div>
                )}
              </div>
            )
          })()}

          {/* Eine vorhandene Buchung, die mehrere Zeilen der Datei zusammenfasst.
              Die Entscheidung gehoert dem Benutzer: Sammelbuchung behalten und
              die Zeilen auslassen, oder sie loeschen und einzeln importieren. */}
          {(vorschau.sammelauftraege ?? []).length > 0 && (
            <div className="rounded border border-orange-300 bg-orange-50 px-3 py-2 text-sm text-orange-900 space-y-2">
              <div>
                <strong>{vorschau.sammelauftraege.length} vorhandene Buchungen fassen mehrere
                Zeilen der Datei zusammen.</strong> Diese Zeilen sind nicht angehakt – einzeln
                importiert würden sie den Betrag ein zweites Mal zählen. Entweder so lassen, oder
                die Sammelbuchung löschen und die Zeilen danach einzeln holen.
              </div>
              {vorschau.sammelauftraege.map(g => (
                <div key={g.buchung.id} className="text-xs bg-white/60 rounded px-2 py-1">
                  <span className="tabular-nums">{g.buchung.datum}</span>{' · '}
                  <span className="font-medium">{g.buchung.empfaenger || '–'}</span>{' · '}
                  <span className="font-mono">{fmt(g.buchung.betrag)}</span>
                  {' = '}
                  {g.hashes.map(h => {
                    const z = vorschau.buchungen.find(b => b.import_hash === h)
                    return z ? `${fmt(z.betrag)} (${z.empfaenger || '–'})` : h
                  }).join(' + ')}
                </div>
              ))}
            </div>
          )}

          {/* Der Endsaldo der Datei ist die einzige Zahl hier, die die Bank
              selbst gesetzt hat. Stimmt sie nach dem Plan nicht, ist etwas
              doppelt oder fehlt - egal wie gut jede Zeile aussah. */}
          {vorschau.konto_abstimmung?.differenz != null && (
            <div className={[
              'rounded border px-3 py-2 text-sm',
              Math.abs(vorschau.konto_abstimmung.differenz) < 0.005
                ? 'border-green-300 bg-green-50 text-green-900'
                : 'border-red-300 bg-red-50 text-red-900',
            ].join(' ')}>
              {Math.abs(vorschau.konto_abstimmung.differenz) < 0.005 ? (
                <>
                  <strong>Kontostand stimmt.</strong> Nach diesem Vorschlag steht das Konto am{' '}
                  {vorschau.konto_abstimmung.enddatum} bei{' '}
                  {fmt(vorschau.konto_abstimmung.stand_danach)} – genau wie die Bank.
                </>
              ) : (
                <>
                  <strong>Kontostand weicht um {fmt(vorschau.konto_abstimmung.differenz)} ab.</strong>{' '}
                  Nach diesem Vorschlag stünde das Konto am {vorschau.konto_abstimmung.enddatum} bei{' '}
                  {fmt(vorschau.konto_abstimmung.stand_danach)}, die Bank sagt{' '}
                  {fmt(vorschau.konto_abstimmung.bank_saldo)}. Eine Zeile ist doppelt gezählt oder
                  es fehlt eine Buchung – vor dem Import klären.
                </>
              )}
            </div>
          )}

          <div className="card p-0 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-gray-500 border-b bg-gray-50 uppercase tracking-wide">
                  <th className="px-3 py-2 w-8">
                    <input
                      type="checkbox"
                      checked={alleAn}
                      ref={el => { if (el) el.indeterminate = teilweiseAn }}
                      onChange={toggleAlle}
                      className="haken"
                      title="Alle auswählen / abwählen"
                    />
                  </th>
                  <th className="px-3 py-2">Status</th>
                  <th className="px-3 py-2">Datum</th>
                  <th className="px-3 py-2">Empfänger</th>
                  <th className="px-3 py-2">Verwendung</th>
                  <th className="px-3 py-2 text-right">Betrag</th>
                  <th className="px-3 py-2">Kategorie (Match)</th>
                </tr>
              </thead>
              <tbody>
                {vorschau.buchungen.map((b, i) => {
                  const istAusgewaehlt = ausgewaehlt.has(b.import_hash)
                  const gewählterTreffer = gewaehlteTreffer[b.import_hash] ?? null
                  // Gesperrt heisst: der Server importiert diese Zeile nicht,
                  // also darf sie hier auch nicht anhakbar sein. Verknuepfen
                  // bleibt erlaubt - genau dafuer ist der PDF-Auszug im
                  // gedeckten Zeitraum noch da.
                  const istWaehlbar = !b.duplikat && !b.gesperrt && !gewählterTreffer
                  const hatTreffer = b.duplikat ? !!b.vorhandene_buchung : (b.nahe_buchungen?.length > 0)
                  const istExpandiert = expandiert.has(b.import_hash)
                  const trefferHinweis = (vorschau.treffer_hinweise ?? {})[b.import_hash] ?? null
                  return (
                    <React.Fragment key={i}>
                      <tr
                        onClick={() => istWaehlbar && toggleRow(b.import_hash)}
                        className={[
                          'border-b transition-colors',
                          b.duplikat
                            ? 'opacity-40 bg-gray-50'
                            // Gesperrt, aber nicht so weit abgeblendet wie ein
                            // Duplikat: hier wird noch verknuepft, und dafuer
                            // muessen die Kandidaten lesbar bleiben.
                            : b.gesperrt
                              ? 'opacity-70 bg-gray-50'
                              : istAusgewaehlt
                              ? 'bg-blue-50 hover:bg-blue-100 cursor-pointer'
                              : 'bg-white hover:bg-gray-50 cursor-pointer opacity-60',
                        ].join(' ')}
                      >
                        <td className="px-3 py-1.5" onClick={e => e.stopPropagation()}>
                          <input
                            type="checkbox"
                            checked={istAusgewaehlt}
                            disabled={!istWaehlbar}
                            onChange={() => toggleRow(b.import_hash)}
                            className={istWaehlbar ? 'haken' : 'haken opacity-30'}
                          />
                        </td>
                        <td className="px-3 py-1.5">
                          <span className="flex items-center gap-1 flex-wrap">
                            {b.gedeckt_von && (
                              <span
                                className={b.gesperrt
                                  ? 'badge bg-amber-100 text-amber-900'
                                  : 'badge bg-gray-100 text-gray-700'}
                                title={b.gesperrt
                                  ? `Im Zeitraum ${b.gedeckt_von.von} – ${b.gedeckt_von.bis} von „${b.gedeckt_von.dateiname}“. Es gibt eine Gegenbuchung, also nur verknüpfen oder überspringen.`
                                  : `Im Zeitraum ${b.gedeckt_von.von} – ${b.gedeckt_von.bis} von „${b.gedeckt_von.dateiname}“, aber ohne Gegenbuchung – darum importierbar.`}
                              >
                                {b.gesperrt ? 'CSV-Zeitraum · gesperrt' : 'CSV-Zeitraum'}
                              </span>
                            )}
                            {b.duplikat
                              ? <span className="badge badge-gray">Duplikat</span>
                              : b.duplikat_verdacht
                                ? <span className="badge bg-orange-100 text-orange-800">Verdacht</span>
                                : b.duplikat_aehnlich
                                  ? <span
                                      className="badge bg-amber-50 text-amber-700 border border-amber-200"
                                      title="Ähnliche Buchung im Toleranzfenster – nur ein Hinweis, die Zeile wird importiert"
                                    >ähnlich</span>
                                  : <span className="badge badge-green">Neu</span>}
                            {gewählterTreffer && (
                              trefferHinweis
                                ? <span
                                    className="badge bg-amber-100 text-amber-900 border border-amber-400"
                                    title={[
                                      trefferHinweis.abstand > 0
                                        && `Datum der vorhandenen Buchung wird um ${trefferHinweis.abstand} Tag(e) verschoben`,
                                      trefferHinweis.mehrere
                                        && 'Mehrere gleich gute Kandidaten – die Wahl ist geraten',
                                    ].filter(Boolean).join(' · ')}
                                  >
                                    ✓ Treffer –{' '}
                                    {trefferHinweis.abstand > 0 ? `${trefferHinweis.abstand} T.` : 'geraten'}
                                  </span>
                                : <span className="badge bg-green-100 text-green-800">✓ Treffer</span>
                            )}
                            {hatTreffer && (
                              <button
                                type="button"
                                title="Vorhandene Buchungen anzeigen"
                                onClick={e => toggleExpandiert(b.import_hash, e)}
                                className="btn-secondary btn-icon-sm"
                              >
                                {istExpandiert ? '▲' : '▼'}
                              </button>
                            )}
                          </span>
                        </td>
                        <td className="px-3 py-1.5 tabular-nums">{b.datum}</td>
                        <td className="px-3 py-1.5 max-w-[180px] truncate">{b.empfaenger || '–'}</td>
                        <td className="px-3 py-1.5 text-gray-400 text-xs max-w-[200px] truncate">{b.verwendungszweck || ''}</td>
                        <td className={`px-3 py-1.5 text-right font-mono font-medium ${b.betrag < 0 ? 'text-red-600' : 'text-green-700'}`}>
                          {fmt(b.betrag)}
                        </td>
                        <td className="px-3 py-1.5 text-gray-500 text-xs">
                          {b.empfaenger_name ? <span>{b.empfaenger_name}</span> : '–'}
                          {/* Sichtbar machen, was eine Import-Regel umgeschrieben hat –
                              sonst ändert der Import still Felder. */}
                          {b.regel_hinweis && (
                            <div className="text-blue-600" title="Import-Regel hat gegriffen">
                              {b.regel_hinweis}
                              {b.notiz && <span className="text-amber-600 ml-1">· Notiz: {b.notiz}</span>}
                            </div>
                          )}
                        </td>
                      </tr>
                      {istExpandiert && hatTreffer && (
                        <tr className="border-b bg-amber-50">
                          <td />
                          <td colSpan={6} className="px-4 py-2 space-y-1">
                            {b.duplikat ? (
                              /* Hard-Duplikat: Einzeleintrag */
                              <div className="flex items-center gap-4 text-xs text-amber-900">
                                <span className="font-medium text-amber-700">Vorhandene Buchung:</span>
                                <span className="tabular-nums">{b.vorhandene_buchung.datum}</span>
                                <span className="truncate max-w-[200px]">{b.vorhandene_buchung.empfaenger || '–'}</span>
                                {b.vorhandene_buchung.notiz && (
                                  <span className="text-amber-600 truncate max-w-[200px]">{b.vorhandene_buchung.notiz}</span>
                                )}
                                <span className={`font-mono font-medium ${b.vorhandene_buchung.betrag < 0 ? 'text-red-600' : 'text-green-700'}`}>
                                  {fmt(b.vorhandene_buchung.betrag)}
                                </span>
                              </div>
                            ) : (
                              /* Verdacht / Neu: alle Buchungen im Toleranzfenster */
                              <>
                                <div className="text-xs font-medium text-amber-700 mb-1">
                                  Buchungen im ±{vorschau.tage_toleranz}-Tage-Fenster ({b.nahe_buchungen.length}):
                                </div>
                                {b.nahe_buchungen.map(nb => {
                                  const istSoftMatch = nb.betrag === b.betrag
                                  const istAehnlich = !istSoftMatch && betragAehnlich(nb.betrag, b.betrag, vorschau.betrag_toleranz)
                                  const istGewählt = gewählterTreffer === nb.id
                                  return (
                                    <div
                                      key={nb.id}
                                      className={[
                                        'flex items-center gap-3 text-xs rounded px-2 py-1 cursor-pointer border transition-colors',
                                        istGewählt
                                          ? 'bg-green-100 border-green-400 text-green-900'
                                          : istSoftMatch
                                            ? 'bg-orange-100 border-orange-200 text-orange-900 hover:bg-orange-200'
                                            : istAehnlich
                                              ? 'bg-amber-50 border-amber-200 text-amber-900 hover:bg-amber-100'
                                              : 'border-transparent text-amber-900 hover:bg-amber-100',
                                      ].join(' ')}
                                      onClick={e => waehleNaheBuchung(b.import_hash, nb.id, e)}
                                    >
                                      <span className="tabular-nums w-24 shrink-0">{nb.datum}</span>
                                      <span className="truncate max-w-[200px]">{nb.empfaenger || '–'}</span>
                                      {nb.notiz && <span className="truncate max-w-[180px] opacity-70">{nb.notiz}</span>}
                                      <span className={`font-mono font-medium shrink-0 ${nb.betrag < 0 ? 'text-red-600' : 'text-green-700'}`}>
                                        {fmt(nb.betrag)}
                                      </span>
                                      {istSoftMatch && !istGewählt && <span className="badge bg-orange-200 text-orange-800 shrink-0">Betrag gleich</span>}
                                      {istAehnlich && !istGewählt && (
                                        <span className="badge bg-amber-100 text-amber-800 shrink-0">
                                          {fmt(Math.abs(nb.betrag - b.betrag))} Differenz
                                        </span>
                                      )}
                                      <span className="ml-auto shrink-0 font-medium">
                                        {istGewählt ? '✓ Gewählt – klicken zum Aufheben' : 'Als Treffer wählen'}
                                      </span>
                                    </div>
                                  )
                                })}
                              </>
                            )}
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Archiv: die PDFs, aus denen importiert wurde. Nachweis hinter jeder
          Buchung - deshalb liegt die Liste hier und nicht in den Einstellungen. */}
      {kontoId && (
        <div className="card space-y-2">
          <div className="flex items-baseline justify-between gap-2 flex-wrap">
            <h3 className="font-semibold">Gespeicherte Kontoauszüge</h3>
            <span className="text-xs text-gray-500">
              Werden beim Import abgelegt und sind im Backup enthalten.
            </span>
          </div>
          {auszuege.length === 0 ? (
            <p className="text-sm text-gray-500">
              Noch kein Auszug für dieses Konto archiviert.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead className="text-xs uppercase text-gray-500 border-b">
                  <tr>
                    <th className="text-left py-2 pr-3">Zeitraum</th>
                    <th className="text-left py-2 pr-3">Format</th>
                    <th className="text-left py-2 pr-3">Datei</th>
                    <th className="text-left py-2 pr-3">Bank</th>
                    <th className="text-right py-2 pr-3">Zeilen</th>
                    <th className="text-left py-2 pr-3">Importiert</th>
                    <th className="py-2"></th>
                  </tr>
                </thead>
                {auszugJahre.map(g => {
                const zu = zugeklappteJahre.has(g.jahr)
                return (
                <tbody key={g.jahr}>
                  <tr>
                    <th colSpan={7} className="pt-3 pb-1 font-normal">
                      {/* Pfeil und Jahreszahl schalten dasselbe, liegen aber
                          nebeneinander statt ineinander: ein Button im Button
                          waere ungueltiges HTML. */}
                      <div className="flex w-full items-center gap-2">
                        <button
                          type="button"
                          className="btn-secondary btn-icon-sm"
                          aria-expanded={!zu}
                          aria-label={zu ? `${g.jahr} aufklappen` : `${g.jahr} zuklappen`}
                          title={zu ? 'Aufklappen' : 'Zuklappen'}
                          onClick={() => jahrUmschalten(g.jahr)}
                        >
                          {zu ? '▸' : '▾'}
                        </button>
                        <button
                          type="button"
                          className="text-lg font-semibold tabular-nums text-gray-900 text-left"
                          onClick={() => jahrUmschalten(g.jahr)}
                        >
                          {g.jahr}
                        </button>
                        <span className="ml-auto text-xs text-gray-500">
                          {g.liste.length === 1 ? '1 Auszug' : `${g.liste.length} Auszüge`}
                        </span>
                      </div>
                    </th>
                  </tr>
                  {!zu && g.liste.map(a => (
                    <React.Fragment key={a.id}>
                    <tr className="border-b last:border-0 hover:bg-gray-50">
                      <td className="py-2 pr-3 tabular-nums whitespace-nowrap">
                        {a.zeitraum_von ? `${a.zeitraum_von} – ${a.zeitraum_bis}` : '–'}
                        {/* Ein CSV-Zeitraum sperrt spaetere PDF-Zeilen. Dass er
                            nur abgeleitet ist, gehoert deshalb dazu - sonst
                            sieht eine geratene Angabe wie eine gepruefte aus. */}
                        {a.zeitraum_von && !a.zeitraum_bestaetigt && (
                          <div
                            className="text-xs text-gray-500"
                            title="Aus min/max der Buchungsdaten abgeleitet – der echte Auszugszeitraum ist eher weiter"
                          >
                            abgeleitet
                          </div>
                        )}
                        {a.zeitraum_bestaetigt && (
                          <div className="text-xs text-green-700">bestätigt</div>
                        )}
                      </td>
                      <td className="py-2 pr-3">
                        {a.format === 'csv'
                          ? <span className="badge badge-green" title="Deckt seinen Zeitraum ab: ein PDF kann darin nur noch verknüpfen">CSV</span>
                          : a.format === 'pdf'
                            ? <span className="badge badge-gray">PDF</span>
                            : <span className="badge badge-gray" title="Format unbekannt – dieser Auszug deckt keinen Zeitraum ab">–</span>}
                      </td>
                      <td className="py-2 pr-3">
                        <button
                          type="button"
                          className="text-blue-600 hover:underline text-left"
                          onClick={() => setAuszugAnsicht(a)}
                        >
                          {a.dateiname}
                        </button>
                      </td>
                      <td className="py-2 pr-3">{a.bank || '–'}</td>
                      <td className="py-2 pr-3 text-right tabular-nums">{a.anzahl_buchungen}</td>
                      <td className="py-2 pr-3 whitespace-nowrap text-gray-500">
                        {a.importiert_am.slice(0, 10)}
                        {a.importiert_von ? ` · ${a.importiert_von}` : ''}
                      </td>
                      <td className="py-2 text-right whitespace-nowrap">
                        <button
                          type="button"
                          className="btn-secondary btn-icon mr-1"
                          title="Anzeigen"
                          aria-label="Anzeigen"
                          onClick={() => setAuszugAnsicht(a)}
                        >
                          <EyeIcon className="w-4 h-4" />
                        </button>
                        <button
                          type="button"
                          className="btn-secondary btn-icon mr-1"
                          title="Format und Zeitraum ändern"
                          aria-label="Format und Zeitraum ändern"
                          onClick={() => auszugBearbeitenStarten(a)}
                        >
                          ✎
                        </button>
                        <button
                          type="button"
                          className="btn-danger btn-icon"
                          title="Löschen"
                          aria-label="Löschen"
                          onClick={() => auszugLoeschen(a)}
                        >
                          ×
                        </button>
                      </td>
                    </tr>
                    {auszugBearbeitet?.id === a.id && (
                      <tr className="border-b bg-amber-50">
                        <td colSpan={7} className="py-3">
                          <div className="flex flex-wrap items-end gap-3">
                            <div>
                              <label className="label text-amber-900" htmlFor={`a-von-${a.id}`}>Zeitraum von</label>
                              <input
                                id={`a-von-${a.id}`}
                                type="date"
                                className="input"
                                value={auszugBearbeitet.von}
                                onChange={e => setAuszugBearbeitet(b => ({ ...b, von: e.target.value }))}
                              />
                            </div>
                            <div>
                              <label className="label text-amber-900" htmlFor={`a-bis-${a.id}`}>bis</label>
                              <input
                                id={`a-bis-${a.id}`}
                                type="date"
                                className="input"
                                value={auszugBearbeitet.bis}
                                onChange={e => setAuszugBearbeitet(b => ({ ...b, bis: e.target.value }))}
                              />
                            </div>
                            <div>
                              <label className="label text-amber-900" htmlFor={`a-format-${a.id}`}>Format</label>
                              <select
                                id={`a-format-${a.id}`}
                                className="input"
                                value={auszugBearbeitet.format}
                                onChange={e => setAuszugBearbeitet(b => ({ ...b, format: e.target.value }))}
                              >
                                <option value="">unbekannt</option>
                                <option value="pdf">PDF</option>
                                <option value="csv">CSV</option>
                              </select>
                            </div>
                            <button className="btn-primary" disabled={auszugSpeichern} onClick={auszugSichern}>
                              {auszugSpeichern ? 'Speichere…' : 'Speichern'}
                            </button>
                            <button className="btn-secondary" onClick={() => setAuszugBearbeitet(null)}>Abbrechen</button>
                            <p className="text-xs text-amber-900 basis-full">
                              Nur ein CSV-Auszug sperrt seinen Zeitraum für spätere PDF-Importe. Der Zeitraum gilt
                              nach dem Speichern als bestätigt — geben Sie ihn so an, wie er auf dem Auszug steht,
                              nicht wie die erste und letzte Buchung liegen.
                            </p>
                          </div>
                        </td>
                      </tr>
                    )}
                    </React.Fragment>
                  ))}
                </tbody>
                )})}
              </table>
            </div>
          )}
        </div>
      )}

      {/* Anzeige im eingebetteten PDF-Viewer des Browsers. Der Endpunkt liefert
          Content-Disposition "inline", sonst würde stattdessen ein Download
          starten. */}
      {auszugAnsicht && (
        <Modal
          onClose={() => setAuszugAnsicht(null)}
          title={auszugAnsicht.dateiname}
          maxWidth="max-w-5xl"
          footer={
            <div className="flex justify-between items-center gap-3">
              <span className="text-xs text-gray-500">
                {auszugAnsicht.zeitraum_von
                  ? `${auszugAnsicht.zeitraum_von} – ${auszugAnsicht.zeitraum_bis}`
                  : 'Kein Zeitraum erkannt'}
                {auszugAnsicht.bank ? ` · ${auszugAnsicht.bank}` : ''}
                {` · ${auszugAnsicht.anzahl_buchungen} Zeilen`}
              </span>
              <a
                href={importPdfApi.auszugDateiUrl(auszugAnsicht.id)}
                download={auszugAnsicht.dateiname}
                className="btn-secondary"
              >
                Herunterladen
              </a>
            </div>
          }
        >
          {/* Nur PDFs rendert der Browser selbst. Eine CSV kommt im iframe als
              eine Spalte Rohtext an, deshalb holt sie das Frontend zerlegt und
              zeichnet die Tabelle selbst. */}
          {auszugAnsicht.dateiname.toLowerCase().endsWith('.pdf') ? (
            <iframe
              src={importPdfApi.auszugDateiUrl(auszugAnsicht.id)}
              title={auszugAnsicht.dateiname}
              className="w-full h-[70vh] border rounded"
            />
          ) : tabelleFehler ? (
            <p className="text-sm text-red-700 py-8 text-center">
              {tabelleFehler} Über „Herunterladen“ lässt sich die Datei öffnen.
            </p>
          ) : !tabelle ? (
            <p className="text-sm text-gray-500 py-8 text-center">Datei wird gelesen…</p>
          ) : (
            <div className="space-y-2">
              <div className="text-xs text-gray-500">
                {tabelle.zeilen_gesamt} Zeilen
                {tabelle.gekuerzt && ` (nur die ersten ${tabelle.zeilen.length} angezeigt)`}
                {tabelle.trennzeichen && ` · Trennzeichen „${tabelle.trennzeichen === '\t' ? 'Tab' : tabelle.trennzeichen}“`}
                {tabelle.kodierung && ` · ${tabelle.kodierung}`}
              </div>

              {/* Der Vorlauf der Bank - Konto, Zeitraum, Anfangssaldo. Gehoert
                  nicht in die Tabelle, aber auch nicht unter den Tisch: dort
                  steht der Saldo, gegen den der Import gerechnet hat. */}
              {tabelle.vorlauf.length > 0 && (
                <div className="text-xs bg-gray-50 border rounded p-2 space-y-0.5 font-mono text-gray-600">
                  {tabelle.vorlauf.map((z, i) => (
                    <div key={i} className="truncate">{z.filter(Boolean).join(' · ')}</div>
                  ))}
                </div>
              )}

              <div className="overflow-auto max-h-[60vh] border rounded">
                <table className="text-xs whitespace-nowrap">
                  <thead className="sticky top-0 bg-gray-100">
                    <tr>
                      <th className="px-2 py-1 text-right text-gray-400 font-normal border-b">#</th>
                      {tabelle.kopf.map((h, i) => (
                        <th key={i} className="px-2 py-1 text-left font-medium border-b">{h || '–'}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {tabelle.zeilen.map((z, i) => (
                      <tr key={i} className={i % 2 ? 'bg-gray-50' : 'bg-white'}>
                        <td className="px-2 py-1 text-right text-gray-400 tabular-nums">{i + 1}</td>
                        {z.map((f, j) => (
                          <td key={j} className="px-2 py-1 max-w-[320px] truncate" title={f}>{f}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                  {tabelle.nachlauf.length > 0 && (
                    <tfoot className="bg-amber-50">
                      {tabelle.nachlauf.map((z, i) => (
                        <tr key={i}>
                          <td className="px-2 py-1 text-right text-gray-400">·</td>
                          <td className="px-2 py-1 font-mono text-amber-900" colSpan={tabelle.kopf.length}>
                            {z.filter(Boolean).join(' · ')}
                          </td>
                        </tr>
                      ))}
                    </tfoot>
                  )}
                </table>
              </div>
            </div>
          )}
        </Modal>
      )}

      {dialog}
    </div>
  )
}
