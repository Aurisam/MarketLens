# MarketLens

MarketLens – internetinė akcijų, ETF ir kriptovaliutų stebėjimo sistema. Ji pateikia kainų istoriją, techninius rodiklius ir pagal juos sudarytą rinkos krypties vertinimą.

## Funkcijos

- Akcijų, ETF ir kriptovaliutų instrumentų sąrašas.
- Tiesioginiai Binance ir Hyperliquid kainų srautai bei Yahoo kainų patikra kas 45 sekundes.
- Paskutinė išsaugota kaina rodoma, kol gaunami nauji duomenys; ryšio sutrikimai pažymimi kortelėje.
- Kainos pokyčio paryškinimas spalva ir vietiniu laiku rodomas kainos gavimo laikas.
- Žvakiniai kainos grafikai ir RSI grafikai su 1h, 4h ir 1d intervalais.
- Automatinė atidaryto puslapio duomenų patikra kas minutę, išsaugant pasirinktą intervalą.
- Laiko rodymas pagal vartotojo naršyklės laiko juostą.
- SMA 20 ir SMA 50 slankieji vidurkiai.
- RSI 14 rodiklis ir jo būsenos vertinimas.
- Kainos krypties, atskirų intervalų ir bendras techninis signalas.
- Duomenų patikros laikas ir vėluojančio atnaujinimo žymėjimas.
- Trijų skaitmenų po kablelio tikslumas užuominose, rodomose užvedus ant žvakės.
- Sujungti kainos ir RSI grafikai su viena matoma laiko ašimi.
- Sinchronizuotas grafikų priartinimas, atitolinimas, slinkimas ir pradinio vaizdo atkūrimas.
- Tamsi ir šviesi tema su naršyklėje išsaugomu pasirinkimu.
- Instrumentų valdymas per Django administravimo sąsają.

## Duomenų šaltiniai

| Šaltinis | Duomenys |
| --- | --- |
| Binance | Kriptovaliutų kainos ir žvakės |
| Hyperliquid | Kriptovaliutų kainos ir žvakės |
| Yahoo Finance | Akcijų ir ETF kainos bei kainų istorija |

Yahoo Finance 4h žvakės sudaromos iš valandinių žvakių, atskiriant prekybos sesijas. Paskutinė sesijos žvakė gali apimti trumpesnį laikotarpį. Pradinė išsaugota akcijų ir ETF kaina gaunama iš valandinės žvakės. Atidarytame puslapyje atskirai tikrinama naujausia Yahoo `regularMarketPrice` reikšmė su jos `regularMarketTime` laiku. Dažnesnė patikra negarantuoja realaus laiko biržos duomenų; ne prekybos metu kainos laikas gali likti ankstesnės sesijos.

## Veikimo principas

Periodinė užduotis paleidžia Django komandą `update_market_data`. Komanda gauna rinkos duomenis iš išorinių šaltinių ir išsaugo juos duomenų bazėje.

```text
Periodinė užduotis → rinkos API → duomenų bazė
Naršyklė → Django → duomenų bazė → rodiklių skaičiavimas → puslapis
Binance / Hyperliquid WebSocket → naršyklės kainų laukeliai
Naršyklė → Django /prices/ → Yahoo API ir trumpas kešas → kainų laukeliai
```

Puslapis kiekvienam instrumentui perskaito po 100 naujausių kiekvieno intervalo žvakių. Tas pats sąrašas naudojamas grafikui, kainos krypčiai, SMA ir RSI apskaičiuoti. Pradinio puslapio ir grafikų atnaujinimo užklausos apdorojamos naudojant DB duomenis.

Instrumento, intervalo ir žvakės pradžios laiko derinys yra unikalus. Pakartotinis atnaujinimas pataiso esamas žvakes ir įrašo naujas. Ankstesnė istorija išlieka. Nepavykus gauti naujų duomenų, rodomi paskutiniai išsaugoti įrašai.

Grafikų X ašyje pateikiamas žvakės pradžios laikas vartotojo naršyklės laiko juostoje. Taip pat vietiniu laiku rodomi duomenų patikros laikai. Laiko juosta nustatoma automatiškai, naudojant naršyklės Intl API. Duomenų patikros laikas saugomas atskirai. Praėjus daugiau nei 30 minučių nuo paskutinio sėkmingo pilno atnaujinimo, puslapyje parodoma vėlavimo žyma.

