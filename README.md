# MarketLens

Django puslapis akcijų, ETF ir kriptovaliutų grafikams bei techniniams rodikliams.

## Kaip keliauja duomenys

1. `python config/manage.py update_market_data` gauna žvakes ir kainas iš Binance, Hyperliquid bei Yahoo Finance.
2. Komanda įrašo žvakes į `Candle`, o paskutinę kainą ir patikros laikus į `Instrument`. Sutampančio instrumento, intervalo ir žvakės pradžios laiko eilutė atnaujinama. Nepavykus API užklausai, ankstesni įrašai išlieka. Komanda grąžina klaidos kodą, kad planuoklis parodytų nepavykusį atnaujinimą.
3. Atidarius puslapį, `views.py` perskaito po 100 naujausių kiekvieno intervalo žvakių iš DB, surikiuoja nuo seniausios ir apskaičiuoja grafiką, trendą, SMA bei RSI. Puslapio atidarymas nesukelia rinkos API užklausų.

Naudojami `1h`, `4h`, `1d` intervalai. Yahoo `4h` žvakės sudaromos iš valandinių žvakių, atskiriant prekybos sesijas. Akcijų bei ETF kaina yra paskutinės prieinamos valandinės žvakės uždarymas. Tai nėra atskiras realaus laiko kainos srautas.

Kiekvienas atnaujinimas gauna naujausių 100 žvakių langą kiekvienam intervalui. DB istorija kaupiasi, senesni įrašai neištrinami. Ilgesnę nei tiekėjo grąžinama istorija pertrauką gali reikėti užpildyti atskirai. Puslapyje rodomas paskutinės sėkmingos pilnos patikros laikas. Po 30 minučių pažymima, kad atnaujinimas vėluoja. Šis laikas rodo patikrą, o žvakės laikas X ašyje rodo rinkos duomenų laiką.

## Paleidimas vietoje

Komandas vykdyk iš projekto šakninio katalogo, aktyvavęs `.venv`. Reikia Python 3.12 arba naujesnio.

```sh
python -m pip install -r requirements.txt
python config/manage.py migrate
python config/manage.py update_market_data
python config/manage.py runserver
```

Esami instrumentai išlieka po migracijos. Tik naujoje tuščioje DB pradinius penkis instrumentus galima įkelti su `python config/manage.py loaddata instruments`. Šio fixture nekrauk į DB su savo pakeistais instrumentais, nes jis naudoja konkrečius ID.

Pirmą atnaujinimą paleidau vietinėje DB. Vėliau atnaujinimo komandą reikia paleisti iš naujo arba suplanuoti. Vien `runserver` duomenų neatnaujina. Naujas instrumentas pradės rodyti duomenis po kito komandos paleidimo.

`.env.example` pateikia aplinkos kintamųjų pavyzdžius. Juos įrašyk į PyCharm paleidimo konfigūraciją arba eksportuok terminale. `.env` failas automatiškai neskaitomas. Jei `DATABASE_URL` nenustatytas, naudojamas vietinis SQLite.

