# Flask Redis SMS OTP Login

A simple phone-number login system built with **Flask**. Users sign in with a one-time password (OTP) sent by SMS through [Kavenegar](https://kavenegar.com). OTP codes, attempt counters, and resend cooldowns are stored in **Redis** with automatic expiry, while users are stored in **PostgreSQL**.

## Features

- Passwordless login with a 4-digit SMS code
- Cryptographically secure code generation (`secrets`)
- **2-minute expiry** for every code (handled by Redis TTL)
- **Attempt limit**: the code is invalidated after 5 wrong attempts
- **Resend cooldown**: a new code can be requested only every 60 seconds
- Live countdown timer on the verification page
- One-time codes: a code is deleted immediately after successful use
- Constant-time code comparison (`secrets.compare_digest`)
- RTL (Persian) UI built with Bootstrap 5

## Tech Stack

| Component | Purpose |
|---|---|
| Flask | Web framework |
| Flask-SQLAlchemy | ORM |
| PostgreSQL (`psycopg`) | Persistent user storage |
| Redis | Temporary storage for OTP codes, attempts, and cooldowns |
| Kavenegar | SMS delivery |
| Bootstrap 5 (RTL) | Frontend styling |

## Project Structure

```
.
├── app_db.py            # Main Flask application
├── requirements.txt     # Python dependencies
└── templates/
    ├── login.html       # Phone number entry
    ├── verify.html      # OTP entry with countdown timer
    └── dashboard.html   # Page shown after successful login
```

## How It Works

1. The user enters a phone number on `/`.
2. The app checks the resend cooldown, generates a random 4-digit code, and stores it in Redis with a 120-second TTL.
3. The code is sent by SMS via Kavenegar and the user is redirected to `/verify`.
4. The user enters the code. Each attempt is counted in Redis.
5. On success the session is marked as authenticated and the user is redirected to `/dashboard`.

### Redis keys

| Key | Value | TTL |
|---|---|---|
| `otp:code:<phone>` | The OTP code | 120 s |
| `otp:attempts:<phone>` | Number of attempts for the current code | 120 s |
| `otp:cooldown:<phone>` | `1` (marker only) | 60 s |

## Prerequisites

- Python 3.10+
- PostgreSQL
- Redis (or a compatible server)
- A Kavenegar account and API key

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/<your-username>/<your-repo>.git
cd <your-repo>
```

### 2. Create a virtual environment and install dependencies

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate
# Linux / macOS
source .venv/bin/activate

pip install -r requirements.txt
```

### 3. Create the PostgreSQL database

```sql
CREATE DATABASE my_flask_db;
```

Tables are created automatically on the first run.

### 4. Start Redis

Redis does not run natively on Windows. Use one of the following:

- **Docker:** `docker run -d -p 6379:6379 --name redis redis`
- **Memurai** (Redis-compatible Windows service): <https://www.memurai.com>
- **WSL2:** `sudo apt install redis-server && sudo service redis-server start`

On Linux/macOS, install Redis from your package manager and start it.

### 5. Configure the application

Edit the following values in `app_db.py`:

| Setting | Description |
|---|---|
| `app.secret_key` | A long random string used to sign sessions |
| `SQLALCHEMY_DATABASE_URI` | PostgreSQL connection string |
| `KavenegarAPI('api_key')` | Your Kavenegar API key |
| `sender` | Your Kavenegar sender number |

Generate a strong secret key with:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

OTP behavior can be tuned with these constants:

```python
OTP_EXPIRE_SECONDS = 120   # code validity
OTP_MAX_ATTEMPTS = 5       # wrong attempts allowed
OTP_RESEND_COOLDOWN = 60   # seconds between code requests
```

> **Never commit real secrets** (secret key, database password, API key) to GitHub. Load them from environment variables or a `.env` file that is listed in `.gitignore`.

### 6. Run

```bash
python app_db.py
```

Open <http://127.0.0.1:5000> in your browser. On startup you should see:

```
Successfully connected to PostgreSQL and tables created!
Successfully connected to Redis!
```

## Development Notes

- If the SMS request fails (for example with an invalid API key), the code is printed to the console so you can keep testing locally. **Remove this debug output before deploying.**
- `debug=True` is enabled for development only. Use a production WSGI server (such as Gunicorn or Waitress) and set `debug=False` in production.

## Possible Improvements

- Load all secrets from environment variables
- Validate Iranian mobile numbers (`09XXXXXXXXX`) on the server side
- Switch `/logout` to a POST request with CSRF protection
- Per-IP rate limiting (for example with Flask-Limiter and Redis)
- Send SMS in a background worker (for example with Celery)

## License

Add a license of your choice (for example MIT) before publishing.
