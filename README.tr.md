# Codexpp

> Diller: [İngilizce](https://github.com/avometre/Codexpp/blob/main/README.md) · [Türkçe](https://github.com/avometre/Codexpp/blob/main/README.tr.md)

[![PyPI](https://img.shields.io/pypi/v/codexpp)](https://pypi.org/project/codexpp/)
[![Python](https://img.shields.io/pypi/pyversions/codexpp)](https://pypi.org/project/codexpp/)
[![Lisans](https://img.shields.io/pypi/l/codexpp)](LICENSE)
[![GitHub Codespaces'ta Aç](https://github.com/codespaces/badge.svg)](https://codespaces.new/avometre/Codexpp?quickstart=1)
Codexpp, OpenAI Codex CLI'yi rol tabanlı ve otomasyon dostu yapılandırılmış iş akışlarına dönüştüren modüler bir genişletme çerçevesidir. Slash komutları, persona tabanlı çalışma modları ve otomatik MCP (Model Context Protocol) kurulumu ile Codex deneyimini daha üretken ve tutarlı hale getirir.

## İçindekiler
- [Özellikler](#özellikler)
- [Kurulum](#kurulum)
- [Hızlı Başlangıç](#hızlı-başlangıç)
- [Codex CLI Yardımcıları](#codex-cli-yardımcıları)
- [Prompt Yazımı](#prompt-yazımı)
- [Komut Detayları](#komut-detayları)
- [Parametre Sözlüğü](#parametre-sözlüğü)
- [Katkıda Bulunma](#katkıda-bulunma)
- [Lisans](#lisans)

## Özellikler
- **Slash Komutları:** TOML tabanlı tanımlar sayesinde Codex CLI içinde `cx:*` komutları olarak görünür.
- **Persona Modu:** `system-architect`, `implementation-engineer`, `code-reviewer` gibi rolleri tek komutla uygulayın.
- **Otomatik Entegrasyon:** `codexpp codex install`, komutları, prompt dosyalarını ve MCP profillerini Codex CLI'ye işler.
- **Prompt Şablonları:** YAML önsözlü Markdown şablonları tüm `cx:*` komutlarını besler ve Codex CLI’ye otomatik senkronize edilir.
- **Şablon Doğrulaması:** Prompt placeholder'ları çalıştırmadan önce doğrulanır; eksik tanımlarda uyarı verilir.
- **Persona Senkronizasyonu:** Proje ve global `AGENTS.md` dosyalarını tek komutla güncel tutun.
- **MCP Yönetimi:** Popüler MCP sunucuları (Filesystem, Context7, GitHub, Memory, Sequential Thinking, Puppeteer) hazır gelir.

## Kurulum

### Gereksinimler
- Python 3.11 veya üzeri
- Node.js & npm (opsiyonel, Codex CLI entegrasyonu için)
 - Codex CLI (opsiyonel): `npm i -g @openai/codex`

### PyPI üzerinden

Önerilen (izole CLI kurulumu):
```bash
pipx install codexpp
# veya
uv tool install codexpp
```

Alternatifler:
```bash
# Mevcut sanal ortamda (venv)
python -m venv .venv && source .venv/bin/activate
pip install -U pip
pip install codexpp

# veya UV ile proje sanal ortamı
uv venv .venv && source .venv/bin/activate
uv pip install codexpp
```

### Geliştirme kurulumu
```bash
git clone https://github.com/avometre/codexpp.git
cd codexpp
uv venv .venv && source .venv/bin/activate
uv pip install -e .
```
(İsterseniz `uv` yerine `python -m venv` + `pip install -e .` kullanabilirsiniz.)

Kurulum sonrası doğrulama:
```bash
codexpp --help
codexpp codex status
```

## Hızlı Başlangıç
Codex CLI içinde `cx:*` komutlarını kullanmak için aşağıdaki akışı izleyin:

1. **Komutları Codex CLI'ye yükleyin**
   ```bash
   codexpp codex install --force
   ```
   - `~/.codex/config.toml` içindeki slash komut bloklarını günceller.
   - `~/.codex/prompts/` dizinine şablonları yazar.
   - Prompt ve MCP profillerini tek seferde kurar; ekstra araç ya da manuel kopyalama gerekmez.

2. **Codex CLI'yi başlatın**
   ```bash
   codex
   ```
   `/prompts:` menüsünde `cx:analyze`, `cx:implement`, `cx:review` vb. komutları görebilirsiniz.

3. **Yeni proje için tam kurulum**
   ```bash
   codexpp codex init --profile full --force
   ```
   Bootstrap klasörlerini oluşturur, persona yönergelerini senkronize eder ve komut paketlerini/MCP profillerini kurar.

## Codex CLI Yardımcıları

### `codexpp codex install`
Paketlenmiş `cx:*` komutlarını ve MCP profillerini yerel Codex CLI yapılandırmanıza işler. Paylaşılan makinelerde veya mevcut `~/.codex/config.toml` dosyanızı değiştirmeden önce aşağıdaki güvenlik parametrelerini kullanabilirsiniz.

**Faydalı parametreler**
- `--dry-run` — Yapılacak değişiklikleri ve MCP özetini gösterir; dosyalara dokunmaz, prompt senkronizasyonu yapılmaz.
- `--backup` — `~/.codex/config.toml` yazılmadan önce `<config>.bak` dosyası üretir.
- `--backup-path PATH` — Yedeği özel bir dizine yönlendirir (ör. dotfiles repo).
- Codex CLI ikilisini npm/pnpm’nin sık kullanılan dizinlerinde otomatik arar; gerektiğinde `--codex-bin` ile manuel yol verebilirsiniz.

Dry-run çıktısı örneği:

```bash
$ codexpp codex install --dry-run
[codexpp] [1/5] Preparing Codex CLI context
    • Project path : /workspace/codexpp
    • Codex binary : /usr/local/bin/codex
[codexpp] [2/5] Loading command definitions
    • Base commands : 12
    • Command packs : (none)
    • Total commands: 12
...
[codexpp] [5/5] Syncing Codex prompt templates
    • Target directory: /home/me/.codex/prompts
    • Force overwrite : False
[codexpp] Codex install completed.
```

### `codexpp codex uninstall`
Daha önce kurulan slash komut bloklarını, prompt şablonlarını ve MCP profillerini temizler.

**Faydalı parametreler**
- `--dry-run` — Temizlenecek config diff’ini ve silinecek prompt/MCP dosyalarını listeler.
- `--backup` / `--backup-path PATH` — Kurulum komutuyla aynı yedekleme davranışını sunar.
- `--prompts-dir` / `--mcp-dir` — Codex CLI farklı bir dizinde ise hedef yolları özelleştirir.

Dry-run çıktısı örneği:

```bash
$ codexpp codex uninstall --dry-run
[codexpp] [1/4] Analyzing Codex installation
    • Config path : /home/me/.codex/config.toml
    • Prompts dir : /home/me/.codex/prompts (12 file(s) tracked)
    • MCP dir     : /home/me/.codex/mcp (6 file(s) tracked)
[codexpp] Dry run enabled; no files were changed.
```

### `codexpp version`
Codexpp paket sürümünü, kurulum yolunu, Python ortamını ve Codex CLI bilgisini gösterir.

**Öne çıkanlar**
- Paket sürümü, dosya konumu ve kullanılan Python yürütücüsünü listeler.
- `--json` ile makine tarafından okunabilir çıktı alabilir, `--codex-bin` ile özel Codex CLI yolunu sorgulayabilirsiniz.

```bash
$ codexpp version
Codexpp 0.x.y
  Location : /workspace/codexpp/codexpp
  Python   : 3.11.9 (/usr/local/bin/python3)
  Codex CLI: /usr/local/bin/codex — codex 0.56.0
```

## Prompt Yazımı

Her `cx:*` komutu, `codexpp/resources/prompts/default/` altında bulunan Markdown şablonlarıyla tanımlanır. Örnek format:

```markdown
---
title: Repository Analysis
description: Belirlenen scope’u analiz et ve eylem öner.
argument_hint: TARGET=<path> [CONTEXT="notlar"] [FOCUS="alanlar"] [DEPTH=medium]
persona: system-architect
---

...bölüm başlıkları ve $PLACEHOLDER referansları...
```

Önemli noktalar:
- YAML başlığı başlık/açıklama, `argument_hint`, `persona` bilgilerini içerir.
- Gövde kısmındaki `$PLACEHOLDER` sembolleri (örn. `$TARGET`, `$FOCUS`) Codex CLI içindeki promptlarda okunabilirlik içindir. `codexpp commands run` kullanıldığında parametreler TOML tanımlarından `{{target}}` benzeri değişkenlere dönüştürülerek render edilir; Codex’e senkronlanan prompt dosyaları `$PLACEHOLDER` metnini aynen korur.
- `codexpp commands render` ve `codexpp codex install` komutları Markdown şablonlarını olduğu gibi (front matter dâhil) Codex’e senkronlar.

Yeni prompt eklemek/güncellemek için:
1. İlgili `.md` dosyasını düzenleyin veya yenisini oluşturun.
2. (Gerekirse) `codexpp/resources/commands/*.toml` içinde yeni input’ları tanımlayın.
3. `codexpp commands render <komut_id>` ile ön izleme yapın veya `codexpp codex install --force` ile Codex CLI’ye senkronlayın.

## Komut Detayları

- `cx:analyze`
  - Amaç: Seçili kapsam için kanıta dayalı depo analizi; uygulama kodu yazmaz.
  - Persona: `system-architect`
  - Çıktı: Yönetici Özeti; Mimari ve Veri Akışı; Bağımlılıklar ve Yüzeyler; Kalite ve Risk; Sıcak Noktalar ve Kanıtlar; Öneriler ve Yol Haritası
  - Kullanım ipucu: `TARGET=<path or scope> [CONTEXT="..."] [FOCUS="..."] [DEPTH=light|medium|deep]`

- `cx:implement`
  - Amaç: Küçük ve doğrulanabilir adımlarla somut kod ve test değişiklikleri planlamak ve anlatmak.
  - Persona: `implementation-engineer`
  - Çıktı: Uygulama Özeti; Plan ve Adımlar; Alana Göre Kod Değişiklikleri; Testler; Manuel Doğrulama; Dosya Özeti
  - Kullanım ipucu: `SPEC="<feature or task>" [NOTES="..."] [FLAG="..."]`

- `cx:review`
  - Amaç: Önceliklendirilmiş ve eyleme dönük geri bildirimlerle kıdemli seviye kod incelemesi.
  - Persona: `code-reviewer`
  - Çıktı: Değişiklik Özeti; İnceleme Sınıflandırması; Güçlü Yönler; Sorunlar – Zorunlu Düzeltme; Sorunlar – Düzeltilebilir; Sorunlar – Güzel Olur; Testler ve Kapsam; Genel Öneri
  - Kullanım ipucu: `DIFF_SOURCE=<diff or ref> [FOCUS="..."] [RISK=low|medium|high]`

- `cx:plan`
  - Amaç: Özellik/sorunu kademeli bir uygulama planına dönüştürmek; riskler ve test stratejisi ile.
  - Persona: `system-architect`
  - Çıktı: Genel Bakış; Varsayımlar; Yüksek Seviye Yaklaşım; Adım Adım Plan; Test Stratejisi; Riskler ve Takaslar; Bağımlılıklar ve Sıralama
  - Kullanım ipucu: `SPEC="<feature or problem>" [HINTS="..."] [CONSTRAINTS="..."] [ESTIMATE=true|false]`

- `cx:test`
  - Amaç: Davranışlar, senaryolar, vakalar ve komutları içeren pratik bir test stratejisi.
  - Persona: `implementation-engineer`
  - Çıktı: Test Hedefi; Mevcut Kapsam; Test Senaryoları; Test Vakaları; Test Uygulama Planı; Köşe Durumlar ve Riskler; Sonraki Adımlar
  - Kullanım ipucu: `CHANGE="<summary>" [TESTS="..."] [COVERAGE="percent or notes"]`

- `cx:doc`
  - Amaç: Değişiklik için hedef kitleye uygun dokümantasyon hazırlamak.
  - Persona: `system-architect`
  - Çıktı: Genel Bakış; Hedef Kitle ve Etki; Ana Kavramlar ve Davranış; Kullanım / Entegrasyon; Operasyonel Notlar; Takip Dokümantasyonu
  - Kullanım ipucu: `CHANGE="<summary>" [AUDIENCE="developer|user|API|ops"] [STYLE="..."]`

- `cx:deploy`
  - Amaç: Ön kontroller, adımlar, doğrulama ve rollback hazırlığıyla güvenli, tekrarlanabilir dağıtım planı.
  - Persona: `implementation-engineer`
  - Çıktı: Dağıtım Özeti; Dağıtım Öncesi Kontroller; Dağıtım Adımları; Doğrulama ve Gözlemlenebilirlik; Geri Dönüş Hazırlığı; Sonraki Adımlar
  - Kullanım ipucu: `NOTES="<release notes>" ENVIRONMENT=<env> [WINDOW="..."] [FLAG="..."]`

- `cx:rollback`
  - Amaç: Tetikleyiciler, adımlar ve takiplerle hızlı ve güvenli rollback planı.
  - Persona: `implementation-engineer`
  - Çıktı: Geri Dönüş Özeti; Geri Dönüş Kapsamı; Önkoşullar ve Güvenlik Kontrolleri; Geri Dönüş Adımları; Geri Dönüş Sonrası Doğrulama; Riskler ve Geri Döndürülemez Etkiler; Takip Aksiyonları
  - Kullanım ipucu: `INCIDENT="<summary>" [VERSION="<current or target>"] [DB_IMPACT=yes|no] [FEATURE_FLAG="..."]`

- `cx:status`
  - Amaç: Sağlık, olaylar, riskler ve eylemleri özetleyen operasyonel durum brifingi.
  - Persona: `system-architect`
  - Çıktı: Durum Özeti; Durum Sınıflandırması; Sağlıklı Olanlar; Endişe Verenler; Olaylar ve Açık İşler; Öneriler
  - Kullanım ipucu: `SCOPE="<service or module>" [METRICS="..."] [SLO="..."]`

- `cx:security`
  - Amaç: Önceliklendirilmiş bulgular ve somut düzeltmelerle odaklı güvenlik denetimi.
  - Persona: `code-reviewer`
  - Çıktı: Güvenlik Özeti; Varlıklar ve Tehdit Modeli; Önemli Bulgular; Şiddet Dağılımı; Önerilen Düzeltmeler; Test ve Doğrulama; Sonraki Adımlar
  - Kullanım ipucu: `TARGET=<scope> [CONTEXT="..."] [FOCUS="..."] [DEPTH=light|medium|deep] [FORMAT=markdown|json|yaml|html]`


## Parametre Sözlüğü

- `TARGET` — Dizin, paket veya dosya kapsamı. Varsayılan geçerli dizin (`.`). Örnekler: `src/`, `pkg/payments`, `src/app.py`.
- `CONTEXT` — Yanıtı şekillendiren serbest biçimli notlar/kısıtlar (örn. "monolith", "sadece dahili", "performans öncelikli").
- `FOCUS` — Virgülle ayrılmış odak etiketleri; katı değil, çıktıyı yönlendirir. Yaygın değerler: `arch,deps,tests,perf,security,readability`.
  - Örnekler: `FOCUS=arch,tests`, `FOCUS=security,perf`.
- `DEPTH` — İncelemenin ayrıntı düzeyi: `light` (yüksek seviye), `medium` (dengeli), `deep` (derin; daha fazla sıcak nokta ve detay).
- `FORMAT` — `cx:security` çıktısı için: `markdown` (varsayılan), `json`, `yaml`, `html`.
- `RISK` — `cx:review` için beklenen risk: `low|medium|high`; incelemenin sıkılığı/öncelikleri etkiler.
- `ESTIMATE` — `cx:plan` içinde kaba zaman tahmini olsun mu: `true|false` (varsayılan `false`).
- `COVERAGE` — `cx:test` için kapsam hedefi. Sayı veya yüzde metni (örn. `80` ya da `80%`).
- `FLAG` — `cx:implement`/`cx:deploy` için rollout’u koruyan feature flag adı.
- `WINDOW` — `cx:deploy` için bakım penceresi metni (örn. `2025-11-14 03:00–04:00 UTC`).
- `SCOPE` — `cx:status` için servis/modül adı (örn. `payments-api`).
- `METRICS` — `cx:status` için öne çıkan metrikler veya dashboard linkleri.
- `SLO` — `cx:status` için SLO hedefleri (örn. `aylık %99.9 erişilebilirlik`).
- `HINTS` — `cx:plan` için depo ipuçları (örn. `src/users, tests/test_users.py`).
- `CONSTRAINTS` — `cx:plan` için varsayımlar/kısıtlar (örn. `DB migration yok`).
- `ENVIRONMENT` — `cx:deploy` hedef ortamı (örn. `staging`, `production`).
- `INCIDENT` — `cx:rollback` için olay özeti/bağlantısı.
- `VERSION` — `cx:rollback` için mevcut ya da hedef sürüm (örn. `v1.2.3`).
- `DB_IMPACT` — `cx:rollback` için veri/migration etkisi göstergesi: `yes|no`.
- `FEATURE_FLAG` — `cx:rollback` sırasında kapatılacak flag.

Parametre geçirme örnekleri:
- Codex CLI içinde: `/prompts` menüsündeki her komutun `argument_hint` satırını izleyin.
- Komut satırından: `codexpp commands run cx:analyze --set target=src/ --summary`.

## Katkıda Bulunma

Issue ve PR’ler memnuniyetle karşılanır. Lütfen değişiklikleri küçük ve odaklı tutun, mevcut tarzı koruyun ve gerekliyse test/dokümantasyon güncellemeleri ekleyin.

## Lisans

MIT lisansı — detaylar için `LICENSE` dosyasına bakın.
 
