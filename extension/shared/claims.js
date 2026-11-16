/* Szybkie wykrywanie sprawdzalnych tez o klimacie - wielojezycznie, bez sieci.

   Teza = zdanie, ktore stwierdza cos o MIERZONEJ wielkosci (temperatura, poziom
   morza, lod morski, CO2 i inne gazy, emisje, opady, temperatura na Marsie...),
   najlepiej z wartoscia, okresem i miejscem. Prognozy, definicje, wyjasnienia
   przyczyn, pytania i reklamy nie sa tezami do sprawdzenia w danych.

   Punkty (tekst bez znakow diakrytycznych, male litery):
     wielkosc  +3   (WYMAGANA)
     wartosc   +3   liczba z jednostka (°C, ppm, mm, %, Gt...), druga +1
     czas      +1,5 rok z przeszlosci, okres, "na dekade", "od 1990"
     zmiana    +2   wzrost/spadek, rekord, porownanie ("szybciej niz")
     miejsce   +1   kraj, kontynent, swiat, Arktyka, Mars...
     przyszlosc -4 (prognozy, "bedzie", "do 2050") / rok z przyszlosci -5
     przyczyna -1,5, definicja -3, pytanie -2, odlegla przeszlosc -3
   Jezyki slownika: PL, EN, DE, FR, ES, IT, PT, NL (wartosci liczbowe i
   jednostki dzialaja w kazdym jezyku). */
"use strict";

var CV = globalThis.CV || (globalThis.CV = {});

