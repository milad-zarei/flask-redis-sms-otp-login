import secrets
import redis
from flask import Flask, render_template, request, redirect, url_for, session, flash
from kavenegar import *
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.secret_key = 'your_super_secret_key_here'

# --- تنظیمات اتصال به PostgreSQL ---
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql+psycopg://postgres:123@127.0.0.1:5432/my_flask_db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# --- تنظیمات Redis ---
# decode_responses=True باعث می‌شود مقادیر به‌صورت str برگردند نه bytes
rds = redis.Redis(host='127.0.0.1', port=6379, db=0, decode_responses=True)

# --- تنظیمات OTP ---
OTP_EXPIRE_SECONDS = 120  # ۲ دقیقه
OTP_MAX_ATTEMPTS = 5
OTP_RESEND_COOLDOWN = 60  # فاصله حداقلی بین دو درخواست کد (ثانیه)

db = SQLAlchemy(app)


# --- مدل دیتابیس: فقط کاربران در دیتابیس ذخیره می شوند ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    phone = db.Column(db.String(15), unique=True, nullable=False)


with app.app_context():
    try:
        db.create_all()
        print("Successfully connected to PostgreSQL and tables created!")
    except Exception as e:
        print(f"Error connecting to PostgreSQL: {e}")

    try:
        rds.ping()
        print("Successfully connected to Redis!")
    except Exception as e:
        print(f"Error connecting to Redis: {e}")


# --- ساخت کلید Redis ---
# kind می‌تواند 'code'، 'attempts' یا 'cooldown' باشد
def key(kind, phone):
    return f'otp:{kind}:{phone}'


def clear_otp(phone):
    """حذف کد و شمارنده تلاش از Redis"""
    rds.delete(key('code', phone), key('attempts', phone))


@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        phone_number = request.form.get('phone')

        if not phone_number:
            flash('لطفاً شماره موبایل خود را وارد کنید.', 'danger')
            return redirect(url_for('login'))

        # محدودیت ارسال مجدد: SET NX فقط وقتی کلید وجود نداشته باشد مقدار می‌گذارد
        # (اتمیک است، پس درخواست‌های هم‌زمان هم نمی‌توانند از آن رد شوند)
        allowed = rds.set(key('cooldown', phone_number), 1, nx=True, ex=OTP_RESEND_COOLDOWN)
        if not allowed:
            wait = rds.ttl(key('cooldown', phone_number))
            wait = wait if wait and wait > 0 else OTP_RESEND_COOLDOWN
            flash(f'لطفاً {wait} ثانیه دیگر برای دریافت کد جدید صبر کنید.', 'warning')
            # اگر کد فعالی دارد، به صفحه تأیید برود
            if rds.exists(key('code', phone_number)):
                session['phone'] = phone_number
                return redirect(url_for('verify'))
            return redirect(url_for('login'))

        # تولید کد OTP تصادفی امن
        code = str(secrets.randbelow(9000) + 1000)

        # ثبت کاربر در PostgreSQL (فقط اگر وجود نداشت)
        user = User.query.filter_by(phone=phone_number).first()
        if not user:
            db.session.add(User(phone=phone_number))
            db.session.commit()

        # ذخیره کد در Redis با انقضای خودکار (جایگزین کد قبلی می‌شود)
        # شمارنده تلاش هم صفر می‌شود
        pipe = rds.pipeline()
        pipe.delete(key('attempts', phone_number))
        pipe.setex(key('code', phone_number), OTP_EXPIRE_SECONDS, code)
        pipe.execute()

        session['phone'] = phone_number

        # --- ارسال پیامک با کاوه‌نگار ---
        try:
            api = KavenegarAPI('api_key')  # کلید خود را اینجا قرار دهید
            params = {
                'sender': '2000660110',
                'receptor': phone_number,
                'message': f'کد تایید شما: {code}'
            }
            api.sms_send(params)
            flash(f'کد تایید به شماره {phone_number} ارسال شد.', 'success')
        except Exception as e:
            print(f"SMS Error: {e}")
            flash('خطا در ارسال پیامک! کد در کنسول چاپ شد.', 'warning')
            print(f"DEBUG: Code for {phone_number} is {code}")

        return redirect(url_for('verify'))

    return render_template('login.html')


@app.route('/verify', methods=['GET', 'POST'])
def verify():
    phone = session.get('phone')
    if not phone:
        return redirect(url_for('login'))

    if request.method == 'POST':
        user_code = (request.form.get('otp') or '').strip()

        saved_code = rds.get(key('code', phone))

        # کد وجود ندارد: یا منقضی شده (TTL تمام شده) یا قبلاً استفاده شده
        if saved_code is None:
            flash('کد تایید منقضی شده یا معتبر نیست. لطفاً کد جدید دریافت کنید.', 'danger')
            return redirect(url_for('login'))

        # شمارش تلاش (INCR اتمیک است، پس در درخواست‌های هم‌زمان هم دقیق می‌شمارد)
        attempts = rds.incr(key('attempts', phone))
        if attempts == 1:
            # شمارنده همزمان با کد منقضی می‌شود
            rds.expire(key('attempts', phone), OTP_EXPIRE_SECONDS)

        if attempts > OTP_MAX_ATTEMPTS:
            clear_otp(phone)
            flash('تعداد تلاش‌های شما بیش از حد مجاز بود. لطفاً کد جدید دریافت کنید.', 'danger')
            return redirect(url_for('login'))

        # مقایسه امن کد
        if secrets.compare_digest(saved_code, user_code):
            clear_otp(phone)  # کد یک‌بارمصرف است
            session['authenticated'] = True
            flash('با موفقیت وارد شدید!', 'success')
            return redirect(url_for('dashboard'))

        remaining = OTP_MAX_ATTEMPTS - attempts
        if remaining <= 0:
            clear_otp(phone)
            flash('تعداد تلاش‌های شما تمام شد. لطفاً کد جدید دریافت کنید.', 'danger')
            return redirect(url_for('login'))

        flash(f'کد تایید اشتباه است. {remaining} تلاش باقی مانده است.', 'danger')

    ttl = rds.ttl(key('code', phone))  # ثانیه‌های باقی‌مانده از ۱۲۰
    return render_template('verify.html', phone=phone, ttl=max(ttl, 0))


@app.route('/dashboard')
def dashboard():
    if not session.get('authenticated'):
        flash('لطفاً ابتدا وارد شوید.', 'warning')
        return redirect(url_for('login'))
    return render_template('dashboard.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


if __name__ == '__main__':
    app.run(debug=True, port=5000)