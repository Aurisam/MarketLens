# MarketLens

MarketLens – internetinė akcijų, ETF ir kriptovaliutų stebėjimo sistema. Ji pateikia kainų istoriją, techninius rodiklius ir pagal juos sudarytą rinkos krypties vertinimą.

## Funkcijos

- Akcijų, ETF ir kriptovaliutų instrumentų sąrašas.
- Paskutinė išsaugota instrumento kaina.
- Žvakiniai kainos grafikai ir RSI grafikai su 1h, 4h ir 1d intervalais.
- Automatinė atidaryto puslapio duomenų patikra kas minutę, išsaugant pasirinktą intervalą.
- Laiko rodymas pagal vartotojo naršyklės laiko juostą.
- SMA 20 ir SMA 50 slankieji vidurkiai.
- RSI 14 rodiklis ir jo būsenos vertinimas.
- Kainos krypties, atskirų intervalų ir bendras techninis signalas.
- Duomenų patikros laikas ir vėluojančio atnaujinimo žymėjimas.
- Instrumentų valdymas per Django administravimo sąsają.

## Duomenų šaltiniai

| Šaltinis | Duomenys |
| --- | --- |
| Binance | Kriptovaliutų kainos ir žvakės |
| Hyperliquid | Kriptovaliutų kainos ir žvakės |
| Yahoo Finance | Akcijų ir ETF kainų istorija |

Yahoo Finance 4h žvakės sudaromos iš valandinių žvakių, atskiriant prekybos sesijas. Paskutinė sesijos žvakė gali apimti trumpesnį laikotarpį. Akcijų ir ETF rodoma kaina gaunama iš paskutinės prieinamos valandinės žvakės uždarymo.

## Veikimo principas

Periodinė užduotis paleidžia Django komandą `update_market_data`. Komanda gauna rinkos duomenis iš išorinių šaltinių ir išsaugo juos duomenų bazėje.

```text
Periodinė užduotis → rinkos API → duomenų bazė
Naršyklė → Django → duomenų bazė → rodiklių skaičiavimas → puslapis
```

Puslapis kiekvienam instrumentui perskaito po 100 naujausių kiekvieno intervalo žvakių. Tas pats sąrašas naudojamas grafikui, kainos krypčiai, SMA ir RSI apskaičiuoti. Lankytojo užklausa apdorojama naudojant DB duomenis.

Instrumento, intervalo ir žvakės pradžios laiko derinys yra unikalus. Pakartotinis atnaujinimas pataiso esamas žvakes ir įrašo naujas. Ankstesnė istorija išlieka. Nepavykus gauti naujų duomenų, rodomi paskutiniai išsaugoti įrašai.

Grafikų X ašyje pateikiamas žvakės pradžios laikas vartotojo naršyklės laiko juostoje. Taip pat vietiniu laiku rodomi duomenų patikros laikai. Laiko juosta nustatoma automatiškai, naudojant naršyklės Intl API. Duomenų patikros laikas saugomas atskirai. Praėjus daugiau nei 30 minučių nuo paskutinio sėkmingo pilno atnaujinimo, puslapyje parodoma vėlavimo žyma.

Atidarytas puslapis kas minutę gauna atnaujintas instrumentų korteles per Django maršrutą `/data/`. Kainų grafikai, RSI ir signalai atnaujinami neperkraunant viso puslapio. Pasirinktas instrumento intervalas išsaugomas pagal instrumento ID. Nepavykus užklausai, lieka ankstesni grafikai ir kitą minutę bandoma dar kartą. Kol naršyklės kortelė paslėpta, periodinės užklausos sustabdomos.

Puslapio atnaujinimas ir rinkos duomenų surinkimas yra atskiri procesai. Puslapis tikrina DB kas minutę, o GitHub Actions rinkos duomenų atnaujinimas suplanuotas kas 15 minučių.

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

Automatiniai testai tikrina API atsakymų apdorojimą, žvakių formatą, duomenų atnaujinimą be pasikartojimų, ankstesnių duomenų išsaugojimą po klaidos ir puslapio veikimą iš DB.

```sh
python config/manage.py test dashboard
```