(function () {
  const CUR_YEAR = new Date().getFullYear();

  /** male litery, bez diakrytykow (ł->l, ß->ss), º->°, indeksy dolne -> cyfry */
  function fold(s) {
    return s.toLowerCase()
      .replace(/\s+/g, " ")            // twarde spacje (&nbsp;) z portali -> zwykle
      .replace(/ł/g, "l").replace(/ß/g, "ss").replace(/º/g, "°")
      .replace(/₂/g, "2").replace(/₄/g, "4")
      .normalize("NFD").replace(/[̀-ͯ]/g, "");
  }
  const R = (src) => new RegExp(src);

  // --- mierzalne wielkosci (co da sie sprawdzic w danych)
  const VAR = [
    // temperatura (rzeczownik) w roznych jezykach
    R("\\btemperatur|\\btemperatur[ae]|\\btemperature|\\btemperaturas?\\b|\\btemperaturen\\b|\\btemperatuur"),
    // ocieplanie / ogrzewanie sie jako zmiana temperatury
    R("\\bociepl|\\bogrzew|\\bnagrzew|\\bcieplej|\\bcieplejsz|\\bgoretsz|\\bchlodniejsz|\\bzimniejsz"),
    R("\\bwarm(ing|er|est|ed|s)?\\b|\\bhotter\\b|\\bhottest\\b|\\bcolder\\b"),
    R("\\berwarm|\\bwarmer\\b|\\bwarmste|\\bwarmsten|\\bkalter\\b|\\btemperaturplus|\\btemperaturanstieg"),
    R("\\brechauff|\\bplus chaude?s?\\b|\\bplus froide?s?\\b"),
    R("\\bcalentamiento|\\bcalid[oa]s?\\b|\\bmas calid|\\bcaluros"),
    R("\\briscaldament|\\bpiu cald|\\bsurriscald|\\bcaldissim"),
    R("\\baquecimento|\\bopwarming"),
    R("\\banomali"),
    // poziom morza
    R("\\bpoziom\\w* (morz|ocean|baltyk|wod\\w* w (morz|baltyk))|\\bsea[- ]level|\\bmeeresspiegel|\\bniveau (de la|des) mer|\\bnivel (del|medio del) mar|\\blivello del mare|\\bzeespiegel"),
    // lod morski / lodowce / pokrywa lodowa
    R("\\blod(u|em)? morsk|\\blodu morskiego|\\bsea ice|\\bice extent|\\bmeereis|\\bbanquise|\\bhielo marino|\\bghiaccio marino|\\blodowc|\\bglacier|\\bgletscher|\\bglaciar|\\bghiacciai|\\bice sheet|\\blad(olod|olodu)|\\bgrenlandi"),
    // gazy cieplarniane / emisje
    R("\\bco2\\b|\\bdwutlen\\w* wegla|\\bcarbon dioxide|\\bkohlendioxid|\\bdioxyde de carbone|\\bdioxido de carbono|\\banidride carbonica|\\bmetan|\\bmethane|\\bch4\\b|\\bn2o\\b|\\bppm\\b|\\bppb\\b"),
    R("\\bemisj|\\bemission|\\bemisi[oo]n|\\bemissioni|\\bemissoes|\\buitstoot|\\bgazow cieplarnian|\\bgreenhouse gas|\\btreibhausgas|\\bgaz a effet de serre|\\bgases de efecto invernadero|\\bgas serra"),
    // opady / susza
    R("\\bopad(y|ow|ami)?\\b|\\bsum\\w* opad|\\bprecipitation|\\brainfall|\\bniederschlag|\\bprecipitacion|\\bprecipitazion|\\blluvia|\\bpiogg|\\bsusz[ay]|\\bdrought|\\bdurre|\\bsecheresse|\\bsequia|\\bsiccita"),
    // temperatura wody / oceanu
    R("\\bsst\\b|\\bsea surface|\\bocean heat|\\bmeerestemperatur|\\btemperature de (la|l')? ?mer|\\bmari italiani|\\bmar(i|es)? (piu|mas) cald"),
  ];
  // planety: wielkosc tylko razem z temperatura/cisnieniem/grawitacja
  const PLANET = R("\\bmars|\\bmarsjan|\\bmartian|\\bwenus|\\bvenus\\b|\\bjowisz|\\bjupiter|\\bmerkur|\\bmercury|\\bsaturn|\\bplanet");
  const PLANET_VAR = R("temperat|\\bgrad|degre|degree|stopn|°|cisnien|pressure|grawitac|gravity|\\bcold|\\bzimn|\\bfroid|\\bfrio|\\bfredd");

  // --- wartosci z jednostkami (dzialaja w kazdym jezyku)
  const VALUE = [
    R("[-+−–]?\\d+(?:[.,]\\d+)?\\s?(?:°\\s?[cf]\\b|°|stopn|st\\.\\s?c|grad\\b|grad celsius|degr|grados|gradi|graus|kelvin)"),
    R("\\b\\d+(?:[.,]\\d+)?c\\b"),                 // "1.44C" (zapis anglojezyczny)
    R("\\d+(?:[.,]\\d+)?\\s?(?:ppm|ppb)\\b"),
    R("\\d+(?:[.,]\\d+)?\\s?(?:mm|cm|km2|km²|mln km|millimet|zentimet|centimet)"),
    R("\\d+(?:[.,]\\d+)?\\s?(?:%|proc|prozent|pour ?cent|por ciento|per cento|percent)"),
    R("\\d+(?:[.,]\\d+)?\\s?(?:mld|mln|miliard|milion|billion|million|milliard|millones|miliardi)\\w*\\s(?:ton|t\\b|tonnes|toneladas|tonnellate)"),
    R("\\b\\d+(?:[.,]\\d+)?\\s?(?:gt|mt)\\b|\\bzettaj|\\bzj\\b"),
    R("\\b\\d+(?:[.,]\\d+)?\\s?(?:mm|cm)\\s?(?:/|na |per |pro |par |por |al )\\s?(?:rok|year|jahr|an|ano|anno)"),
    R("\\b(?:dwukrotnie|trzykrotnie|podwoi|doubled|tripled|verdoppelt|double|duplicado|raddoppiat)"),
  ];
  // --- odniesienia czasowe (przeszlosc/terazniejszosc)
  const TIME = [
    R("\\b(?:od|since|seit|depuis|desde|dal|dalla|sinds)\\s(?:lat |roku |the |den |les |los |gli |l'|el )?(?:18|19|20)\\d{2}"),
    R("\\b(?:od|since|seit|depuis|desde|dal)\\s(?:lat |the |den |les |los |gli |los anos )?(?:\\d0\\.?|\\d0s|\\d0er|60|70|80|90)"),
    R("\\b(?:na|per|pro|par|por|al|a)\\s(?:dekad|decad|jahrzehnt|decenni|decennio)"),
    R("\\b(?:w ciagu|przez|over the (?:past|last)|in den letzten|au cours des|en los ultimos|negli ultimi)\\s(?:ostatnich |ostatnie )?\\d+"),
    R("\\b(?:18|19|20)\\d{2}\\s?[-–]\\s?(?:18|19|20)?\\d{2}\\b"),
    R("\\bpre-?industri|\\bprzedindustr|\\bprzedprzemysl|\\bvorindustri|\\bpreindustri|\\bpre-?industri"),
    R("\\b(?:two|three|four|five|six|seven|eight|nine|ten|several|dwoch|trzech|czterech|pieciu|kilku|kilkunastu|zwei|drei|vier|funf|deux|trois|quatre|cinq|dos|tres|cuatro|cinco|due|tre|quattro|cinque)\\s(?:decades|years|dekad|lat|jahrzehnten?|jahren|decennies|annees|decadas|anos|decenni|anni)"),
    R("\\b(?:w|in|im jahr|en|nel|em|anno)\\s(?:roku\\s)?(?:18|19|20)\\d{2}(?:\\s(?:roku|r\\.))?(?!\\d|[.,]\\d)"),
    R("\\bw (?:ostatnich|kolejnych) dekad|\\bin (?:recent|the last) decades|\\bin den letzten jahrzehnten|\\bces dernieres decennies"),
  ];
  // --- zmiana / porownanie / rekord
  const CHANGE = [
    R("\\bwzr(os|asta|osl|osla|osly|osn)|\\brosn(ie|a|ac)|\\bzwieksz|\\bspad(a|l|la|ly|ek|nie)\\b|\\bzmal|\\bzmniejsz|\\bmalej|\\bpodnosi|\\bpodni(osl|esie)"),
    R("\\brekord|\\bnajciepl|\\bnajgor|\\bnajzimn|\\bnajwyzsz|\\bnajnizsz|\\bnajsuch|\\bcoraz\\b|\\bprzyspiesz|\\bszybciej niz|\\bwolniej niz|\\bwiecej niz|\\bmniej niz|\\bwyzsz\\w* (niz|od)|\\bnizsz\\w* (niz|od)|\\bstale\\b|\\bwciaz\\b|\\btopni|\\bkurcz"),
    R("\\brise[sn]?\\b|\\brisen\\b|\\brising\\b|\\brose\\b|\\bincreas|\\bdecreas|\\bdeclin|\\bdropp|\\bfell\\b|\\brecord|\\bfaster than|\\bslower than|\\bmore than|\\babove|\\bbelow|\\bshrink|\\bmelt|\\baccelerat|\\blowest|\\bhighest"),
    R("\\bgestiegen|\\bsteig|\\banstieg|\\bzugenommen|\\bgesunken|\\brekord|\\bschneller als|\\bbeschleunig|\\bhoher als|\\buber dem mittel"),
    R("\\bhausse|\\baugment|\\bbaisse|\\bdiminu|\\brecord|\\bplus vite que|\\bacceler|\\bau-dessus|\\bsuperieur"),
    R("\\baument|\\bsubid|\\bha subido|\\bsube|\\bdescen|\\bdisminu|\\brecord|\\bmas rapido que|\\bacelera|\\bpor encima"),
    R("\\baument|\\bcresc|\\bdiminu|\\bcalo\\b|\\brecord|\\bpiu veloce|\\baccelera|\\bsopra la media|\\bsuperiore"),
    R("\\bstijg|\\bgestegen|\\bdaal|\\brecord|\\bsneller dan"),
    // superlatywy = rekord ("najcieplejszy rok", "das warmste Jahr", "la plus chaude")
    R("\\bwarmest|\\bhottest|\\bcoldest|\\bwettest|\\bdriest|\\bwarmste|\\bkalteste|\\bheisseste|\\bla plus chaude|\\ble plus chaud|\\bmas calid|\\bmas caluros|\\bpiu cald|\\bmais quente|\\bwarmste"),
  ];
  const TEMP_VALUE = R("[-+−–]?\\d+(?:[.,]\\d+)?\\s?(?:°\\s?[cf]\\b|st\\.\\s?c\\b|grad celsius|degres? celsius|grados? celsius|gradi celsius)");
  const PLACE = R("\\bpolsk|\\bpolsce\\b|\\beurop|\\bswiat|\\bglobal|\\bworld|\\bwelt|\\bmonde|\\bmundo|\\bmondo|\\bziemi|\\bearth\\b|\\berde\\b|\\bterre\\b|\\btierra\\b|\\bterra\\b|\\bdeutschland|\\bfrance|\\bfranc|\\bespan|\\bspain|\\bital|\\bpeninsula|\\barkty|\\barctic|\\barktis|\\barctique|\\bartic|\\bantarkty|\\bantarctic|\\bantarktis|\\bbaltyk|\\bbaltic|\\bostsee|\\bmars|\\bwarszaw|\\bkrakow|\\bwroclaw|\\bgdansk|\\bpoznan|\\blodz|\\bkraj|\\bcountry|\\bpays\\b|\\bpais\\b|\\bpaese|\\bland\\b|\\bocean|\\bmorz|\\bmeer|\\bmer\\b|\\bmar(e|i)?\\b");

  // --- kary
  const FUTURE = R([
    "\\bbedzie\\b|\\bbeda\\b|\\bbedziemy\\b|\\bbedziecie\\b|\\bwzrosnie|\\bwzrosna|\\bspadnie|\\bspadna|\\bzwiekszy sie|\\bzmniejszy sie|\\bspowoduj|\\bprzekroczy\\b|\\bosiagnie\\b|\\bw gre wchodzi|\\bmoze byc|\\bmoga (byc|sie|siegnac|wzrosnac)|\\bprognoz|\\bprzewid|\\bscenariusz|\\bdo konca (wieku|xxi)|\\bw przyszlosci|\\bza \\d+(-\\d+)? lat|\\bspodziewa|\\bzakład",
    "\\bwill\\b|\\bwould\\b|\\bcould\\b|\\bmight\\b|\\bprojected|\\bprojection|\\bforecast|\\bpredict|\\bexpected to|\\blikely to|\\bby (20[3-9]\\d|21\\d\\d)|\\bscenario",
    "\\bwird\\b|\\bwerden\\b|\\bkonnte\\b|\\bprognose|\\bbis (20[3-9]\\d|21\\d\\d)|\\bszenario|\\bvoraussicht",
    "\\bsera\\b|\\bseront\\b|\\bpourrai|\\bprevision|\\bd'ici (20[3-9]\\d|21\\d\\d|la fin)|\\bscenario",
    "\\bsera\\b|\\bseran\\b|\\bpodria|\\bprevision|\\bpara (20[3-9]\\d|21\\d\\d)|\\bescenario",
    "\\bsara\\b|\\bsaranno\\b|\\bpotrebbe|\\bprevision|\\bentro il (20[3-9]\\d|21\\d\\d)|\\bdovrebbe",
  ].join("|"));
  const CAUSE = R("\\bprzyczyn|\\bpowodem\\b|\\bpowoduje|\\bsprawia, ze|\\bprowadzi do|\\bza sprawa|\\bwynikiem\\b|\\bleads? to\\b|\\bfuhrt zu|\\bconduit a|\\bconduce a|\\bporta a\\b|\\bdlaczego|\\bponiewaz|\\bodpowiada (kilka|szereg)|\\bwynika (to )?z|\\bbecause\\b|\\bdriven by|\\bcaused by|\\bdue to\\b|\\bweil\\b|\\bwegen\\b|\\bangetrieben|\\bparce que|\\ba cause|\\bporque\\b|\\bdebido a|\\bperche\\b|\\ba causa");
  const DEFINITION = R("\\bto takie,? w ktorych|\\brozumie(c|my) bedziemy|\\bdefiniowan|\\bdefiniuje|\\bis defined|\\bdefined as|\\bmowimy,? kiedy|\\bnazywa sie|\\bwird definiert|\\bse definit|\\bse define|\\bsi definisce|\\bokres ten okresla");
  const DEEP_PAST = R("\\bw przeszlosci\\b|\\bmiliard\\w* lat|\\bmilion\\w* lat|\\bin the past\\b|\\bbillion years|\\bmillion years|\\bonce been|\\bmay have been|\\bmilliard\\w* d'annees|\\bhace millones|\\bmilioni di anni|\\bepoki lodowc|\\bice age");
  // opis rysunku / wykresu / tabeli - to nie jest teza
  const FIGURE = R("\\b(?:the )?(?:figure|chart|graph|map|table) (?:below|above)|\\bwykres(?:ie)? (?:ponizej|powyzej|pokazuje)|\\bna (?:wykresie|mapie|rysunku|ilustracji)|\\bilustracja \\d|\\brysunek \\d|\\bmapa pokazuje|\\bmapk|\\bz zalaczon|\\babbildung|\\bgrafik (?:unten|oben)|\\bgraphique ci-dessous|\\bgrafico|\\bgrafica|\\bfuente:|\\bzrodlo:|\\bsource:|\\bquelle:|\\bfonte:|\\bcredit:");
  // atrybucja przyczyn ("CO2 odpowiada za 42% ocieplenia") - danych nie sprawdzimy
  const ATTRIBUTION = R("\\baccounting for|\\bcontribut|\\bresponsible for|\\battribut|\\bodpowiada za|\\bprzyczynia sie|\\bprzypisuje sie|\\bbeitrag zu|\\bverantwortlich|\\bresponsable de|\\bcontribu");
  const JUNK = R("cookie|ciasteczk|zaloguj|subskryb|newsletter|reklama|sponsor|czytaj (tez|takze|wiecej)|zobacz (tez|takze)|udostepnij|komentarz|polub nas|regulamin|prenumerat|\\bcopyright\\b|wszelkie prawa|bon plan|guide d'achat|\\btags :|abonn|kaffee|spende|suscrib|iscriviti|read more|related:|ultimi articoli|free to read|nonprofit|donat|wesprzyj|wplac|subscribe|sign up|zapisz sie");

  const RECORD = R("\\brekord|\\brecord|\\bnajciepl|\\bwarmest|\\bhottest|\\bwarmste|\\bla plus chaude|\\bmas calid|\\bpiu cald|\\blowest\\b|\\bhighest\\b|\\bnajnizsz|\\bnajwyzsz|\\bw historii pomiarow|\\bon record\\b|\\bseit beginn der|\\bdepuis le debut des|\\bdesde que hay registros");
  // kategoria wielkosci - zaznaczenia maja obejmowac rozne tematy artykulu
  const CATS = [
    ["sea_level", R("\\bpoziom\\w* (morz|ocean|baltyk)|sea[- ]level|meeresspiegel|niveau (de la|des) mer|nivel (del|medio del) mar|livello del mare|zeespiegel")],
    ["ice", R("lod(u|em)? morsk|lodu morskiego|sea ice|ice extent|meereis|banquise|hielo marino|ghiaccio marino|lodowc|glacier|gletscher|glaciar|ghiacciai|ice sheet|ladolod")],
    ["gases", R("\\bco2\\b|dwutlen|carbon dioxide|kohlendioxid|dioxyde de carbone|dioxido de carbono|anidride|metan|methane|ppm\\b|ppb\\b")],
    ["emissions", R("emisj|emission|emisi|uitstoot|treibhausgas")],
    ["precip", R("\\bopad|precipitation|rainfall|niederschlag|precipitacion|precipitazion|lluvia|piogg|susz|drought|durre|secheresse|sequia|siccita")],
    ["ocean", R("\\bsst\\b|sea surface|ocean heat|meerestemperatur|mari italiani|\\bmari\\b|\\bocean")],
    ["planet", R("\\bmars|martian|wenus|venus|jowisz|jupiter|planet")],
  ];
  function category(t) {
    for (const [name, re] of CATS) if (re.test(t)) return name;
    return "temperature";
  }

  function count(rules, t, cap) {
    let n = 0;
    for (const r of rules) {
      if (r.test(t)) { n++; if (n >= cap) break; }
    }
    return n;
  }

  function futureYear(t) {
    const ys = t.match(/\b(20\d{2}|21\d{2})\b/g) || [];
    return ys.some((y) => Number(y) > CUR_YEAR);
  }

  /** Punktacja zdania (score 0 = to nie jest teza do sprawdzenia). */
  function scoreSentence(sentence) {
    const words = sentence.trim().split(/\s+/).length;
    if (words < 6 || words > 70) return { score: 0 };
    const t = fold(sentence);
    if (JUNK.test(t)) return { score: 0 };
    if (ATTRIBUTION.test(t)) return { score: 0 };   // atrybucja przyczyn - nie do sprawdzenia w danych
    let v = count(VAR, t, 2);
    const cat = category(t);
    const planet = PLANET.test(t);
    if (!v && planet && PLANET_VAR.test(t)) v = 1;
    if (!v && TEMP_VALUE.test(t)) v = 1;     // "+0,6 °C" to temperatura
    if (!v) return { score: 0 };
    const val = count(VALUE, t, 2);
    const time = count(TIME, t, 1);
    const ch = count(CHANGE, t, 1);
    if (!val && !ch) return { score: 0 };
    const place = PLACE.test(t) ? 1 : 0;
    let score = 3 + (v > 1 ? 0.5 : 0) + (val ? 3 + (val > 1 ? 1 : 0) : 0) + time * 1.5 + ch * 2 + place;
    // 4. sama wartosc bez okresu i bez zmiany na Ziemi = odczyt pogody, nie teza
    if (val && !time && !ch && !planet) score -= 1.5;
    if (RECORD.test(t)) score += 1;              // rekord / "najwyzszy w historii" = mocna teza
    if (FUTURE.test(t)) score -= 4;
    if (futureYear(t)) score -= 5;
    if (CAUSE.test(t)) score -= 1.5;
    if (DEFINITION.test(t)) score -= 3;
    if (FIGURE.test(t)) score -= 3;

    if (DEEP_PAST.test(t)) score -= 3;
    if (/\?\s*$/.test(sentence.trim())) score -= 2;
    return { score, v, val, time, ch, place, cat };
  }

  // skroty, po ktorych kropka nie konczy zdania (PL, EN, DE, FR, ES, IT)
  const ABBREV = new Set(["r", "ok", "np", "tys", "mln", "mld", "prof", "dr", "tzw", "ul", "sw", "godz",
    "ang", "wg", "nr", "im", "in", "tj", "itd", "itp", "pt", "proc", "st", "min", "max", "ds", "ps",
    "e.g", "i.e", "vs", "mr", "mrs", "ms", "no", "fig", "approx", "etc", "jr", "sr", "u.a", "z.b", "bzw",
    "ca", "inkl", "evtl", "mio", "mrd", "jh", "jhd", "env", "av", "apr", "j.-c", "mme", "sra", "sr", "aprox",
    "pag", "ecc", "sig", "dott", "ing"]);

  /** Podzial tekstu bloku na zdania z pozycjami [start, end). */
  function splitSentences(text) {
    const out = [];
    const re = /[.!?…]+["”»)]?(?=\s+["„«“(]?[A-ZĄĆĘŁŃÓŚŹŻÀ-ÖØ-Þ0-9–-])/g;
    let start = 0;
    let m;
    while ((m = re.exec(text))) {
      const end = m.index + m[0].length;
      const before = text.slice(start, m.index);
      const lastWord = (before.match(/([\p{L}.]+)$/u) || ["", ""])[1].toLowerCase().replace(/^\./, "");
      // skrot (np. "w 2020 r.", "z.B.") albo inicjal ("J. Kowalski") - nie dziel
      const unitLetter = /^[cfk]$/i.test(lastWord) && /(?:st\.|°|\d)\s?[cfk]$/i.test(before);
      if (ABBREV.has(lastWord) || (/^\p{L}$/u.test(lastWord) && !unitLetter)) continue;
      // "st. C" / "40 st. C" - stopnie, nie koniec zdania
      if (/\bst$/i.test(before) && /^\.\s+C\b/.test(text.slice(m.index))) continue;
      push(start, end);
      start = end;
    }
    push(start, text.length);
    return out;

    function push(s, e) {
      while (s < e && /\s/.test(text[s])) s++;
      while (e > s && /\s/.test(text[e - 1])) e--;
      if (e - s >= 25) out.push({ start: s, end: e, text: text.slice(s, e) });
    }
  }

  /** Teza gotowa do wyslania: bez przypisow, wielokrotnych spacji, max 600 znakow. */
  function cleanThesis(s) {
    return s.replace(/\[\d+\]/g, "").replace(/\s+/g, " ").replace(/^[-–—•*\s]+/, "").trim().slice(0, 600);
  }

  /**
   * Wykrywa tezy w liscie blokow tekstu.
   * blocks: [{id, text}] -> [{blockId, start, end, text, score}] (najlepsze, bez duplikatow)
   */
  function findClaims(blocks, { threshold = 6, max = 6 } = {}) {
    // dluzsze artykuly moga miec wiecej tez: +1 na kazde 700 slow ponad 1500, max 2x
    const words = blocks.reduce((n, b) => n + b.text.split(/\s+/).length, 0);
    const limit = Math.min(max * 2, max + Math.max(0, Math.floor((words - 1500) / 700)));
    const found = [];
    for (const b of blocks) {
      for (const s of splitSentences(b.text)) {
        const sc = scoreSentence(s.text);
        if (sc.score >= threshold) {
          found.push({ blockId: b.id, start: s.start, end: s.end, text: cleanThesis(s.text), score: sc.score, cat: sc.cat });
        }
      }
    }
    found.sort((a, b) => b.score - a.score || a.blockId - b.blockId);
    const seen = [];
    const picked = [];
    const dup = (f) => {
      const key = fold(f.text);
      // ta sama teza powtorzona (lead + tresc) - zostaw jedna
      return seen.some((k) => k === key || (k.length > 40 && (k.includes(key.slice(0, 60)) || key.includes(k.slice(0, 60)))));
    };
    const take = (f) => { seen.push(fold(f.text)); picked.push(f); };
    // 1) najlepsza teza z kazdej kategorii (temperatura, morze, lod, gazy...)
    const cats = new Set();
    for (const f of found) {
      if (picked.length >= limit) break;
      if (cats.has(f.cat) || dup(f)) continue;
      cats.add(f.cat);
      take(f);
    }
    // 2) reszta wg punktacji
    for (const f of found) {
      if (picked.length >= limit) break;
      if (picked.includes(f) || dup(f)) continue;
      take(f);
    }
    return picked.sort((a, b) => b.score - a.score);
  }

  CV.claims = { scoreSentence, splitSentences, findClaims, cleanThesis, fold };
})();

if (typeof module !== "undefined") module.exports = CV.claims;