Neon projektas `MarketLens` sukurtas Frankfurte tavo Free organizacijoje. [Atidaryti projektą](https://console.neon.tech/app/projects/summer-bonus-82974220/). Pagrindinė DB yra `marketlens`, šaka `production`. Migracijos pirmiausia patikrintos laikinoje `migration-check` šakoje, kuri automatiškai baigs galioti 2026-11-04 06:30 UTC.

Prisijungimo adresai saugomi vietiniame `.env.neon` faile. Jis ignoruojamas Git ir į saugyklą nekeliamas. `DATABASE_URL` skirtas įprastam darbui per ryšių telkinį, `DATABASE_URL_UNPOOLED` – tiesioginiam migracijų ryšiui. `manage.py migrate` automatiškai pasirenka antrąjį, kai jis nustatytas. Jei norėsi vietinį serverį paleisti su Neon, projekto kataloge atidaryk terminalą ir vykdyk žemiau pateiktas komandas. To terminalo komandos tada dirbs su serverio DB.

```sh
set -a
source .env.neon
set +a
.venv/bin/python config/manage.py runserver
```

## Nemokamas talpinimas

Paruoštas variantas yra Render Free svetainei, Neon Free PostgreSQL bazei ir GitHub Actions periodiniams atnaujinimams. Sąskaitų prijungimas bei publikavimas atliekami tavo paskyrose.

1. Įkelk projektą į GitHub. Viešos saugyklos standartiniai GitHub Actions vykdytojai nemokami, privačios saugyklos turi naudojimo limitus. Į Git neįtraukiami `.env`, vietinė DB ir `.idea`. Duomenų bazės adresą su slaptažodžiu laikyk paskyros paslaptyse.
2. Jei naudoji jau sukurtą projektą, adresai yra tavo vietiniame `.env.neon`. Kuriant naują projektą, nukopijuok pooled ir direct adresus su `sslmode=require`. Nustatyk `DATABASE_URL` ir `DATABASE_URL_UNPOOLED` aplinkos kintamuosius. Komandoms jie parenka Neon bazę vietoje SQLite.
3. Taip nustatęs `DATABASE_URL`, paleisk žemiau pateiktas komandas. Jos paruošia naują serverio DB, įkelia instrumentus ir sukuria administratorių. Pradinį fixture krauk tik į naują tuščią DB.

```sh
python config/manage.py migrate
python config/manage.py loaddata instruments
python config/manage.py createsuperuser
python config/manage.py update_market_data
```

4. Render pasirink **New → Blueprint**, prijunk GitHub saugyklą ir naudok `render.yaml`. Jame parinktas Free planas, bibliotekų įdiegimas, statinių failų paruošimas ir Gunicorn paleidimas. Įrašyk prašomus kintamuosius. `DATABASE_URL` yra Neon adresas. `DJANGO_ALLOWED_HOSTS` yra suteiktas vardas, pavyzdžiui `marketlens-xxxx.onrender.com`, be `https://`. `DJANGO_CSRF_TRUSTED_ORIGINS` yra `https://marketlens-xxxx.onrender.com`. `DJANGO_DEBUG=false` ir atsitiktinis `DJANGO_SECRET_KEY` paruošti konfigūracijoje. Jei adresą sužinosi tik sukūręs paslaugą, tada pataisyk šiuos du kintamuosius ir perleisk diegimą.
   Render taip pat nustatyk `DATABASE_URL_UNPOOLED` tiesioginiam migracijų prisijungimui. Adresų reikšmes iš `.env.neon` nukopijuok be išorinių viengubų kabučių.
5. GitHub saugykloje atidaryk **Settings → Secrets and variables → Actions** ir pridėk `DATABASE_URL` paslaptį su tuo pačiu Neon adresu. Tada **Actions → Update market data → Run workflow** paleisk pirmą patikrą. Workflow turi būti numatytojoje šakoje. Jis suplanuotas kas 15 minučių, UTC laiku minutėmis 7, 22, 37 ir 52. Vienu metu vykdoma viena šio workflow užduotis. Migrations vykdomos diegiant serverį, todėl po modelių keitimo pirma sėkmingai įdiek naują serverio versiją.

Render Free po 15 minučių be lankytojų užmiega, todėl pirmas atidarymas gali užtrukti apie minutę. Vietinė SQLite DB ten neišlieka po perkrovimo. Render Free Postgres galioja tik 30 dienų, todėl šiame variante DB laikoma Neon. [Render nemokamo plano sąlygos](https://render.com/docs/free)

Neon Free turi 1 GB saugyklos ir 100 CU valandų per mėnesį vienam projektui. 15 minučių intervalas parinktas kaip pradinis kompromisas. Stebėk DB naudojimą ir lankytojų apkrovą, kad tilptum į nemokamą planą. [Neon kainodara](https://neon.com/pricing)

GitHub tvarkaraštis gali vėluoti, o viešoje saugykloje po 60 dienų be veiklos suplanuoti workflow išjungiami. Jei duomenys neatnaujinami, patikrink Actions žurnalą. Rinkos API prieinamumas priklauso ir nuo vykdytojo regiono, todėl išorinių API patikrą pakartok jau GitHub aplinkoje. [GitHub tvarkaraščiai](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule), [GitHub Actions naudojimas](https://docs.github.com/en/billing/concepts/product-billing/github-actions)

## Kitas serveris su cron

Komandą gali paleisti ir Linux serverio cron. Pavyzdys kas minutę, pakeitus projekto kelią į tikrąjį. Serveriui turi būti nustatyti DB aplinkos kintamieji. `flock` neleidžia dubliuoti dar nebaigtos užduoties.

```cron
* * * * * flock -n /tmp/marketlens-update.lock /srv/MarketLens/.venv/bin/python /srv/MarketLens/config/manage.py update_market_data >> /srv/MarketLens/market-data.log 2>&1
```

Vienu metu naudok vieną planuoklį. SQLite vietiniam darbui paleisk tik vieną atnaujinimo procesą, PostgreSQL komanda užrakina konkretaus instrumento eilutę atnaujinimo metu. Atnaujinimas vykdomas atskirame procese nuo puslapio.

## Patikros

```sh
python config/manage.py test dashboard
python config/manage.py makemigrations --check --dry-run
python config/manage.py collectstatic --noinput
```
