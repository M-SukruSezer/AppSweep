# -*- coding: utf-8 -*-
"""Generate the project page in both languages from one structure.

The two pages have to stay the same page in two languages, not two pages
that drifted apart, so the markup lives here once and only the words
differ. Run after editing:

    python3 docs/_site.py

It writes docs/index.html (English) and docs/tr.html (Turkish).
"""
import pathlib
import re

HERE = pathlib.Path(__file__).parent
REPO = "https://github.com/M-SukruSezer/AppSweep"
VERSION = re.search(
    r'__version__ = "([^"]+)"',
    (HERE.parent / "appsweep" / "__init__.py").read_text(),
).group(1)

SOURCES = [
    ("apt", "--apt"), ("dnf", "--apt"), ("pacman", "--apt"),
    ("Flatpak", "--flatpak"), ("Snap", "--snap"), ("AppImage", "--flatpak"),
    ("pip", "--pip"), ("pipx", "--pip"), ("npm", "--npm"), ("cargo", "--cargo"),
]

EN = {
    "lang": "en", "other": "tr.html", "other_label": "Türkçe",
    "dir_doc": "README.md",
    "title": f"AppSweep {VERSION} — one uninstaller for every way Linux "
             f"installs software",
    "meta": "List every program installed by apt, dnf, pacman, Flatpak, Snap, "
            "AppImage, pip, pipx, npm and cargo, remove any of it in one "
            "step, and clear the files uninstalling leaves behind.",
    "nav_docs": "Docs", "nav_source": "Source", "nav_releases": "Releases",
    "shot": "screenshot-applications-en.png",
    "h1": "One uninstaller for every way Linux installs software",
    "cta_main": f"Download {VERSION}", "cta_alt": "View the source",
    "cta_note": f"Debian · Fedora · source tarball — GPL-3.0, "
                f"version {VERSION}",
    "shot_alt": "The AppSweep window listing installed applications with "
                "their icons and sizes",
    "s1_eyebrow": "One list",
    "s1_h2": "Everything installed, whichever package manager put it there",
    "s1_lede": "A Linux machine keeps its software in a dozen places at "
               "once, and each one answers a different command. AppSweep "
               "asks all of them and puts the answers in a single list you "
               "can sort by size.",
    "c1_big": "10", "c1_h": "sources, one window",
    "c1_p": "apt, dnf and pacman for the system; Flatpak, Snap and AppImage "
            "for the portable ones; pip, pipx, npm and cargo for the "
            "language managers that nothing else tracks.",
    "c2_big": "GB", "c2_h": "measured, not estimated",
    "c2_p": "Every row carries the space it really takes on disk, so the "
            "largest thing you no longer use is the first thing you see.",
    "c3_h": "Every row with its own icon",
    "c3_p": "Icons come from the desktop entries already on the system, and "
            "an ambiguous match is dropped rather than guessed — a wrong "
            "logo invites you to remove the wrong thing.",
    "views": [
        ("screenshot-leftovers-en.png", "Leftovers.",
         "Directories under your home folder, /etc and /var/lib that no "
         "installed application accounts for. Each one is marked certain, "
         "likely or a guess, and a guess is never ticked for you.",
         "The Leftovers view listing orphaned directories with confidence "
         "labels and sizes"),
        ("screenshot-reclaim-en.png", "Reclaim.",
         "Download caches, orphaned dependencies and superseded snap "
         "revisions — none of it something you chose to install, all of it "
         "measured rather than estimated.",
         "The Reclaim view showing 11 GB of reclaimable space"),
        ("screenshot-uninstall-en.png", "Before anything happens.",
         "Remove several at once and the confirmation shows what each one "
         "is, how thorough the removal will be, and the exact commands that "
         "will run.",
         "The uninstall confirmation listing five applications and the "
         "removal options"),
    ],
    "s2_eyebrow": "The three views",
    "s2_h2": "The program goes. Its settings, caches and data stay.",
    "s2_lede": "No package manager cleans these up, which is why a machine "
               "that has been in use for years carries folders belonging to "
               "software removed long ago. AppSweep lists the ones no "
               "installed application accounts for, tells you how sure it "
               "is about each, and sends what you confirm to the trash.",
    "s3_eyebrow": "Because it deletes files",
    "s3_h2": "The careful part is where it does nothing",
    "safety": [
        ("Nothing runs unconfirmed",
         "The exact commands appear before anything happens."),
        ("Protected paths are refused outright",
         "Whether or not they exist. Your document folders are read from "
         "user-dirs.dirs, so they are guarded under whatever name your "
         "language gives them."),
        ("A guess is labelled a guess",
         "Matches are marked certain, likely or guess, and a guess is never "
         "pre-selected."),
        ("Still-installed software keeps its own folder",
         "Removing one program never takes another's settings."),
        ("Leftovers go to the trash",
         "Not to /dev/null. Permanent deletion is a separate choice."),
    ],
    "s4_eyebrow": "Install",
    "s4_h2": f"Get AppSweep {VERSION}",
    "dl": [
        ("Debian, Ubuntu, Mint, Pop!_OS", ".deb package",
         f"sudo apt install ./appsweep_{VERSION}_all.deb"),
        ("Fedora, RHEL, openSUSE", ".rpm package",
         f"sudo dnf install ./appsweep-{VERSION}-1.noarch.rpm"),
        ("Any distribution", "source tarball",
         f"tar -xzf appsweep-{VERSION}.tar.gz\ncd appsweep-{VERSION}\n"
         f"./install.sh"),
    ],
    "dl_btn": "Download",
    "dl_note": "Needs Python 3.10+, GTK 4.10+ and libadwaita 1.4+. The "
               "tarball installs under ~/.local and needs no root. Every "
               "release carries SHA256SUMS.",
    "foot_license": "GPL-3.0-or-later",
    "foot_docs": "Documentation", "foot_issues": "Report an issue",
}

