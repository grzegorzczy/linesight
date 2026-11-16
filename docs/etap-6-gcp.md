# Etap 6 – chmura GCP i pętla MLOps

Rejestr wersji modelu w Cloud Storage, Jetson pobierający wskazaną wersję i budujący silnik TensorRT,
niepewne klatki wracające do chmury i retrening v2 z bramką jakości. Dokument uzupełniany w trakcie etapu.

Okna: **LAPTOP** (cmd), **SSH1/SSH2** (Jetson).

## Projekt i koszty (E6-01)

| Element | Wartość |
|---|---|
| Projekt | `linesight-514914` (organizacja `gczyrnianski202001-org`) |
| Konto rozliczeniowe | płatne – Free Trial na tym koncie Google był już wykorzystany |
| Budżet | 20 zł / miesiąc, alerty e-mail 50 / 90 / 100 % rzeczywistych i 100 % prognozowanych |
| Region | `us-central1` – darmowy poziom Cloud Storage (5 GB-mies. Standard, 5 tys. operacji A, 50 tys. B) |

Budżet **nie zatrzymuje** wydatków, tylko wysyła alerty. Spend caps (twardy limit, GA 11.2026) działają tylko
dla budżetu z jednym projektem i jedną kwalifikującą się usługą (głównie AI) i nie wstrzymują trwałych zasobów
jak magazyn – dla Cloud Storage nic nie dają. Ryzyko kosztów ograniczamy więc w projekcie: darmowy region,
klatki usuwane po 30 dniach, limit wysyłanych klatek w kodzie Jetsona, konto usługi Jetsona z dostępem tylko
do dwóch zasobników (wyciek klucza nie pozwala uruchomić maszyn wirtualnych).

### gcloud na laptopie
`gcloud` – oficjalne CLI Google Cloud (instalator `GoogleCloudSDKInstaller.exe`); po instalacji **nowe** okno cmd,
bo stare nie widzi zmienionego PATH.

```cmd
gcloud init
gcloud auth application-default login
gcloud config set project linesight-514914
gcloud auth application-default set-quota-project linesight-514914
gcloud services enable storage.googleapis.com
```
- `gcloud init` – logowanie samego CLI i domyślny projekt.
- `application-default login` – osobne poświadczenia ADC dla bibliotek Pythona (skrypty `publish` / `promote`);
  na stronie zgody trzeba zaznaczyć **wszystkie** pola, inaczej błąd „cloud-platform scope is required but not consented”.
- `set-quota-project` – projekt, któremu biblioteki przypisują zużycie API (inaczej mógłby to być stary projekt).
- `services enable` – w GCP każde API włącza się osobno dla projektu.

Sprawdzenie: `gcloud config list` (konto, `project = linesight-514914`), `gcloud billing projects describe
linesight-514914` (`billingEnabled: true`), `gcloud storage ls` („matched no objects” = brak zasobników, poprawnie).

Na liście projektów są też `gen-lang-client-…` – projekty zakładane przez AI Studio dla kluczy Gemini; nie ruszamy ich.

## Zasobniki i konto usługi (E6-02)

| Zasobnik | Zawartość | `jetson-edge` |
|---|---|---|
| `gs://linesight-514914-models` | wersje modelu: ONNX + `metrics.json`, wskazanie wersji dla urządzenia | `roles/storage.objectViewer` – odczyt i lista |
| `gs://linesight-514914-frames` | niepewne klatki z Jetsona do retreningu | `roles/storage.objectCreator` – **tylko dodawanie** |

Oba: `us-central1`, klasa STANDARD, `uniform_bucket_level_access: true` (uprawnienia tylko przez IAM zasobnika,
bez ACL na plikach), `public_access_prevention: enforced`. Klatki: reguła cyklu życia `Delete` po 30 dniach
(`infra/gcp/frames-lifecycle.json`). Domyślny soft delete trzyma usunięte obiekty 7 dni (`604800` s) – przy
kilkuset MB koszt pomijalny.

`objectCreator` nie ma odczytu ani usuwania, a nadpisanie obiektu wymaga usunięcia starego – przejęty Jetson
nie podmieni ani nie skasuje danych. Dwa zasobniki zamiast jednego z uprawnieniami warunkowymi na prefiksach:
prościej i czytelniej w polityce IAM.

