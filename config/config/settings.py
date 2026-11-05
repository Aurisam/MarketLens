"""Django nustatymai: aplinka, duomenų bazė, saugumas, šablonai ir statiniai failai."""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

# Bazinis config katalogas naudojamas SQLite ir surinktų statinių failų keliams.
BASE_DIR = Path(__file__).resolve().parent.parent


# Vietinės numatytos reikšmės pakeičiamos serverio aplinkos kintamaisiais.
# See https://docs.djangoproject.com/en/6.1/howto/deployment/checklist/

# Django pasirašymo raktas serveryje perduodamas per aplinką, o ne saugomas kode.
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'development-only-marketlens-key')

# Viešame serveryje DEBUG išjungiamas, o numatytas vystymo raktas neleidžiamas.
DEBUG = os.getenv('DJANGO_DEBUG', 'true').lower() == 'true'
if not DEBUG and SECRET_KEY == 'development-only-marketlens-key':
    raise ImproperlyConfigured('Set DJANGO_SECRET_KEY when DJANGO_DEBUG=false.')

# Leidžiami hostai ir CSRF kilmės išskaidomi iš kableliais atskirtų aplinkos reikšmių.
ALLOWED_HOSTS = [host.strip() for host in os.getenv('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',') if host.strip()]
CSRF_TRUSTED_ORIGINS = [origin.strip() for origin in os.getenv('DJANGO_CSRF_TRUSTED_ORIGINS', '').split(',') if origin.strip()]
# Render suteiktas domenas pridedamas automatiškai.
render_hostname = os.getenv('RENDER_EXTERNAL_HOSTNAME')
if render_hostname:
    ALLOWED_HOSTS.append(render_hostname)
    CSRF_TRUSTED_ORIGINS.append(f'https://{render_hostname}')
# Produkcinėje aplinkoje prisijungimo ir CSRF slapukai perduodami tik per HTTPS.
if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = True
    # Tarpinis serveris turi pašalinti kliento pateiktas X-Forwarded-Proto antraštes prieš nustatydamas savąją.
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')


# Django sistemos programėlės ir projekto dashboard programėlė.

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'dashboard',
]

# Užklausų apdorojimo sluoksniai; WhiteNoise aptarnauja CSS ir JavaScript failus.
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

# APP_DIRS leidžia Django rasti dashboard/templates kataloge esančius šablonus.
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# Be DATABASE_URL naudojama vietinė SQLite; serveryje URL parenka PostgreSQL ryšį.
# https://docs.djangoproject.com/en/6.1/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}
if os.getenv('DATABASE_URL'):
    import dj_database_url

    # Ilgai nelaikome ryšių atidarytų; prieš jų pakartotinį naudojimą tikrinama būsena.
    DATABASES['default'] = dj_database_url.config(conn_max_age=0, conn_health_checks=True)


# Django administravimo vartotojų slaptažodžių taisyklės.
# https://docs.djangoproject.com/en/6.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Serverio datos saugomos su laiko juostos informacija; vietinį rodymą atlieka naršyklė.
# https://docs.djangoproject.com/en/6.1/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# collectstatic surenka failus; produkcijoje WhiteNoise juos suspaudžia ir versijuoja pavadinimuose.
# https://docs.djangoproject.com/en/6.1/howto/static-files/

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage' if DEBUG else 'whitenoise.storage.CompressedManifestStaticFilesStorage',
    },
}


# Laiškų turinys šioje konfigūracijoje išvedamas į serverio konsolę.
# https://docs.djangoproject.com/en/6.1/topics/email/#topic-email-configuration

MAILERS = {
    'default': {
        'BACKEND': 'django.core.mail.backends.console.EmailBackend',
    },
}