TR = {
    "lang": "tr", "other": "index.html", "other_label": "English",
    "dir_doc": "README.tr.md",
    "title": f"AppSweep {VERSION} — Linux'ta kurduğunuz her yazılımı tek bir yerden kaldırın",
    "meta": "apt, dnf, pacman, Flatpak, Snap, AppImage, pip, pipx, npm ve "
            "cargo ile kurulmuş her programı listeleyin, tek adımda "
            "kaldırın, kaldırmanın geride bıraktıklarını temizleyin.",
    "nav_docs": "Belgeler", "nav_source": "Kaynak", "nav_releases": "Sürümler",
    "shot": "screenshot-applications-tr.png",
    "h1": "Linux'ta kurduğunuz her yazılımı tek bir yerden kaldırın.",
    "cta_main": f"{VERSION} sürümünü indir", "cta_alt": "Kaynağa bak",
    "cta_note": f"Debian · Fedora · kaynak arşivi — GPL-3.0, "
                f"sürüm {VERSION}",
    "shot_alt": "AppSweep penceresi: kurulu uygulamalar, logoları ve "
                "boyutlarıyla listeleniyor",
    "s1_eyebrow": "Tek liste",
    "s1_h2": "Kurulu olan her şey, hangi paket yöneticisi koymuş olursa olsun",
    "s1_lede": "Bir Linux makinesi yazılımlarını aynı anda bir düzine yerde "
               "tutar ve her biri başka bir komuta yanıt verir. AppSweep "
               "hepsine sorar ve yanıtları, boyuta göre sıralayabileceğiniz "
               "tek bir listede toplar.",
    "c1_big": "10", "c1_h": "kaynak, tek pencere",
    "c1_p": "Sistem için apt, dnf ve pacman; taşınabilirler için Flatpak, "
            "Snap ve AppImage; başka hiçbir şeyin takip etmediği dil "
            "yöneticileri için pip, pipx, npm ve cargo.",
    "c2_big": "GB", "c2_h": "tahmin değil, ölçüm",
    "c2_p": "Her satır diskte gerçekten kapladığı alanı taşır; böylece artık "
            "kullanmadığınız en büyük şey ilk gördüğünüz şey olur.",
    "c3_h": "Her satır kendi logosuyla",
    "c3_p": "Logolar sistemde zaten bulunan masaüstü girdilerinden gelir; "
            "belirsiz bir eşleşme tahmin edilmek yerine atılır — yanlış bir "
            "logo, yanlış şeyi kaldırmaya davet eder.",
    "views": [
        ("screenshot-leftovers-tr.png", "Kalıntılar.",
         "Ev klasörünüzün, /etc ve /var/lib altındaki, hiçbir kurulu "
         "uygulamanın sahiplenmediği dizinler. Her biri kesin, olası ya da "
         "tahmin diye işaretlenir; tahmin olanlar sizin yerinize asla "
         "seçilmez.",
         "Kalıntılar ekranı: sahipsiz dizinler, güven etiketleri ve "
         "boyutlarıyla"),
        ("screenshot-reclaim-tr.png", "Geri Kazan.",
         "İndirme önbellekleri, artık bağımlılıklar ve eskimiş snap "
         "sürümleri — hiçbiri sizin bilerek kurduğunuz bir şey değil, hepsi "
         "tahmin değil ölçüm.",
         "Geri Kazan ekranı: geri kazanılabilir 11 GB"),
        ("screenshot-uninstall-tr.png", "Bir şey olmadan önce.",
         "Birkaçını birden kaldırın; onay ekranı her birinin ne olduğunu, "
         "kaldırmanın ne kadar kapsamlı olacağını ve çalışacak komutların "
         "tam metnini gösterir.",
         "Kaldırma onayı: beş uygulama ve kaldırma seçenekleri"),
    ],
    "s2_eyebrow": "Üç ekran",
    "s2_h2": "Program gider. Ayarları, önbellekleri ve verisi kalır.",
    "s2_lede": "Hiçbir paket yöneticisi bunları temizlemez; yıllardır "
               "kullanılan bir makinenin, çoktan kaldırılmış yazılımlara ait "
               "klasörler taşımasının sebebi budur. AppSweep, hiçbir kurulu "
               "uygulamanın sahiplenmediği klasörleri listeler, her biri "
               "için ne kadar emin olduğunu söyler ve onayladıklarınızı çöp "
               "kutusuna gönderir.",
    "s3_eyebrow": "Dosya sildiği için",
    "s3_h2": "Asıl özen, hiçbir şey yapmadığı yerlerde",
    "safety": [
        ("Hiçbir şey onaysız çalışmaz",
         "Çalışacak komutlar, bir şey olmadan önce görünür."),
        ("Korunan yollar koşulsuz reddedilir",
         "Var olsunlar ya da olmasınlar. Belge klasörleriniz "
         "user-dirs.dirs dosyasından okunur, yani dilinizin verdiği adla "
         "korunurlar."),
        ("Tahmin, tahmin olarak etiketlenir",
         "Eşleşmeler kesin, olası ya da tahmin diye işaretlenir; tahmin "
         "olanlar asla önceden seçili gelmez."),
        ("Hâlâ kurulu yazılım kendi klasörünü korur",
         "Bir programı kaldırmak, başka birinin ayarlarını asla götürmez."),
        ("Kalıntılar çöp kutusuna gider",
         "/dev/null'a değil. Kalıcı silme ayrı bir seçimdir."),
    ],
    "s4_eyebrow": "Kurulum",
    "s4_h2": f"AppSweep {VERSION} sürümünü edinin",
    "dl": [
        ("Debian, Ubuntu, Mint, Pop!_OS", ".deb paketi",
         f"sudo apt install ./appsweep_{VERSION}_all.deb"),
        ("Fedora, RHEL, openSUSE", ".rpm paketi",
         f"sudo dnf install ./appsweep-{VERSION}-1.noarch.rpm"),
        ("Her dağıtım", "kaynak arşivi",
         f"tar -xzf appsweep-{VERSION}.tar.gz\ncd appsweep-{VERSION}\n"
         f"./install.sh"),
    ],
    "dl_btn": "İndir",
    "dl_note": "Python 3.10+, GTK 4.10+ ve libadwaita 1.4+ gerekir. Arşiv "
               "~/.local altına kurar, kök yetkisi istemez. Her sürümde "
               "SHA256SUMS bulunur.",
    "foot_license": "GPL-3.0-or-later",
    "foot_docs": "Belgeler", "foot_issues": "Sorun bildir",
}