```cmd
gcloud storage buckets create gs://linesight-514914-models --location=us-central1 --uniform-bucket-level-access --public-access-prevention
gcloud storage buckets create gs://linesight-514914-frames --location=us-central1 --uniform-bucket-level-access --public-access-prevention
gcloud storage buckets update gs://linesight-514914-frames --lifecycle-file=infra\gcp\frames-lifecycle.json
gcloud services enable iam.googleapis.com
gcloud iam service-accounts create jetson-edge --display-name="Jetson Nano edge"
gcloud storage buckets add-iam-policy-binding gs://linesight-514914-models --member=serviceAccount:jetson-edge@linesight-514914.iam.gserviceaccount.com --role=roles/storage.objectViewer
gcloud storage buckets add-iam-policy-binding gs://linesight-514914-frames --member=serviceAccount:jetson-edge@linesight-514914.iam.gserviceaccount.com --role=roles/storage.objectCreator
```
„Service account … does not exist” zaraz po `service-accounts create` – IAM jest *eventually consistent*;
po minucie ta sama komenda przechodzi.

### Klucz JSON zablokowany → krótkotrwałe tokeny
`gcloud iam service-accounts keys create` kończy się `constraints/iam.disableServiceAccountKeyCreation`.
Google sam utworzył organizację `gczyrnianski202001-org` przy koncie rozliczeniowym i włączył polityki
„secure by default” (organizacje od 3.05.2024). Konto Gmail nie jest jej administratorem
(`organizations add-iam-policy-binding` → brak `getIamPolicy`), więc wyjątku dla projektu nie zrobimy.

Rozwiązanie bez klucza – **impersonation**: konto użytkownika dostaje `roles/iam.serviceAccountTokenCreator`
na samym koncie `jetson-edge` i może wystawiać w jego imieniu tokeny ważne 1 h (IAM Credentials API).
```cmd
gcloud services enable iamcredentials.googleapis.com
gcloud iam service-accounts add-iam-policy-binding jetson-edge@linesight-514914.iam.gserviceaccount.com --member=user:gczyrnianski202001@gmail.com --role=roles/iam.serviceAccountTokenCreator
```
Rola działa po kilku minutach (wcześniej `iam.serviceAccounts.getAccessToken denied`).

Sprawdzenie najmniejszych uprawnień z laptopa – komendy wykonywane jako `jetson-edge`:
```cmd
gcloud storage ls gs://linesight-514914-models --impersonate-service-account=jetson-edge@linesight-514914.iam.gserviceaccount.com
gcloud storage ls gs://linesight-514914-frames --impersonate-service-account=jetson-edge@linesight-514914.iam.gserviceaccount.com
```
Wynik 16.11: models – bez błędu (pusto); frames – `storage.objects.list denied` (zamierzone).

| Wariant | Sekret na Jetsonie | Zależność | Uwagi |
|---|---|---|---|
| klucz JSON konta usługi | długoterminowy, ważny do ręcznego unieważnienia | brak | zablokowany polityką; Google odradza |
| **broker tokenów na laptopie (wybrany)** | token 1 h + sekret do brokera w sieci lokalnej | laptop musi działać, by odnowić token | w produkcji: brama brzegowa |
| Workload Identity Federation | brak | dostawca tożsamości (OIDC / certyfikat X.509) | wymaga nowszych bibliotek niż Python 3.6 |

## Broker tokenów i klient na Jetsonie (E6-03)

```
Jetson (gcs.py, Python 3.6, urllib) ── GET /token + sekret ──► laptop: linesight-tokens (Docker, :8010)
        │                                                       └─ ADC użytkownika → IAM Credentials API
        │                                                          → token jetson-edge (1 h, w pamięci brokera)
        └── Bearer token ──► storage.googleapis.com (JSON API): models = odczyt, frames = tylko dodawanie
```
- `cloud/token_broker.py` – `GET /token` z nagłówkiem `Authorization: Bearer <BROKER_SECRET>`; token odświeżany,
  gdy zostało < 5 min; w logach tylko adres i kod odpowiedzi, nigdy token. ADC montowane z
  `%APPDATA%\gcloud` tylko do odczytu.
- `jetson/gcs.py` – lista, pobranie (plik `.part` + zmiana nazwy), wysyłka z `ifGenerationMatch=0` (tylko nowy
  obiekt), `selftest`. Bez `google-cloud-storage`: ostatnia wersja dla Pythona 3.6 to 2.0.0 (2022) z
  zależnościami protobuf/api-core; trzy wywołania REST są prostsze.
- Sekret brokera: zmienna Windows `BROKER_SECRET` (laptop) i plik `~/.config/linesight/broker_secret`, prawa 600
  (Jetson). Sieć domowa, HTTP bez TLS – jak MQTT; w produkcji TLS albo sieć zarządzana.
