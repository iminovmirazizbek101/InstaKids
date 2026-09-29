# StartApp — Windows xatosini tuzatish

Sizdagi xato `Django 6.1` bilan eski `djangorestframework 3.16.1` birga o‘rnatilgani sababli chiqadi. DRF 3.18 Django 6.1 bilan mos va `cc_delim_re` muammosini tuzatadi.

## 1. Eski virtual muhitni o‘chiring
PowerShell:

```powershell
deactivate
Remove-Item -Recurse -Force .muhit
```

Agar `deactivate` xato bersa, uni tashlab keyingi buyruqni bajaring.

## 2. Yangi muhit yarating

```powershell
python -m venv .muhit
.\.muhit\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 3. Ma'lumotlar bazasi

```powershell
python manage.py migrate
```

## 4. Gmail OAuth
Google Cloud'dan Desktop app OAuth `credentials.json` faylini loyiha ildiziga qo‘ying, so‘ng:

```powershell
python manage.py gmail_auth
```

Brauzerda `iminovmirazizbek101@gmail.com` akkauntini tanlab ruxsat bering. `token.json` avtomatik yaratiladi.

## 5. Server

```powershell
python manage.py runserver
```

## Muhim

`requirements.txt`ni o‘zgartirishning o‘zi eski `.muhit`ni tuzatmaydi. Shuning uchun yuqoridagi **.muhitni o‘chirish va qayta yaratish** bosqichi kerak.