def esc(text):
    return (text.replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;"))


def render(t):
    sources = "\n".join(
        f'        <li style="--c: var({var})"><b>{name}</b></li>'
        for name, var in SOURCES
    )
    safety = "\n".join(
        f"""        <li>
          <span class="k"></span>
          <div><b>{esc(title)}</b><p>{esc(body)}</p></div>
        </li>"""
        for title, body in t["safety"]
    )
    views = "\n".join(
        f"""    <figure class="view reveal">
      <img src="{shot}" alt="{esc(alt)}" loading="lazy">
      <figcaption><b>{esc(title)}</b> {esc(body)}</figcaption>
    </figure>"""
        for shot, title, body, alt in t["views"]
    )
    downloads = "\n".join(
        f"""        <div class="dl-card">
          <p class="for">{esc(who)}</p>
          <h3>{esc(what)}</h3>
          <code>{esc(cmd)}</code>
          <a class="btn btn-primary" href="{REPO}/releases/latest">{
              esc(t['dl_btn'])}</a>
        </div>"""
        for who, what, cmd in t["dl"]
    )

    return f"""<!DOCTYPE html>
<!-- Generated by docs/_site.py — edit that file, not this one. -->
<html lang="{t['lang']}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(t['title'])}</title>
<meta name="description" content="{esc(t['meta'])}">
<meta property="og:title" content="{esc(t['title'])}">
<meta property="og:description" content="{esc(t['meta'])}">
<meta property="og:image" content="{REPO}/raw/main/docs/{t['shot']}">
<meta property="og:type" content="website">
<link rel="icon" href="icon.png">
<link rel="alternate" hreflang="{'tr' if t['lang'] == 'en' else 'en'}"
      href="{t['other']}">
<link rel="stylesheet" href="assets/site.css">
</head>
<body>

<header class="hb">
  <div class="wrap hb-in">
    <img src="icon.png" alt="">
    <span class="name">AppSweep</span>
    <span class="ver num">{VERSION}</span>
    <nav>
      <a class="hide-sm" href="{REPO}/blob/main/{t['dir_doc']}">{
          esc(t['nav_docs'])}</a>
      <a class="hide-sm" href="{REPO}">{esc(t['nav_source'])}</a>
      <a href="{REPO}/releases">{esc(t['nav_releases'])}</a>
      <span class="lang">
        <a href="index.html" {'aria-current="true"' if t['lang'] == 'en'
                              else ''}>EN</a>
        <a href="tr.html" {'aria-current="true"' if t['lang'] == 'tr'
                           else ''}>TR</a>
      </span>
    </nav>
  </div>
</header>

<main>

<div class="hero wrap">
  <h1>{esc(t['h1'])}</h1>
  <ul class="sources">
{sources}
  </ul>
  <div class="cta">
    <a class="btn btn-primary" href="#download">{esc(t['cta_main'])}</a>
    <a class="btn btn-ghost" href="{REPO}">{esc(t['cta_alt'])}</a>
  </div>
  <p class="cta-note num">{esc(t['cta_note'])}</p>
</div>

<div class="shot">
  <img src="{t['shot']}" alt="{esc(t['shot_alt'])}"
       width="1000" height="760">
</div>

<section>
  <div class="wrap">
    <div class="sec-head reveal">
      <p class="eyebrow">{esc(t['s1_eyebrow'])}</p>
      <h2>{esc(t['s1_h2'])}</h2>
      <p class="lede">{esc(t['s1_lede'])}</p>
    </div>
    <div class="grid g-3">
      <div class="card"><span class="big num">{esc(t['c1_big'])}</span>
        <h3>{esc(t['c1_h'])}</h3><p>{esc(t['c1_p'])}</p></div>
      <div class="card"><span class="big">{esc(t['c2_big'])}</span>
        <h3>{esc(t['c2_h'])}</h3><p>{esc(t['c2_p'])}</p></div>
      <div class="card"><h3>{esc(t['c3_h'])}</h3>
        <p>{esc(t['c3_p'])}</p></div>
    </div>
  </div>
</section>

<section class="views">
  <div class="wrap">
    <div class="sec-head reveal">
      <p class="eyebrow">{esc(t['s2_eyebrow'])}</p>
      <h2>{esc(t['s2_h2'])}</h2>
      <p class="lede">{esc(t['s2_lede'])}</p>
    </div>
{views}
  </div>
</section>

<section>
  <div class="wrap">
    <div class="sec-head reveal">
      <p class="eyebrow">{esc(t['s3_eyebrow'])}</p>
      <h2>{esc(t['s3_h2'])}</h2>
    </div>
    <ul class="safety reveal">
{safety}
    </ul>
  </div>
</section>

<section class="dl" id="download">
  <div class="wrap">
    <div class="sec-head reveal">
      <p class="eyebrow">{esc(t['s4_eyebrow'])}</p>
      <h2>{esc(t['s4_h2'])}</h2>
    </div>
    <div class="grid g-3">
{downloads}
    </div>
    <p class="checks">{esc(t['dl_note'])}</p>
  </div>
</section>

</main>

<footer>
  <div class="wrap foot-in">
    <span>AppSweep {VERSION} · {esc(t['foot_license'])}</span>
    <a href="{REPO}/blob/main/{t['dir_doc']}">{esc(t['foot_docs'])}</a>
    <a href="{REPO}/issues">{esc(t['foot_issues'])}</a>
    <a href="{t['other']}">{esc(t['other_label'])}</a>
  </div>
</footer>

<script src="https://cdn.jsdelivr.net/npm/gsap@3.12.5/dist/gsap.min.js"
        defer></script>
<script src="https://cdn.jsdelivr.net/npm/gsap@3.12.5/dist/ScrollTrigger.min.js"
        defer></script>
<script src="assets/site.js" defer></script>
</body>
</html>
"""


for data, name in ((EN, "index.html"), (TR, "tr.html")):
    (HERE / name).write_text(render(data), encoding="utf-8")
    print(f"docs/{name}")
