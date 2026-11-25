# Hosting ESP32-CAM di VPS Oracle dengan Docker

ESP32-CAM membuka koneksi WSS keluar ke VPS dan mengirim frame JPEG. Browser membuka domain yang sama lewat HTTPS untuk menonton dan mengatur kamera. Koneksi keluar ini bisa dipakai dari Wi-Fi rumah tanpa membuka port di router. Konfigurasi ini melayani satu kamera, dengan satu proses relay karena koneksi dan frame disimpan di memori.

## 1. Siapkan domain dan jaringan

- Di zona DNS `caksa.id`, arahkan record `A` bernama `live` ke IPv4 publik VPS. Jika ada record `AAAA` untuk `live.caksa.id`, pastikan IPv6-nya juga mencapai VPS. Caddy memakai domain ini untuk memperoleh dan memperbarui sertifikat TLS. [Dokumentasi HTTPS Caddy](https://caddyserver.com/docs/automatic-https)
- Di Oracle Cloud, izinkan TCP `443` dari `0.0.0.0/0` pada Network Security Group yang terpasang ke VNIC atau Security List subnet, serta di firewall VM. Port ini melayani HTTPS dan WSS. Caddy juga menerima koneksi langsung di port ini untuk memperoleh dan memperbarui sertifikat melalui TLS-ALPN. [Dokumentasi aturan jaringan Oracle](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/securityrules.htm) · [Validasi TLS-ALPN Caddy](https://caddyserver.com/docs/automatic-https#tls-alpn-challenge)
- Jika ingin membuka `http://live.caksa.id:8081` dari internet, izinkan juga TCP `8081`. Docker meneruskannya ke port HTTP `80` milik Caddy untuk redirect ke `https://live.caksa.id`. Jika memakai IPv6 publik, terapkan aturan yang sama untuk `::/0`. Di dalam jaringan Docker, Caddy meneruskan video dan kontrol ke `relay:8081`.
- Pasang Docker Engine dan plugin Docker Compose di VM. Contoh perintah di bawah memakai image VM Ubuntu dan akun SSH `ubuntu`. [Panduan instalasi Docker untuk Ubuntu](https://docs.docker.com/engine/install/ubuntu/)

## 2. Salin proyek dan isi konfigurasi

Dari folder proyek di komputer lokal, ganti `IP_PUBLIK` dengan IP VPS atau gunakan alias SSH milikmu.

```sh
rsync -avR compose.yaml Caddyfile .env.example \
  server/Dockerfile server/.dockerignore server/requirements.txt server/server.py server/static \
  ubuntu@IP_PUBLIK:~/esp32-cam/
ssh ubuntu@IP_PUBLIK
```

Di VPS, buat file konfigurasi saat pemasangan pertama.

```sh
cd ~/esp32-cam
install -m 600 .env.example .env
openssl rand -hex 32
openssl rand -hex 32
nano .env
```

| Variabel di `.env` | Isi |
| --- | --- |
| `CAMERA_DOMAIN` | Sudah terisi `live.caksa.id` |
| `INGEST_TOKEN` | Hasil acak pertama. Salin nilai yang sama ke firmware kamera |
| `VIEWER_USER` | Nama pengguna untuk login di browser |
| `VIEWER_PASS` | Hasil acak kedua atau sandi kuat tersendiri untuk penonton |

Compose membaca `.env` di sebelah `compose.yaml`. Jika VPS sudah memakai `.env` dengan domain lama, ubah barisnya menjadi `CAMERA_DOMAIN=live.caksa.id` dan jalankan kembali perintah Compose di bawah.

## 3. Jalankan dan cek dari browser

```sh
sudo docker compose config --quiet
sudo docker compose up -d --build --wait
sudo docker compose ps
```

Buka `https://live.caksa.id/` dan masuk dengan akun penonton. Selama kamera belum tersambung, halaman akan menampilkan **ESP32 offline**. Untuk memeriksa jalur HTTPS dari luar VPS, jalankan perintah berikut. Endpoint ini tetap merespons saat kamera mati.

```sh
curl --fail https://live.caksa.id/healthz
```

Hasil yang diharapkan adalah `{"status":"ok"}`. Jika domain belum bisa dibuka, periksa resolusi DNS, aturan ingress, dan pesan sertifikat dengan `sudo docker compose logs --tail=60 caddy`.

## 4. Sambungkan ESP32-CAM

Atur klien WebSocket di firmware untuk terhubung ke `wss://live.caksa.id/ingest?token=ISI_INGEST_TOKEN`. Jika library meminta parameter terpisah, gunakan host `live.caksa.id`, port `443`, dan path `/ingest?token=ISI_INGEST_TOKEN`. Ganti `ISI_INGEST_TOKEN` dengan nilai `INGEST_TOKEN` dari VPS. Aktifkan TLS, validasi sertifikat server dengan CA tepercaya, dan sinkronkan waktu ESP32 sebelum membuka koneksi.

Firmware perlu mengirim **satu JPEG utuh per pesan biner WebSocket** dan menerima pesan teks seperti `res:5`, `led:1`, atau `fps:10` untuk kontrol dari web. Source firmware belum ada di repositori ini. Jika firmware saat ini hanya menyediakan stream HTTP di LAN, firmware perlu mendukung protokol pengiriman tersebut.

Begitu frame masuk, status web berubah menjadi **Live**. Untuk mengecek status dari terminal, gunakan perintah berikut. Ganti `admin` jika kamu memilih nama pengguna lain. Curl akan meminta sandi. Saat video berjalan, `online` dan `streaming` bernilai `true`.

```sh
curl --fail --user admin https://live.caksa.id/api/state
```
