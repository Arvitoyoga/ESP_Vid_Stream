# Hosting ESP32-CAM di VPS Oracle dengan Docker

ESP32-CAM membuka koneksi WSS keluar ke VPS dan mengirim frame JPEG. Browser membuka domain yang sama lewat HTTPS untuk menonton dan mengatur kamera. Koneksi keluar ini bisa dipakai dari Wi-Fi rumah tanpa membuka port di router. Konfigurasi ini melayani satu kamera, dengan satu proses relay karena koneksi dan frame disimpan di memori.

## 1. Siapkan domain dan jaringan

- Arahkan record DNS `A` untuk `live.caksa.id` ke IPv4 publik VPS. Jika ada record `AAAA`, pastikan IPv6-nya juga mencapai VPS.
- Nginx di host memakai TCP `80` untuk validasi sertifikat dan redirect, serta TCP `443` untuk HTTPS dan WSS. Izinkan kedua port itu di Network Security Group atau Security List Oracle serta di firewall VM. Port `8081` terikat ke `127.0.0.1` untuk koneksi dari Nginx ke Docker. [Dokumentasi aturan jaringan Oracle](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/securityrules.htm)
- Pasang Docker Engine dan plugin Docker Compose di VM. Contoh perintah di bawah memakai image VM Ubuntu dan akun SSH `ubuntu`. [Panduan instalasi Docker untuk Ubuntu](https://docs.docker.com/engine/install/ubuntu/)

## 2. Salin proyek dan isi konfigurasi

Dari folder proyek di komputer lokal, ganti `IP_PUBLIK` dengan IP VPS atau gunakan alias SSH milikmu.

```sh
rsync -avR compose.yaml nginx .env.example \
  server/Dockerfile server/.dockerignore server/requirements.txt server/server.py server/static \
  ubuntu@IP_PUBLIK:~/ESP_Vid_Stream/
ssh ubuntu@IP_PUBLIK
```

Di VPS, masuk ke `~/ESP_Vid_Stream`. Jika relay sudah berjalan dan `.env` sudah terisi, lanjut ke langkah 3. Untuk pemasangan pertama, buat kredensial berikut.

```sh
cd ~/ESP_Vid_Stream
install -m 600 .env.example .env
openssl rand -hex 32
openssl rand -hex 32
nano .env
```

| Variabel di `.env` | Isi |
| --- | --- |
| `INGEST_TOKEN` | Hasil acak pertama. Salin nilai yang sama ke firmware kamera |
| `VIEWER_USER` | Nama pengguna untuk login di browser |
| `VIEWER_PASS` | Hasil acak kedua atau sandi kuat tersendiri untuk penonton |

## 3. Jalankan relay di VPS

```sh
cd ~/ESP_Vid_Stream
sudo docker compose config --quiet
sudo docker compose up -d --build --wait --remove-orphans
sudo docker compose ps
curl --fail http://127.0.0.1:8081/healthz
```

Opsi `--remove-orphans` membersihkan container Caddy dari konfigurasi proyek sebelumnya. Hasil pemeriksaan relay yang diharapkan adalah `{"status":"ok"}`, termasuk saat kamera mati.

## 4. Tambahkan live.caksa.id ke Nginx yang sudah berjalan

Contoh Ubuntu ini memakai `/etc/nginx/conf.d/*.conf`. Jika sudah ada blok `server_name live.caksa.id`, gabungkan pengaturan ke blok yang cocok agar domain hanya terdaftar sekali per port.

Aktifkan konfigurasi HTTP dulu agar Certbot dapat memvalidasi domain melalui port `80`.

```sh
sudo install -d -m 755 /var/www/letsencrypt
sudo install -m 644 nginx/live.caksa.id-http.conf /etc/nginx/conf.d/
sudo nginx -t && sudo systemctl reload nginx
```

Jika sertifikat untuk `live.caksa.id` sudah tersedia, gunakan lokasi sertifikat dan private key tersebut dalam `nginx/live.caksa.id-https.conf` dan lanjutkan ke pemasangan HTTPS. Untuk sertifikat baru, pasang Certbot jika diperlukan (`sudo apt install certbot`), lalu jalankan perintah berikut. Certbot menggunakan webroot dan memuat ulang Nginx setelah sertifikat diperbarui. [Panduan Certbot](https://eff-certbot.readthedocs.io/en/stable/using.html#webroot)

```sh
sudo certbot certonly --webroot -w /var/www/letsencrypt \
  --cert-name live.caksa.id -d live.caksa.id --deploy-hook "systemctl reload nginx"
```

Setelah sertifikat tersedia, aktifkan situs HTTPS dan periksa jalur publiknya.

```sh
sudo install -m 644 nginx/live.caksa.id-https.conf /etc/nginx/conf.d/
sudo nginx -t && sudo systemctl reload nginx
curl --fail https://live.caksa.id/healthz
```

Responsnya harus sama dengan pemeriksaan relay lokal. Buka `https://live.caksa.id/` dan masuk dengan akun penonton. Selama kamera belum tersambung, halaman menampilkan **ESP32 offline**.

## 5. Sambungkan ESP32-CAM

Atur klien WebSocket di firmware untuk terhubung ke `wss://live.caksa.id/ingest?token=ISI_INGEST_TOKEN`. Jika library meminta parameter terpisah, gunakan host `live.caksa.id`, port `443`, dan path `/ingest?token=ISI_INGEST_TOKEN`. Ganti `ISI_INGEST_TOKEN` dengan nilai `INGEST_TOKEN` dari VPS. Aktifkan TLS, validasi sertifikat server dengan CA tepercaya, dan sinkronkan waktu ESP32 sebelum membuka koneksi.

Firmware perlu mengirim **satu JPEG utuh per pesan biner WebSocket** dan menerima pesan teks seperti `res:5`, `led:1`, atau `fps:10` untuk kontrol dari web. Source firmware belum ada di repositori ini. Jika firmware saat ini hanya menyediakan stream HTTP di LAN, firmware perlu mendukung protokol pengiriman tersebut.

Begitu frame masuk, status web berubah menjadi **Live**. Untuk mengecek status dari terminal, gunakan perintah berikut. Ganti `admin` jika kamu memilih nama pengguna lain. Curl akan meminta sandi. Saat video berjalan, `online` dan `streaming` bernilai `true`.

```sh
curl --fail --user admin https://live.caksa.id/api/state
```
