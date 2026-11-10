/* UI chrome i18n: fa, en, de, ru. RTL only for fa. */
window.I18N = {
  fa: {
    tabChat:"گفتگو", tabOffice:"دفتر", tabAdmin:"مدیریت", tabLang:"زبان",
    langTitle:"زبان / Language / Sprache / Язык",
    langHint:"زبان رابط کاربری را انتخاب کن. گفتگو و دفتر صفحه‌های جدا هستند.",
    langNow:"زبان فعلی",
    start:"شروع کار دفتر", stop:"توقف", save:"ذخیره", clear:"پاک کردن", all:"همه",
    officeMode:"حالت دفتر", roles:"نقش‌ها", boss:"مدیر", secretary:"منشی",
    judgeLegacy:"داور (قدیمی)", wires:"نمایش پیام‌های رمزی کارکنان",
    topic:"موضوع بحث", send:"ارسال",
    placeholder:"با مدیر حرف بزن… یا @نام برای یک کارمند (Enter)",
    accessAsk:"پرسش (پیش‌فرض)", accessAuto:"خودمختاری کامل",
    accessHint:"در حالت پرسش، ابزارهای دارای اثر جانبی اول از تو تأیید می‌گیرند. در خودمختاری کامل، هر نقش فقط ابزار شغل خودش را آزادانه اجرا می‌کند. کیف‌پول و پرداخت همیشه نیاز به تأیید دارند.",
    scorecard:"کارنامه بهینه‌ساز", inspector:"پیشنهادهای بازرس", apply:"اعمال", dismiss:"رد",
    suggested:"APIهای پیشنهادی", perms:"مجوزهای شغلی", keys:"سرویس‌ها و کلیدها",
    needKey:"کلید لازمه", hasKey:"کلید دارد"
  },
  en: {
    tabChat:"Chat", tabOffice:"Office", tabAdmin:"Admin", tabLang:"Language",
    langTitle:"Language / زبان / Sprache / Язык",
    langHint:"Choose the interface language. Chat and Office are separate pages.",
    langNow:"Current language",
    start:"Start office work", stop:"Stop", save:"Save", clear:"Clear", all:"All",
    officeMode:"Office mode", roles:"Roles", boss:"Boss", secretary:"Secretary",
    judgeLegacy:"Judge (legacy)", wires:"Show staff coded messages",
    topic:"Topic", send:"Send",
    placeholder:"Talk to the boss… or @name for one employee (Enter)",
    accessAsk:"Ask (default)", accessAuto:"Full autonomy",
    accessHint:"In Ask mode, side-effect tools wait for your approval. In Full autonomy each role may only run its own job tools. Wallet and payments always need your approval.",
    scorecard:"Optimizer scorecard", inspector:"Inspector proposals", apply:"Apply", dismiss:"Dismiss",
    suggested:"Suggested APIs", perms:"Job permissions", keys:"Providers and keys",
    needKey:"Key needed", hasKey:"Has key"
  },
  de: {
    tabChat:"Chat", tabOffice:"Büro", tabAdmin:"Verwaltung", tabLang:"Sprache",
    langTitle:"Sprache / Language / زبان / Язык",
    langHint:"Wähle die Sprache der Oberfläche. Chat und Büro sind getrennte Seiten.",
    langNow:"Aktuelle Sprache",
    start:"Büroarbeit starten", stop:"Stopp", save:"Speichern", clear:"Leeren", all:"Alle",
    officeMode:"Büro-Modus", roles:"Rollen", boss:"Chef", secretary:"Sekretär",
    judgeLegacy:"Richter (alt)", wires:"Kodierte Mitarbeiter-Nachrichten zeigen",
    topic:"Thema", send:"Senden",
    placeholder:"Sprich mit dem Chef… oder @Name für eine Person (Enter)",
    accessAsk:"Nachfragen (Standard)", accessAuto:"Volle Autonomie",
    accessHint:"Im Nachfragen-Modus warten Werkzeuge mit Nebenwirkung auf deine Freigabe. In voller Autonomie darf jede Rolle nur ihre Job-Werkzeuge nutzen. Wallet und Zahlungen brauchen immer deine Freigabe.",
    scorecard:"Optimizer-Scorekarte", inspector:"Vorschläge des Inspektors", apply:"Übernehmen", dismiss:"Ablehnen",
    suggested:"Vorgeschlagene APIs", perms:"Rollenrechte", keys:"Dienste und Schlüssel",
    needKey:"Schlüssel nötig", hasKey:"Schlüssel vorhanden"
  },
  ru: {
    tabChat:"Чат", tabOffice:"Офис", tabAdmin:"Админ", tabLang:"Язык",
    langTitle:"Язык / Language / زبان / Sprache",
    langHint:"Выберите язык интерфейса. Чат и Офис — отдельные страницы.",
    langNow:"Текущий язык",
    start:"Начать работу офиса", stop:"Стоп", save:"Сохранить", clear:"Очистить", all:"Все",
    officeMode:"Режим офиса", roles:"Роли", boss:"Босс", secretary:"Секретарь",
    judgeLegacy:"Судья (старый)", wires:"Показывать кодовые сообщения сотрудников",
    topic:"Тема", send:"Отправить",
    placeholder:"Напишите боссу… или @имя для сотрудника (Enter)",
    accessAsk:"Спрашивать (по умолчанию)", accessAuto:"Полная автономия",
    accessHint:"В режиме «Спрашивать» инструменты с побочным эффектом ждут вашего одобрения. В полной автономии каждая роль выполняет только свои рабочие инструменты. Кошелёк и платежи всегда требуют одобрения.",
    scorecard:"Карточка оптимизатора", inspector:"Рекомендации инспектора", apply:"Применить", dismiss:"Отклонить",
    suggested:"Рекомендуемые API", perms:"Права ролей", keys:"Сервисы и ключи",
    needKey:"Нужен ключ", hasKey:"Ключ есть"
  }
};
window.currentLang = function(){ return localStorage.getItem("rt-lang") || "fa"; };
window.t = function(k){ const pack=I18N[currentLang()]||I18N.fa; return pack[k]||(I18N.en[k]||k); };
window.applyI18n = function(code){
  const c = code || currentLang();
  if(!I18N[c]) return;
  localStorage.setItem("rt-lang", c);
  document.documentElement.lang = c;
  document.documentElement.dir = (c==="fa") ? "rtl" : "ltr";
  document.querySelectorAll("[data-i18n]").forEach(el=>{
    const k=el.getAttribute("data-i18n");
    if(k && t(k)) el.textContent=t(k);
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach(el=>{
    const k=el.getAttribute("data-i18n-placeholder");
    if(k && t(k)) el.setAttribute("placeholder", t(k));
  });
  const now=document.getElementById("lang-now");
  if(now) now.textContent = t("langNow")+": "+({fa:"فارسی",en:"English",de:"Deutsch",ru:"Русский"}[c]||c);
  document.querySelectorAll("[data-lang]").forEach(b=>b.classList.toggle("pri", b.getAttribute("data-lang")===c));
};
window.setLang = function(c){ applyI18n(c); if(typeof toast==="function") toast(({fa:"فارسی",en:"English",de:"Deutsch",ru:"Русский"}[c]||c)); };
document.addEventListener("DOMContentLoaded", ()=>applyI18n(currentLang()));
