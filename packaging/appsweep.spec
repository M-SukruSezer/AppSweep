%global appname appsweep
%global debug_package %{nil}

Name:           %{appname}
Version:        0.1.0
Release:        1%{?dist}
Summary:        One uninstaller for every way Linux installs software
Summary(tr):    Linux'ta yazılım kurmanın her yolu için tek kaldırma aracı

License:        GPL-3.0-or-later
URL:            https://github.com/M-SukruSezer/AppSweep
Source0:        %{appname}-%{version}.tar.gz

BuildArch:      noarch
BuildRequires:  gettext
Requires:       python3
Requires:       python3-gobject
Requires:       gtk4
Requires:       libadwaita
Recommends:     polkit

%description
AppSweep lists everything installed on the machine - whichever package
manager put it there - with the space it occupies, removes any of it in
one step, and then finds the configuration, caches and data that
uninstalling leaves behind.

It reads apt/dpkg, dnf/rpm, pacman, Flatpak, Snap, AppImage, pip, pipx,
npm and cargo. Every removal is shown as the exact commands it will run
before anything happens, protected paths are refused outright, and
deleted leftovers go to the trash rather than being destroyed.

%description -l tr
AppSweep, makinede kurulu olan her şeyi - hangi paket yöneticisi koymuş
olursa olsun - kapladığı alanla birlikte listeler, seçilenleri tek adımda
kaldırır ve ardından kaldırma işleminin geride bıraktığı ayar, önbellek
ve veri klasörlerini bulur.

apt/dpkg, dnf/rpm, pacman, Flatpak, Snap, AppImage, pip, pipx, npm ve
cargo kaynaklarını okur. Her kaldırma işlemi, çalıştırılacak komutların
tam metniyle önceden gösterilir; korunan yollar koşulsuz reddedilir ve
silinen kalıntılar yok edilmek yerine çöp kutusuna gönderilir.

%prep
%autosetup -n %{appname}-%{version}

%install
sh packaging/install-tree.sh %{buildroot} %{_prefix}

%check
python3 -m compileall -q appsweep

%files
%license LICENSE
%doc README.md README.tr.md
%{_bindir}/appsweep
%{_datadir}/appsweep/
%{_datadir}/applications/io.github.appsweep.AppSweep.desktop
%{_datadir}/icons/hicolor/*/apps/io.github.appsweep.AppSweep*.svg
%{_datadir}/locale/*/LC_MESSAGES/appsweep.mo
%{_datadir}/doc/appsweep/

%changelog
* Wed Nov 19 2026 Muhammed Şükrü SEZER <M-SukruSezer@users.noreply.github.com> - 0.1.0-1
- First release.
