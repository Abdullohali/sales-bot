"""Uzbek translation of sqladmin's own interface (msgids from sqladmin/translations/admin.pot).

sqladmin ships ru and en catalogs but no Uzbek one; app/admin/i18n.py installs this one.
"""

MESSAGES: dict[str, str] = {
    "List": "Roʻyxat",
    "Details": "Batafsil",
    "Create": "Yaratish",
    "Edit": "Tahrirlash",
    "Delete": "Oʻchirish",
    "Export": "Eksport",
    "Import": "Import",
    "Access": "Kirish",
    "Page": "Sahifa",
    "Permissions": "Ruxsatlar",
    "You are not allowed to grant: %(permissions)s": "Siz bu ruxsatlarni bera olmaysiz: %(permissions)s",
    "New %(name)s": "Yangi: %(name)s",
    "Cancel": "Bekor qilish",
    "Save": "Saqlash",
    "Save and continue editing": "Saqlash va tahrirlashni davom ettirish",
    "Save and add another": "Saqlash va yana qoʻshish",
    "Column": "Ustun",
    "Value": "Qiymat",
    "Go Back": "Orqaga",
    "Edit %(name)s": "Tahrirlash: %(name)s",
    "Save as new": "Yangi sifatida saqlash",
    "Logout": "Chiqish",
    "Language": "Til",
    "Import CSV": "CSV import",
    "You are not authorized to view these records.": "Bu yozuvlarni koʻrishga ruxsatingiz yoʻq.",
    "Actions": "Amallar",
    "Delete selected items": "Tanlanganlarni oʻchirish",
    "Search": "Qidiruv",
    "Select all": "Hammasini tanlash",
    "Select item": "Tanlash",
    "View": "Koʻrish",
    "Showing %(start)s to %(end)s of %(count)s items": "%(count)s tadan %(start)s–%(end)s koʻrsatilmoqda",
    "prev": "oldingi",
    "next": "keyingi",
    "Show": "Koʻrsatish",
    "%(size)s / Page": "%(size)s / sahifa",
    "Filters": "Filtrlar",
    "Login to %(title)s": "%(title)s — kirish",
    "Username": "Login",
    "Enter username": "Loginni kiriting",
    "Password": "Parol",
    "Login": "Kirish",
    "Close": "Yopish",
    "Done": "Tayyor",
    "Clear filter": "Filtrni tozalash",
    "Apply Filter": "Filtrni qoʻllash",
    "Please confirm": "Tasdiqlang",
    "Yes": "Ha",
    "Choose CSV file": "CSV faylni tanlang",
    "No file selected": "Fayl tanlanmagan",
    "Skip invalid rows and continue import": "Notoʻgʻri qatorlarni oʻtkazib yuborib, importni davom ettirish",
    "Import progress": "Import jarayoni",
    "%(processed)s/%(total)s rows processed": "%(processed)s/%(total)s qator qayta ishlandi",
    "%(imported)s imported, %(skipped)s skipped, %(processed)s/%(total)s rows processed": (
        "%(imported)s ta import qilindi, %(skipped)s ta oʻtkazib yuborildi, "
        "%(processed)s/%(total)s qator qayta ishlandi"
    ),
    "%(imported)s imported, %(skipped)s skipped, %(processed)s/%(total)s rows processed - "
    "saving valid rows... (%(seconds)ss)": (
        "%(imported)s ta import qilindi, %(skipped)s ta oʻtkazib yuborildi, %(processed)s/%(total)s qator "
        "qayta ishlandi — toʻgʻri qatorlar saqlanmoqda... (%(seconds)s s)"
    ),
    "Import result": "Import natijasi",
    "Missed rows": "Oʻtkazib yuborilgan qatorlar",
    "Download CSV": "CSV yuklab olish",
    "Download TXT": "TXT yuklab olish",
    "Refresh list": "Roʻyxatni yangilash",
}
