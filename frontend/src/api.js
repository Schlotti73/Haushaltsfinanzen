import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  withCredentials: true,
})

api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401 && window.location.pathname !== '/login') {
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

export default api

// ── Konten ──────────────────────────────────────────────────────────────────
export const kontenApi = {
  list: (nurAktiv = true) => api.get('/konten', { params: { nur_aktiv: nurAktiv } }),
  get: (id) => api.get(`/konten/${id}`),
  // geplant_ab: ab diesem Datum zaehlen geplante Buchungen mit
  saldo: (id, bis, geplantAb) => api.get(`/konten/${id}/saldo`, {
    params: { ...(bis ? { bis } : {}), ...(geplantAb ? { geplant_ab: geplantAb } : {}) },
  }),
  buchungenCount: (id) => api.get(`/konten/${id}/buchungen-count`),
  create: (data) => api.post('/konten', data),
  update: (id, data) => api.patch(`/konten/${id}`, data),
  delete: (id) => api.delete(`/konten/${id}`),
  // Depot
  depotUebersicht: () => api.get('/konten/depot-uebersicht'),
  // Darlehen
  darlehenUebersicht: () => api.get('/konten/darlehen-uebersicht'),
  hochrechnung: (id, mitSonder = true) => api.get(`/konten/${id}/darlehen-hochrechnung`, { params: { mit_sondertilgung: mitSonder } }),
  hochrechnungSzenario: (id, neuerTilgungssatz, zusatzSondertilgungJaehrlich = 0) =>
    api.get(`/konten/${id}/darlehen-hochrechnung-szenario`, {
      params: { neuer_tilgungssatz: neuerTilgungssatz, zusatz_sondertilgung_jaehrlich: zusatzSondertilgungJaehrlich },
    }),
  sondertilgungen: (id) => api.get(`/konten/${id}/sondertilgungen`),
  sonder: {
    create: (kid, data) => api.post(`/konten/${kid}/sondertilgungen`, data),
    update: (kid, sid, data) => api.patch(`/konten/${kid}/sondertilgungen/${sid}`, data),
    delete: (kid, sid) => api.delete(`/konten/${kid}/sondertilgungen/${sid}`),
  },
}

// ── Kategorien ──────────────────────────────────────────────────────────────
export const kategorienApi = {
  tree: () => api.get('/kategorien'),
  flat: () => api.get('/kategorien/flach'),
  create: (data) => api.post('/kategorien', data),
  update: (id, data) => api.patch(`/kategorien/${id}`, data),
  delete: (id) => api.delete(`/kategorien/${id}`),
}

// ── Projekte ─────────────────────────────────────────────────────────────────
export const projekteApi = {
  list: () => api.get('/projekte'),
  get: (id) => api.get(`/projekte/${id}`),
  darlehen: (id) => api.get(`/projekte/${id}/darlehen-raten`),
  budgetVsIst: (id) => api.get(`/projekte/${id}/budget-vs-ist`),
  create: (data) => api.post('/projekte', data),
  update: (id, data) => api.patch(`/projekte/${id}`, data),
  delete: (id) => api.delete(`/projekte/${id}`),
  // Geplante Ausgaben (Posten)
  planVsIst: (id) => api.get(`/projekte/${id}/plan-vs-ist`),
  geplanteAusgaben: (id) => api.get(`/projekte/${id}/geplante-ausgaben`),
  posten: {
    create: (pid, data) => api.post(`/projekte/${pid}/geplante-ausgaben`, data),
    update: (pid, gid, data) => api.patch(`/projekte/${pid}/geplante-ausgaben/${gid}`, data),
    delete: (pid, gid) => api.delete(`/projekte/${pid}/geplante-ausgaben/${gid}`),
    verknuepfen: (pid, gid, buchungIds) => api.post(`/projekte/${pid}/geplante-ausgaben/${gid}/verknuepfen`, { buchung_ids: buchungIds }),
    loesen: (pid, gid, buchungIds) => api.post(`/projekte/${pid}/geplante-ausgaben/${gid}/loesen`, { buchung_ids: buchungIds }),
  },
}

// ── Buchungen ────────────────────────────────────────────────────────────────
export const buchungenApi = {
  notizVorschlaege: () => api.get('/buchungen/notiz-vorschlaege'),
  list: (params) => api.get('/buchungen', { params }),
  get: (id) => api.get(`/buchungen/${id}`),
  empfaenger: () => api.get('/buchungen/empfaenger'),
  create: (data) => api.post('/buchungen', data),
  update: (id, data) => api.patch(`/buchungen/${id}`, data),
  delete: (id) => api.delete(`/buchungen/${id}`),
  deleteBulk: (ids) => api.delete('/buchungen/bulk', { data: ids }),
  // body: { ids } oder { alle_gefilterten: true, filter } plus die zu setzenden Felder
  updateBulk: (body) => api.patch('/buchungen/bulk', body),
  exportUrl: (format, filter) => {
    const p = new URLSearchParams({ format, ...Object.fromEntries(Object.entries(filter).filter(([, v]) => v !== '' && v != null)) })
    return `${api.defaults.baseURL}/buchungen/export?${p}`
  },
  transferKandidaten: (id) => api.get(`/buchungen/${id}/transfer-kandidaten`),
  transferVerknuepfen: (id, gegenbuchungId) => api.post(`/buchungen/${id}/transfer-verknuepfen`, null, { params: { gegenbuchung_id: gegenbuchungId } }),
  transferNeu: (id, zielkontoId, kategorieId) => api.post(`/buchungen/${id}/transfer-neu`, null, { params: { zielkonto_id: zielkontoId, ...(kategorieId ? { kategorie_id: kategorieId } : {}) } }),
  transferLoesen: (id) => api.post(`/buchungen/${id}/transfer-loesen`),
  hhKandidaten: (id) => api.get(`/buchungen/${id}/hh-kandidaten`),
  hhVerknuepfen: (id, hhId) => api.post(`/buchungen/${id}/hh-verknuepfen`, null, { params: { hh_id: hhId } }),
  hhLoesen: (id) => api.post(`/buchungen/${id}/hh-loesen`),
  hhEintrag: (id) => api.get(`/buchungen/${id}/hh-eintrag`),
  hhSelbstBestaetigen: (id) => api.post(`/buchungen/${id}/hh-selbst-bestaetigen`),
}

// ── Wiederkehrende Buchungen ──────────────────────────────────────────────────
export const wiederkehrendApi = {
  list: () => api.get('/wiederkehrend'),
  create: (data) => api.post('/wiederkehrend', data),
  update: (id, data) => api.patch(`/wiederkehrend/${id}`, data),
  delete: (id) => api.delete(`/wiederkehrend/${id}`),
}

// ── Statistik ────────────────────────────────────────────────────────────────
export const statistikApi = {
  monats: (params) => api.get('/statistik/monatsuebersicht', { params }),
  jahres: (params) => api.get('/statistik/jahresuebersicht', { params }),
  kategorien: (params) => api.get('/statistik/kategorien', { params }),
  geschaefte: (params) => api.get('/statistik/geschaefte', { params }),
  sollIst: (jahr) => api.get('/statistik/soll-ist', { params: { jahr } }),
  liquiditaet: (params) => api.get('/statistik/liquiditaet', { params }),
  sparkonten: () => api.get('/statistik/sparkonten'),
  hochrechnung: (monate = 12) => api.get('/statistik/hochrechnung', { params: { monate } }),
  exportCsv: (params) => api.get('/statistik/export/csv', { params, responseType: 'blob' }),
}

// ── Belege ───────────────────────────────────────────────────────────────────
export const belegeApi = {
  list: (buchungId) => api.get(`/belege/${buchungId}`),
  upload: (buchungId, datei) => {
    const form = new FormData()
    form.append('datei', datei)
    return api.post(`/belege/${buchungId}`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  dateUrl: (buchungId, belegId) => `/api/belege/${buchungId}/${belegId}/datei`,
  delete: (buchungId, belegId) => api.delete(`/belege/${buchungId}/${belegId}`),

  listEintrag: (eintragId) => api.get(`/belege/eintrag/${eintragId}`),
  uploadEintrag: (eintragId, datei) => {
    const form = new FormData()
    form.append('datei', datei)
    return api.post(`/belege/eintrag/${eintragId}`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  dateUrlEintrag: (eintragId, belegId) => `/api/belege/eintrag/${eintragId}/${belegId}/datei`,
  deleteEintrag: (eintragId, belegId) => api.delete(`/belege/eintrag/${eintragId}/${belegId}`),

  listGebaeude: (gebaeudeId) => api.get(`/belege/gebaeude/${gebaeudeId}`),
  uploadGebaeude: (gebaeudeId, datei) => {
    const form = new FormData()
    form.append('datei', datei)
    return api.post(`/belege/gebaeude/${gebaeudeId}`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  dateUrlGebaeude: (gebaeudeId, belegId) => `/api/belege/gebaeude/${gebaeudeId}/${belegId}/datei`,
  deleteGebaeude: (gebaeudeId, belegId) => api.delete(`/belege/gebaeude/${gebaeudeId}/${belegId}`),

  // Zählerstand-Foto: genau eines je Ablesung, ein neues ersetzt das alte.
  // `datei` ist der im Browser zugeschnittene Ausschnitt, kein Originalfoto.
  uploadAblesung: (ablesungId, datei) => {
    const form = new FormData()
    form.append('datei', datei)
    return api.post(`/belege/ablesung/${ablesungId}`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  // `stand` ist nur ein Cache-Brecher: SQLite vergibt nach dem Ersetzen oft
  // dieselbe Beleg-ID wieder, das neue Foto haette sonst dieselbe Adresse wie
  // das alte und der Browser zeigte weiter das alte Bild.
  dateUrlAblesung: (ablesungId, belegId, stand) =>
    `/api/belege/ablesung/${ablesungId}/${belegId}/datei${stand ? `?v=${stand}` : ''}`,
  deleteAblesung: (ablesungId, belegId) => api.delete(`/belege/ablesung/${ablesungId}/${belegId}`),
}

// ── Geschäfte (Phase 8) ───────────────────────────────────────────────────────
export const geschaefteApi = {
  list: (params) => api.get('/geschaefte', { params }),
  get: (id) => api.get(`/geschaefte/${id}`),
  create: (data) => api.post('/geschaefte', data),
  update: (id, data) => api.patch(`/geschaefte/${id}`, data),
  delete: (id) => api.delete(`/geschaefte/${id}`),
}

// ── Haushaltsbuch-Einträge (Phase 8) ──────────────────────────────────────────
export const haushaltsbuchApi = {
  list: (params) => api.get('/haushaltsbuch', { params }),
  get: (id) => api.get(`/haushaltsbuch/${id}`),
  create: (data) => api.post('/haushaltsbuch', data),
  update: (id, data) => api.patch(`/haushaltsbuch/${id}`, data),
  delete: (id) => api.delete(`/haushaltsbuch/${id}`),
  ocr: (id) => api.post(`/haushaltsbuch/${id}/ocr`),
  belegVorschauUrl: (id) => `/api/haushaltsbuch/${id}/beleg-vorschau`,
  artikelVorschlaege: (geschaeftId) => api.get('/haushaltsbuch/artikel-vorschlaege', { params: { geschaeft_id: geschaeftId } }),
  abgleichKandidaten: (params) => api.get('/haushaltsbuch/abgleich-kandidaten', { params }),
  verknuepfen: (id, buchungId) => api.post(`/haushaltsbuch/${id}/verknuepfen`, null, { params: { buchung_id: buchungId } }),
}

// ── Empfänger ────────────────────────────────────────────────────────────────
export const empfaengerApi = {
  list: (suche) => api.get('/empfaenger', { params: suche ? { suche } : {} }),
  get: (id) => api.get(`/empfaenger/${id}`),
  vorschlaege: (q, limit = 10) => api.get('/empfaenger/vorschlaege', { params: { q, limit } }),
  match: (text, iban) => api.get('/empfaenger/match', { params: { text, iban } }),
  create: (data) => api.post('/empfaenger', data),
  update: (id, data) => api.patch(`/empfaenger/${id}`, data),
  delete: (id) => api.delete(`/empfaenger/${id}`),
  zusammenfuehren: (id, ziel_id) => api.post(`/empfaenger/${id}/zusammenfuehren`, null, { params: { ziel_id } }),
}

// ── Kontoauszug-Import ───────────────────────────────────────────────────────────────
export const importPdfApi = {
  vorschau: (kontoId, datei, profilId) => {
    const form = new FormData()
    form.append('konto_id', kontoId)
    form.append('datei', datei)
    if (profilId) form.append('profil_id', profilId)
    return api.post('/import/pdf/vorschau', form, { headers: { 'Content-Type': 'multipart/form-data' } })
  },
  // `zeitraum` ist der im Dialog bestaetigte Auszugszeitraum ({von, bis}).
  // Nur bei CSV gefuellt: daraus ergibt sich, welche PDF-Zeilen spaeter
  // gesperrt sind. Fehlt er, leitet das Backend ihn aus den Buchungsdaten ab
  // und merkt den Eintrag als ungeprueft.
  commit: (kontoId, datei, hashes, treffer, auffrischen, profilId, zeitraum) => {
    const form = new FormData()
    form.append('konto_id', kontoId)
    form.append('datei', datei)
    form.append('hashes', JSON.stringify(hashes ?? []))
    if (treffer && Object.keys(treffer).length) form.append('treffer', JSON.stringify(treffer))
    if (auffrischen) form.append('auffrischen', 'true')
    if (profilId) form.append('profil_id', profilId)
    if (zeitraum?.von && zeitraum?.bis) {
      form.append('zeitraum_von', zeitraum.von)
      form.append('zeitraum_bis', zeitraum.bis)
    }
    return api.post('/import/pdf/commit', form, { headers: { 'Content-Type': 'multipart/form-data' } })
  },

  // CSV-Profile: beim PDF ist das Layout der Parser, bei CSV dieses Profil.
  csvErkennen: (datei) => {
    const form = new FormData()
    form.append('datei', datei)
    return api.post('/import/pdf/csv-erkennen', form, { headers: { 'Content-Type': 'multipart/form-data' } })
  },
  csvProfile:        ()         => api.get('/import/pdf/csv-profile'),
  csvProfilAnlegen:  (daten)    => api.post('/import/pdf/csv-profile', daten),
  csvProfilAendern:  (id, daten) => api.put(`/import/pdf/csv-profile/${id}`, daten),
  csvProfilLoeschen: (id)       => api.delete(`/import/pdf/csv-profile/${id}`),

  // Archiv der importierten Auszuege
  auszuege:      (kontoId) => api.get('/import/pdf/auszuege', { params: { konto_id: kontoId } }),
  // Direkte URL fuer das <iframe>; der Endpunkt liefert Content-Disposition
  // "inline", damit der PDF-Viewer des Browsers rendert statt herunterzuladen.
  auszugDateiUrl: (auszugId) => `/api/import/pdf/auszuege/${auszugId}/datei`,
  // Zerlegte CSV fuer die Tabellenansicht - im <iframe> waere sie eine Spalte
  // Rohtext, und Kodierung und Trennzeichen kennt nur das Backend.
  auszugTabelle: (auszugId) => api.get(`/import/pdf/auszuege/${auszugId}/tabelle`),
  // Format und Zeitraum nachtraeglich richtigstellen. Beides traegt die
  // Zeitraum-Sperre, und beim Altbestand ist beides geraten: das Format aus
  // der Dateiendung, der Zeitraum aus min/max der Buchungsdaten.
  auszugAendern: (auszugId, felder) => api.patch(`/import/pdf/auszuege/${auszugId}`, felder),
  auszugLoeschen: (auszugId) => api.delete(`/import/pdf/auszuege/${auszugId}`),
}

// ── Import-Regeln (Bankrohtext → definierte Werte) ───────────────────────────
export const importRegelApi = {
  list:         ()            => api.get('/import-regeln'),
  create:       (data)        => api.post('/import-regeln', data),
  update:       (id, data)    => api.patch(`/import-regeln/${id}`, data),
  delete:       (id)          => api.delete(`/import-regeln/${id}`),
  // anwenden=false liefert die reine Vorschau, ohne etwas zu schreiben.
  bestandslauf: (data)        => api.post('/import-regeln/bestandslauf', data),
  export:       ()            => api.get('/import-regeln/export'),
  import:       (daten)       => api.post('/import-regeln/import', daten),
  vorschlaege:  (limit = 25)  => api.get('/import-regeln/vorschlaege', { params: { limit } }),
}

// ── Generierung ──────────────────────────────────────────────────────────────
export const generierungApi = {
  vorschau: (monate = 12, kontoId) => api.post('/generierung/vorschau', null, { params: { monate, ...(kontoId ? { konto_id: kontoId } : {}) } }),
  ausfuehren: (monate = 12, kontoId) => api.post('/generierung/ausfuehren', null, { params: { monate, ...(kontoId ? { konto_id: kontoId } : {}) } }),
}

// ── Einstellungen ────────────────────────────────────────────────────────────
export const einstellungenApi = {
  getBackup:              ()     => api.get('/einstellungen/backup'),
  putBackup:              (data) => api.put('/einstellungen/backup', data),
  backupJetzt:            ()     => api.post('/einstellungen/backup/jetzt'),
  backupListe:            ()     => api.get('/einstellungen/backup/liste'),
  // Kein axios-Aufruf, sondern die URL fuer einen normalen Link: der Browser
  // streamt das ZIP (mit allen Belegen darin) auf die Platte, statt es als
  // Blob komplett im Speicher zu halten. Die Sitzung steckt im Cookie und
  // geht beim Link-Klick mit.
  backupDownloadUrl:      (name) => `/api/einstellungen/backup/herunterladen/${name}`,
  // erzwingen=true nur nach ausdrücklicher Bestätigung: überschreibt die aktive
  // DB mit einem Backup aus einer anderen registrierten Datenbank
  backupWiederherstellen: (name, erzwingen = false) =>
    api.post(`/einstellungen/backup/wiederherstellen/${name}`, null,
      erzwingen ? { params: { erzwingen: true } } : undefined),

  // Toleranzen für den Abgleich in der Kontoauszug-Import-Vorschau
  getImportAbgleich: ()     => api.get('/einstellungen/import-abgleich'),
  putImportAbgleich: (data) => api.put('/einstellungen/import-abgleich', data),

  // Dashboard-Anzeigeoptionen (lesend für jeden Benutzer, schreibend nur Admin)
  getDashboard: ()     => api.get('/einstellungen/dashboard'),
  putDashboard: (data) => api.put('/einstellungen/dashboard', data),

  // Kontoauszug-Muster (Phase 9)
  musterListe:      ()           => api.get('/einstellungen/kontoauszug-muster'),
  musterZielAttribute: ()        => api.get('/einstellungen/kontoauszug-muster/ziel-attribute'),
  musterUpdate:     (id, data)   => api.put(`/einstellungen/kontoauszug-muster/${id}`, data),
  musterLoeschen:   (id)         => api.delete(`/einstellungen/kontoauszug-muster/${id}`),
  musterUpload:     (name, keywords, datei) => {
    const form = new FormData()
    form.append('name', name)
    if (keywords) form.append('keywords', keywords)
    form.append('datei', datei)
    return api.post('/einstellungen/kontoauszug-muster/upload', form, { headers: { 'Content-Type': 'multipart/form-data' } })
  },
  musterBeispiel:   (id, datei)  => {
    const form = new FormData()
    form.append('datei', datei)
    return api.post(`/einstellungen/kontoauszug-muster/${id}/beispiel`, form, { headers: { 'Content-Type': 'multipart/form-data' } })
  },
  musterScreenshotUrl: (id)      => `/api/einstellungen/kontoauszug-muster/${id}/screenshot`,

  // Kassenzettel-Muster (Phase 10)
  kzListe:        ()           => api.get('/einstellungen/kassenzettel-muster'),
  kzKategorien:   ()           => api.get('/einstellungen/kassenzettel-muster/kategorien'),
  kzAnlegen:      (data)       => api.post('/einstellungen/kassenzettel-muster', data),
  kzUpdate:       (id, data)   => api.put(`/einstellungen/kassenzettel-muster/${id}`, data),
  kzLoeschen:     (id)         => api.delete(`/einstellungen/kassenzettel-muster/${id}`),
  kzProbe:        (id)         => api.post(`/einstellungen/kassenzettel-muster/${id}/probe`),
  kzBeispiel:     (id, datei)  => {
    const form = new FormData()
    form.append('datei', datei)
    return api.post(`/einstellungen/kassenzettel-muster/${id}/beispiel`, form, { headers: { 'Content-Type': 'multipart/form-data' } })
  },
  kzScreenshotUrl: (id)        => `/api/einstellungen/kassenzettel-muster/${id}/screenshot`,
  kzVorschauUrl:   (id)        => `/api/einstellungen/kassenzettel-muster/${id}/vorschau`,

  // Datenbanken (Mehrfach-DB-Verwaltung)
  dbListe:         ()          => api.get('/einstellungen/datenbanken'),
  dbErstellen:     (name)      => api.post('/einstellungen/datenbanken', { name }),
  dbWechseln:      (id)        => api.post(`/einstellungen/datenbanken/${id}/wechseln`),
  dbEntfernen:     (id)        => api.delete(`/einstellungen/datenbanken/${id}`),
  dbDateiLoeschen: (id)        => api.delete(`/einstellungen/datenbanken/${id}/datei`),
}

// ── Auth ─────────────────────────────────────────────────────────────────────
export const authApi = {
  // code: TOTP- oder Wiederherstellungscode, nur noetig bei Zugriff von aussen
  login: (name, passwort, code) => api.post('/auth/login', { name, passwort, code }),
  mfaStatus: () => api.get('/auth/mfa/status'),
  mfaEinrichten: () => api.post('/auth/mfa/einrichten'),
  mfaBestaetigen: (code) => api.post('/auth/mfa/bestaetigen', null, { params: { code } }),
  mfaDeaktivieren: (passwort) => api.post('/auth/mfa/deaktivieren', null, { params: { passwort } }),
  logout: () => api.post('/auth/logout'),
  me: () => api.get('/auth/me'),
  benutzer: () => api.get('/auth/benutzer'),
  createBenutzer: (data) => api.post('/auth/benutzer', data),
  updateBenutzer: (id, data) => api.patch(`/auth/benutzer/${id}`, data),
  deleteBenutzer: (id) => api.delete(`/auth/benutzer/${id}`),
}

// ── System ─────────────────────────────────────────────
export const systemApi = {
  version: () => api.get('/version'),
}

// ── Update-Pruefung ────────────────────────────────────────
export const updateApi = {
  // erzwingen=true umgeht den 15-Minuten-Zwischenspeicher der Release-Abfrage
  status: (erzwingen = false) => api.get('/update/status', { params: { erzwingen } }),
  einstellungen: () => api.get('/update/einstellungen'),
  speichern: (data) => api.put('/update/einstellungen', data),
  downloadStarten: () => api.post('/update/download'),
  downloadStand: () => api.get('/update/download'),
}

// ── Gebäude & Verbrauchszahlen ──────────────────────────────────────────────
export const erinnerungenApi = {
  list: () => api.get('/erinnerungen'),
}

export const gebaeudeApi = {
  list: (nurAktiv = true) => api.get('/gebaeude', { params: { nur_aktiv: nurAktiv } }),
  create: (data) => api.post('/gebaeude', data),
  update: (id, data) => api.patch(`/gebaeude/${id}`, data),
  delete: (id) => api.delete(`/gebaeude/${id}`),

  uebersicht: (id) => api.get(`/gebaeude/${id}/uebersicht`),
  vorschlaege: (id) => api.get(`/gebaeude/${id}/kategorie-vorschlaege`),

  zaehler: (id) => api.get(`/gebaeude/${id}/zaehler`),
  zaehlerCreate: (data) => api.post('/gebaeude/zaehler', data),
  zaehlerUpdate: (id, data) => api.patch(`/gebaeude/zaehler/${id}`, data),
  zaehlerDelete: (id) => api.delete(`/gebaeude/zaehler/${id}`),
  zaehlerWechsel: (id, params) => api.post(`/gebaeude/zaehler/${id}/wechsel`, null, { params }),

  ablesungen: (zaehlerId) => api.get(`/gebaeude/zaehler/${zaehlerId}/ablesungen`),
  ablesungCreate: (data) => api.post('/gebaeude/ablesungen', data),
  ablesungUpdate: (id, data) => api.patch(`/gebaeude/ablesungen/${id}`, data),
  ablesungDelete: (id) => api.delete(`/gebaeude/ablesungen/${id}`),
  pruefung: (zaehlerId, jahr, stand) =>
    api.get('/gebaeude/ablesungen/pruefung', { params: { zaehler_id: zaehlerId, jahr, stand } }),
  offeneAblesungen: () => api.get('/gebaeude/ablesungen/offen'),

  kostenkategorien: (id) => api.get(`/gebaeude/${id}/kostenkategorien`),
  kostenkategorieAdd: (id, kategorieId) =>
    api.post(`/gebaeude/${id}/kostenkategorien`, null, { params: { kategorie_id: kategorieId } }),
  kostenkategorieDelete: (zuordnungId) => api.delete(`/gebaeude/kostenkategorien/${zuordnungId}`),
}