Atidarytas puslapis kas minutę gauna atnaujintas instrumentų korteles per Django maršrutą `/data/`. Kainų grafikai, RSI ir signalai atnaujinami neperkraunant viso puslapio. Pasirinktas instrumento intervalas ir priartinta grafikų sritis išsaugomi pagal instrumento ID. Nepavykus užklausai, lieka ankstesni grafikai ir kitą minutę bandoma dar kartą. Kol naršyklės kortelė paslėpta, periodinės užklausos sustabdomos.

Puslapio atnaujinimas ir rinkos duomenų surinkimas yra atskiri procesai. Puslapis tikrina DB kas minutę, o GitHub Actions rinkos duomenų atnaujinimas suplanuotas kas 15 minučių.

Kortelių kainas valdo atskiras `prices.js` modulis. Vienas bendras Binance ryšys prenumeruoja instrumentų `miniTicker` srautus, o Hyperliquid `allMids` pateikia vidurines kainas. Binance kainos nurodomos USDT. Nutrūkę ryšiai automatiškai atkuriami, naudojant iki 30 sekundžių didėjantį laukimą. Paslėpus naršyklės kortelę kainų ryšiai ir užklausos sustabdomi, grįžus atnaujinami.

Yahoo kainų JSON maršrutas `/prices/` tikrinamas kas 45 sekundes; sėkmingi atsakymai Django procese laikomi keše 30 sekundžių. Nesėkmės atveju lieka ankstesnė kaina su klaidos žyma. Kainos laikas ir užklausos patikros laikas rodomi atskirai. Naujos kortelių kainos į DB nerašomos ir istorinių žvakių ar indikatorių nekeičia. Minutinis kortelių HTML atnaujinimas išsaugo naujausias srauto kainas naršyklėje.

Grafikų priartinimą ir slinkimą valdo Chart.js zoom papildinys. Priartinimo mygtukai keičia kainos ir RSI grafikų laiko ašį. Temos pasirinkimas saugomas naršyklės localStorage. Pirmą kartą tema parenkama pagal naršyklės sistemos spalvų nuostatą. Pasikeitus temai, pritaikomos ir grafikų spalvos.

## Duomenų modeliai

**Instrument** saugo instrumento pavadinimą, simbolį, tipą, duomenų šaltinį, paskutinę kainą ir patikros laikus.

**Candle** saugo ryšį su instrumentu, intervalą, pradžios laiką bei atidarymo, didžiausią, mažiausią ir uždarymo kainas. Unikalumo apribojimas apsaugo nuo pasikartojančių žvakių.

## Technologijos

| Dalis | Technologijos |
| --- | --- |
| Serverio logika | Python, Django |
| Duomenų bazė | PostgreSQL, vietiniam darbui SQLite |
| Sąsaja | Django šablonai, Bootstrap, JavaScript |
| Grafikai | Chart.js, chartjs-chart-financial, Luxon datos adapteris |
| API užklausos | Requests |
| Serverio paleidimas ir statiniai failai | Gunicorn, WhiteNoise |
| Paruošta talpinimo konfigūracija | Render ir Neon |
| Paruoštas atnaujinimo tvarkaraštis | GitHub Actions, kas 15 minučių |

Django ORM naudojamas duomenų skaitymui ir rašymui. Duomenų bazės struktūros pakeitimai aprašyti migracijose. Serverio aplinkos kintamieji nustato DB prisijungimą ir produkcinius nustatymus. Render suteiktas domenas įtraukiamas automatiškai.

## Patikros

Automatiniai testai tikrina API atsakymų apdorojimą, žvakių formatą, duomenų atnaujinimą be pasikartojimų, ankstesnių duomenų išsaugojimą po klaidos ir puslapio veikimą iš DB. Atskiri kainų testai tikrina Yahoo metaduomenis, kešą ir JSON maršruto veikimą nekeičiant DB istorijos.

```sh
python config/manage.py test dashboard
```
