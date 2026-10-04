from flask import Flask
from flask import render_template, send_from_directory, jsonify, request, redirect, url_for, flash
import json
import math
import os
import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from werkzeug.utils import secure_filename
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from models import db, User, Product, ProductVariant, CartItem, Order, OrderItem, PendingUser, PasswordReset
from werkzeug.security import generate_password_hash, check_password_hash
#from flask_admin import Admin
#from flask_admin.contrib.sqla import ModelView


app = Flask(__name__, template_folder='.', static_folder='css')

# app.config['FLASK_ADMIN_TEMPLATE_MODE'] = 'bootstrap4'

# admin = Admin(app, name='Urban Peak Admin')

# admin.add_view(ModelView(User, db.session, name='Пользователи'))
# admin.add_view(ModelView(Product, db.session, name='Товары'))
# admin.add_view(ModelView(ProductVariant, db.session, name='Модификации'))

ITEMS_PER_PAGE = 12

app.config['SECRET_KEY'] = 'секретный-ключ-для-сессий'  # Обязательно!
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'  # файл БД
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# ===== ЗАГРУЗКА ИЗОБРАЖЕНИЙ =====
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'static', 'images', 'products')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'gif'}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Копируем дефолтное изображение в папку загрузок если его там нет
_default_src = os.path.join(os.path.dirname(__file__), 'css', 'data', 'cap.png')
_default_dst = os.path.join(UPLOAD_FOLDER, 'cap.png')
if os.path.isfile(_default_src) and not os.path.isfile(_default_dst):
    import shutil
    shutil.copy2(_default_src, _default_dst)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

DEFAULT_IMAGE = '/static/images/products/cap.png'

def delete_image_file(image_url):
    """Удаляет файл изображения с диска. Никогда не удаляет дефолтное изображение."""
    if not image_url:
        return
    # Защита дефолтного изображения
    if image_url.rstrip('/').endswith('cap.png') and 'products' in image_url:
        return
    rel = image_url.lstrip('/')
    full_path = os.path.join(os.path.dirname(__file__), rel)
    if os.path.isfile(full_path):
        try:
            os.remove(full_path)
        except OSError:
            pass

# ===== КОНФИГУРАЦИЯ ПОЧТЫ (Яндекс 360) =====
MAIL_HOST     = 'smtp.yandex.ru'
MAIL_PORT     = 465          # SSL
MAIL_USER     = 'chav1975@urbanpeakshop.ru'   # аккаунт сотрудника
MAIL_PASSWORD = 'wgygdukrwlqpnlsg'
MAIL_FROM     = 'orders@urbanpeakshop.ru'     # корпоративный адрес «От»
MAIL_MANAGER  = 'orders@urbanpeakshop.ru'     # куда копия для менеджеров


def send_order_emails(order):
    """Отправляет два письма: клиенту и менеджерам."""

    # Строим таблицу позиций
    rows_html = ''
    rows_text = ''
    for item in order.items:
        v = item.variant
        name = v.product.name
        color = v.color or '—'
        size  = v.size  or '—'
        qty   = item.quantity
        price = int(item.price_per_unit)
        total = int(item.price_per_unit * qty)
        rows_html += (
            f'<tr>'
            f'<td style="padding:8px 12px;border-bottom:1px solid #eee;">{name}</td>'
            f'<td style="padding:8px 12px;border-bottom:1px solid #eee;">{color} / {size}</td>'
            f'<td style="padding:8px 12px;border-bottom:1px solid #eee;text-align:center;">{qty} шт.</td>'
            f'<td style="padding:8px 12px;border-bottom:1px solid #eee;text-align:right;">{price} ₽</td>'
            f'<td style="padding:8px 12px;border-bottom:1px solid #eee;text-align:right;font-weight:bold;">{total} ₽</td>'
            f'</tr>'
        )
        rows_text += f'  • {name} ({color}, {size}) — {qty} шт. × {price} ₽ = {total} ₽\n'

    total_price = int(order.total_price)
    order_date  = order.created_at.strftime('%d.%m.%Y %H:%M')

    # -------- HTML-шаблон из файла --------
    _tpl_path = os.path.join(os.path.dirname(__file__), 'email_order.html')
    with open(_tpl_path, encoding='utf-8') as f:
        _tpl = f.read()

    def make_html(title, greeting):
        comment_row = (
            f'<tr><td style="padding:6px 0;vertical-align:top;"><strong>Комментарий:</strong></td>'
            f'<td style="padding:6px 0;">{order.comment}</td></tr>'
        ) if order.comment else ''

        address = (
            f'{order.country}, {order.region}, г. {order.city}'
            f'{(", " + order.postal_code) if order.postal_code else ""}<br>{order.address}'
        )

        return (
            _tpl
            .replace('{{title}}',       title)
            .replace('{{greeting}}',    greeting)
            .replace('{{order_id}}',    f'#{order.id}')
            .replace('{{order_date}}',  order_date)
            .replace('{{full_name}}',   f'{order.last_name} {order.first_name} {order.patronymic}')
            .replace('{{phone}}',       order.phone)
            .replace('{{email}}',       order.email)
            .replace('{{org}}',         f'{order.org_type}{(" — " + order.company) if order.company else ""}')
            .replace('{{address}}',     address)
            .replace('{{comment_row}}', comment_row)
            .replace('{{rows}}',        rows_html)
            .replace('{{total}}',       str(total_price))
        )

    # -------- Plain-text --------
    def make_text(greeting):
        return (
            f"{greeting}\n\n"
            f"Заказ #{order.id} от {order_date}\n"
            f"{'='*40}\n"
            f"Получатель: {order.last_name} {order.first_name} {order.patronymic}\n"
            f"Телефон:    {order.phone}\n"
            f"E-mail:     {order.email}\n"
            f"Организация:{order.org_type}{(' — ' + order.company) if order.company else ''}\n"
            f"Адрес:      {order.country}, {order.region}, г. {order.city}"
            f"{(', ' + order.postal_code) if order.postal_code else ''}, {order.address}\n"
            + (f"Комментарий: {order.comment}\n" if order.comment else '')
            + f"\nСостав заказа:\n{rows_text}"
            f"{'='*40}\n"
            f"ИТОГО: {total_price} ₽\n\n"
            f"UrbanPeak · orders@urbanpeakshop.ru"
        )

    def build_msg(to_addr, subject, html_body, text_body):
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From']    = f'UrbanPeak <{MAIL_FROM}>'
        msg['To']      = to_addr
        msg.attach(MIMEText(text_body, 'plain', 'utf-8'))
        msg.attach(MIMEText(html_body, 'html',  'utf-8'))
        return msg

    # Письмо клиенту
    client_msg = build_msg(
        to_addr   = order.email,
        subject   = f'UrbanPeak: ваш заказ #{order.id} принят',
        html_body = make_html(
            title    = f'Ваш заказ #{order.id} успешно оформлен!',
            greeting = f'Здравствуйте, {order.first_name}! Мы получили ваш заказ и скоро свяжемся с вами для подтверждения.'
        ),
        text_body = make_text(f'Здравствуйте, {order.first_name}! Ваш заказ #{order.id} принят.')
    )

    # Письмо менеджерам
    manager_msg = build_msg(
        to_addr   = MAIL_MANAGER,
        subject   = f'Новый заказ #{order.id} от {order.last_name} {order.first_name}',
        html_body = make_html(
            title    = f'Новый заказ #{order.id}',
            greeting = f'Поступил новый заказ от клиента {order.last_name} {order.first_name} {order.patronymic}.'
        ),
        text_body = make_text(f'Новый заказ от {order.last_name} {order.first_name}.')
    )

    # Отправка через SMTP Яндекс 360 (SSL, порт 465)
    with smtplib.SMTP_SSL(MAIL_HOST, MAIL_PORT) as smtp:
        smtp.login(MAIL_USER, MAIL_PASSWORD)
        smtp.sendmail(MAIL_FROM, [order.email], client_msg.as_bytes())
        smtp.sendmail(MAIL_FROM, [MAIL_MANAGER], manager_msg.as_bytes())




db.init_app(app)
login_manager = LoginManager(app)
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


def get_paginated_products(filtered_products, page=1, per_page=ITEMS_PER_PAGE):
    """Получение товаров для текущей страницы"""
    total_items = len(filtered_products)
    
    if total_items == 0:
        return [], {
            'current_page': 1,
            'total_pages': 0,
            'total_items': 0,
            'has_prev': False,
            'has_next': False,
            'prev_page': 1,
            'next_page': 1,
            'per_page': per_page,
            'start_item': 0,
            'end_item': 0,
            'pages': []
        }
    
    total_pages = math.ceil(total_items / per_page)
    
    # Корректируем номер страницы
    page = max(1, min(page, total_pages))
    
    # Получаем товары для текущей страницы
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    products = filtered_products[start_idx:end_idx]
    
    # Рассчитываем диапазон страниц для пагинации
    start_page = max(1, page - 2)
    end_page = min(total_pages, page + 2)
    
    # Если у начала, показываем больше справа
    if start_page == 1 and end_page < total_pages:
        end_page = min(total_pages, start_page + 4)
    
    # Если у конца, показываем больше слева
    if end_page == total_pages and start_page > 1:
        start_page = max(1, end_page - 4)
    
    # Генерируем список страниц
    pages = list(range(start_page, end_page + 1))
    
    pagination = {
        'current_page': page,
        'total_pages': total_pages,
        'total_items': total_items,
        'has_prev': page > 1,
        'has_next': page < total_pages,
        'prev_page': page - 1,
        'next_page': page + 1,
        'per_page': per_page,
        'start_item': start_idx + 1,
        'end_item': min(start_idx + per_page, total_items),
        'pages': pages
    }
    
    return products, pagination

def search_products(products, query):
    """Поиск по названию, артикулу, описанию и категории"""
    if not query:
        return products
    
    query = query.lower().strip()
    results = []
    
    for product in products:
        name = product.get('name', '').lower()
        article = product.get('article', '').lower()

        
        # Проверяем вхождение запроса в любое из полей
        if (query in name or 
            query in article):
            results.append(product)
    
    return results
    

# @app.route('/catalog')
# def catalog():
#     page = request.args.get('page', default=1, type=int)
#     types = request.args.getlist('type')
#     colors = request.args.getlist('color')

#     search_query = request.args.get('q', '').strip()

#     #try:
#         #page = int(request.args.get('page', 1))
#     #except ValueError:
#         #page = 1

#     with open('products.json', 'r', encoding='utf-8') as f:
#         data = json.load(f)
#     products = data.get('products', [])

#     #filtered_products = products

#     def get_product_type(article):
#         if article and len(article) >= 2:
#             first_two = article[:2]
#             if first_two == 'SH':
#                 return 'hat'
#             elif first_two == 'CP':
#                 return 'cap'
#         return None  # если не определено
    
#     #filtered_products = products.copy()
#     filtered_products = search_products(products, search_query)


#     if types:
#         filtered_products = [
#             p for p in filtered_products
#             if get_product_type(p.get('article', '')) in types
#         ]

#     if colors:
#         filtered_products = [
#             p for p in filtered_products
#             if p.get('color') in colors
#         ]

#     #if search_query:
#         # Поиск по названию (регистронезависимый)
#         #filtered_products = [
#             #p for p in products 
#             #if search_query.lower() in p.get('name', '').lower()]


#     if not types and not colors and not search_query:  # если ничего не выбрано - показываем всё
#         filtered_products = products

#     # Получаем товары и данные пагинации
#     products, pagination = get_paginated_products(filtered_products, page)

#     return render_template("catalog.html", products=products, pagination = pagination,
#                            current_filters = {
#                                'type': types
#                            }) # отображение страницы каталога
@app.route('/catalog')
def catalog():
    import math
    page = request.args.get('page', 1, type=int)
    
    # 1. Получаем массивы выбранных фильтров из GET-запроса
    selected_categories = request.args.getlist('category')  # ['hat', 'cap']
    selected_colors = request.args.getlist('color')        # ['Черный', 'Белый']
    selected_sizes = request.args.getlist('size')          # ['52-54', 'Универсальный']
    show_out_of_stock = request.args.get('out_of_stock', '0') == '1'
    search_query = request.args.get('q', '').strip()

    # 2. Генерируем списки ВСЕХ доступных фильтров для вывода в HTML
    # Собираем уникальные цвета и размеры из базы данных
    all_colors = sorted([r[0] for r in db.session.query(ProductVariant.color).distinct() if r[0]])
    all_sizes = sorted([r[0] for r in db.session.query(ProductVariant.size).distinct() if r[0]])

    # 3. Строим базовый запрос к товарам
    query = Product.query.filter(db.or_(Product.is_hidden == False, Product.is_hidden == None))

    # Фильтр по поисковому запросу
    if search_query:
        query = query.filter(Product.name.ilike(f"%{search_query}%"))

    # Фильтр по типу товара (категории)
    if selected_categories:
        query = query.filter(Product.category.in_(selected_categories))

    # Фильтры по свойствам модификаций (цвет, размер, наличие)
    # Делаем JOIN с таблицей вариантов, если применены специфичные фильтры
    if selected_colors or selected_sizes or not show_out_of_stock:
        query = query.join(Product.variants)

        if selected_colors:
            query = query.filter(ProductVariant.color.in_(selected_colors))
        
        if selected_sizes:
            query = query.filter(ProductVariant.size.in_(selected_sizes))
            
        if not show_out_of_stock:
            query = query.filter(ProductVariant.stock > 0)

    # Получаем уникальные товары (избегаем дубликатов из-за JOIN)
    products_list = query.distinct().all()

    # Изображения: берём из БД, иначе дефолтное
    DEFAULT_IMAGE = '/static/images/products/cap.png'
    for product in products_list:
        product.image = product.main_image if product.main_image else DEFAULT_IMAGE

    # 4. Ручная пагинация отфильтрованного списка
    total_items = len(products_list)
    total_pages = math.ceil(total_items / ITEMS_PER_PAGE) if total_items > 0 else 1
    
    if page < 1: page = 1
    if page > total_pages: page = total_pages
    
    start_idx = (page - 1) * ITEMS_PER_PAGE
    end_idx = start_idx + ITEMS_PER_PAGE
    paginated_products = products_list[start_idx:end_idx]

    pagination = {
        'current_page': page,
        'total_pages': total_pages,
        'total_items': total_items,
        'start_item': start_idx + 1 if total_items > 0 else 0,
        'end_item': min(end_idx, total_items),
        'has_prev': page > 1,
        'has_next': page < total_pages,
        'prev_page': page - 1,
        'next_page': page + 1,
        'pages': list(range(max(1, page - 2), min(total_pages, page + 2) + 1))
    }

    # Строим строку параметров фильтров для передачи в пагинацию
    # (все параметры кроме 'page', чтобы ссылки пагинации их сохраняли)
    filter_params = []
    for cat in selected_categories:
        filter_params.append(f'category={cat}')
    for col in selected_colors:
        filter_params.append(f'color={col}')
    for siz in selected_sizes:
        filter_params.append(f'size={siz}')
    if show_out_of_stock:
        filter_params.append('out_of_stock=1')
    if search_query:
        filter_params.append(f'q={search_query}')
    filter_query_string = '&'.join(filter_params)

    return render_template(
        'catalog.html',
        products=paginated_products,
        pagination=pagination,
        all_colors=all_colors,
        all_sizes=all_sizes,
        selected_categories=selected_categories,
        selected_colors=selected_colors,
        selected_sizes=selected_sizes,
        show_out_of_stock=show_out_of_stock,
        filter_query_string=filter_query_string
    )

# @app.route('/product/<string:product_article>') # страница товара
# def product_page(product_article):
#     with open('products.json', 'r', encoding='utf-8') as f:
#         data = json.load(f)

#     product = None
#     for p in data['products']:
#         if p['article'] == product_article:
#             product = p
#             break

#     if not product:
#         return "Товар не найден", 404
    
#     return render_template("product.html", product=product)

# @app.route('/product/<article>')
# def product_detail(article):
#     # 1. Ищем товар в БД по его уникальному базовому артикулу (например, BK122036)
#     product = Product.query.filter_by(article=article).first_or_404()
    
#     # 2. Адаптируем под product.html (подменяем main_image на image)
#     product.image = product.main_image
    
#     # 3. В product.html выводится строка {{ product.color }}.
#     # Но у нас цвета лежат внутри таблицы ProductVariant.
#     # Соберем все доступные цвета для этого товара в одну красивую строку:
#     available_colors = set(variant.color for variant in product.variants if variant.color)
    
#     if available_colors:
#         product.color = ", ".join(available_colors)
#     else:
#         product.color = "Обычный"
        
#     return render_template('product.html', product=product)

@app.route('/product/<article>')
def product_detail(article):
    product = Product.query.filter_by(article=article).first_or_404()

    DEFAULT_IMAGE = '/static/images/products/cap.png'

    # Главное изображение: берём из БД, иначе дефолтное
    product.image = product.main_image if product.main_image else DEFAULT_IMAGE

    variants_data = {}
    for variant in product.variants:
        if variant.stock > 0:
            color = variant.color or 'Обычный'
            if color not in variants_data:
                variants_data[color] = []
            variants_data[color].append({
                'id':    variant.id,
                'size':  variant.size or 'Универсальный',
                'stock': variant.stock if variant.stock <= 10 else "> 10",
                'stock_real': variant.stock,
                'image': variant.image if variant.image else DEFAULT_IMAGE
            })

    color_icon = '/css/data/hat.png' if product.category == 'hat' else '/static/images/products/cap.png'

    return render_template(
        'product.html',
        product=product,
        variants_data=variants_data,
        color_icon=color_icon
    )

@app.route('/css/catalog.css')
def catalog_custom_static():
    return send_from_directory('css', 'catalog.css')

@app.route('/data')
def data():
    with open('products.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    return jsonify(data)

@app.route('/about')
def about():
    return render_template("index.html") # отображение главной страницы

@app.route('/')
def index():
    return render_template("index.html")

def send_confirm_email(email, username, code):
    """Отправляет письмо с кодом подтверждения регистрации."""
    _tpl_path = os.path.join(os.path.dirname(__file__), 'email_confirm.html')
    with open(_tpl_path, encoding='utf-8') as f:
        html = f.read()
    html = html.replace('{{username}}', username).replace('{{code}}', code)

    text = (
        f"Здравствуйте, {username}!\n\n"
        f"Ваш код подтверждения регистрации на UrbanPeak:\n\n"
        f"  {code}\n\n"
        f"Код действителен 15 минут.\n\n"
        f"Если вы не регистрировались — проигнорируйте письмо.\n\n"
        f"UrbanPeak · orders@urbanpeakshop.ru"
    )

    msg = MIMEMultipart('alternative')
    msg['Subject'] = 'UrbanPeak: код подтверждения регистрации'
    msg['From']    = f'UrbanPeak <{MAIL_FROM}>'
    msg['To']      = email
    msg.attach(MIMEText(text, 'plain', 'utf-8'))
    msg.attach(MIMEText(html,  'html',  'utf-8'))

    with smtplib.SMTP_SSL(MAIL_HOST, MAIL_PORT) as smtp:
        smtp.login(MAIL_USER, MAIL_PASSWORD)
        smtp.sendmail(MAIL_FROM, [email], msg.as_bytes())


@app.route('/register', methods=['GET', 'POST'])
def register():
    import random, datetime

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email    = request.form.get('email', '').strip()
        tel      = request.form.get('tel', '').strip()
        password = request.form.get('password', '')

        if not username or not email or not password or not tel:
            return render_template('register.html', error='Все поля обязательны')

        if User.query.filter_by(email=email).first():
            return render_template('register.html', error='Пользователь с таким email уже существует')

        # Удаляем старую pending-запись для этого email (если была)
        PendingUser.query.filter_by(email=email).delete()

        code = str(random.randint(100000, 999999))

        pending = PendingUser(
            username=username,
            email=email,
            tel=tel,
            password=generate_password_hash(password),
            code=code
        )
        db.session.add(pending)
        db.session.commit()

        try:
            send_confirm_email(email, username, code)
        except Exception as e:
            app.logger.error(f'Ошибка отправки кода подтверждения на {email}: {e}')
            return render_template('register.html', error='Не удалось отправить письмо. Проверьте email и попробуйте снова.')

        return redirect(url_for('verify', email=email))

    return render_template('register.html', error=None)


@app.route('/verify', methods=['GET', 'POST'])
def verify():
    import datetime
    email = request.args.get('email') or request.form.get('email', '')

    if not email:
        return redirect(url_for('register'))

    if request.method == 'POST':
        code_entered = request.form.get('code', '').strip()

        pending = PendingUser.query.filter_by(email=email).first()

        if not pending:
            return render_template('verify.html', email=email,
                                   error='Запрос не найден. Зарегистрируйтесь заново.')

        # Проверка срока — 15 минут
        age = datetime.datetime.utcnow() - pending.created_at
        if age.total_seconds() > 900:
            db.session.delete(pending)
            db.session.commit()
            return render_template('verify.html', email=email,
                                   error='Код истёк. Зарегистрируйтесь заново.')

        if pending.code != code_entered:
            return render_template('verify.html', email=email,
                                   error='Неверный код. Попробуйте ещё раз.')

        # Код верный — создаём настоящего пользователя
        new_user = User(
            username=pending.username,
            email=pending.email,
            tel=pending.tel,
            password=pending.password
        )
        db.session.add(new_user)
        db.session.delete(pending)
        db.session.commit()

        login_user(new_user)
        flash('Регистрация успешно завершена!', 'success')
        return redirect(url_for('catalog'))

    return render_template('verify.html', email=email, error=None)


@app.route('/resend-code')
def resend_code():
    import random
    email = request.args.get('email', '')
    pending = PendingUser.query.filter_by(email=email).first()

    if not pending:
        return redirect(url_for('register'))

    # Генерируем новый код и обновляем время
    pending.code = str(random.randint(100000, 999999))
    pending.created_at = __import__('datetime').datetime.utcnow()
    db.session.commit()

    try:
        send_confirm_email(email, pending.username, pending.code)
    except Exception as e:
        app.logger.error(f'Ошибка повторной отправки кода на {email}: {e}')

    return redirect(url_for('verify', email=email))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        user = User.query.filter_by(email=email).first()
        
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('catalog'))
        
        return render_template('login.html', error='Неверный email или пароль')
    return render_template('login.html', error=None)

@app.route('/profile', methods=['GET', 'POST'])
@login_required  # только для авторизованных
def profile():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        tel = request.form.get('tel')

        if not username or not email or not tel:
            flash('Все поля обязательны для заполнения', 'danger')
            return redirect(url_for('profile'))
        
        if email != current_user.email:  # email изменился
            existing_email = User.query.filter_by(email=email).first()
            if existing_email:
                flash('Этот email уже используется другим пользователем', 'danger')
                return redirect(url_for('profile'))
            
        if tel != current_user.tel:  # email изменился
            existing_tel = User.query.filter_by(tel=tel).first()
            if existing_tel:
                flash('Этот номер телефона уже используется другим пользователем', 'danger')
                return redirect(url_for('profile'))
            
        current_user.username = username
        current_user.email = email
        current_user.tel = tel

        try:
            db.session.commit()
            flash('Профиль успешно обновлен!', 'success')
            print("completed")
            return redirect(url_for('profile'))
        except:
            db.session.rollback()
            flash('Ошибка при сохранении данных', 'danger')
            return redirect(url_for('profile'))
        
    return render_template('profile.html', user=current_user)

@app.route('/logout')
@login_required
def logout():
    # Выход из аккаунта
    logout_user()
    
    # Показываем сообщение об успешном выходе
    flash('Вы вышли из аккаунта', 'info')
    
    # Перенаправляем на главную или страницу входа
    return redirect(url_for('catalog'))

@app.route('/css/index.css')
def index_custom_static():
    return send_from_directory('css', 'index.css')

@app.route('/css/product.css')
def product_custom_static():
    return send_from_directory('css', 'product.css')

@app.route('/css/register.css')
def register_custom_static():
    return send_from_directory('css', 'register.css')

@app.route('/js/color_map.js')
def color_map_js():
    return send_from_directory('.', 'color_map.js', mimetype='application/javascript')


@app.route('/css/checkout.css')
def checkout_custom_static():
    return send_from_directory('css', 'checkout.css')

@app.route('/css/profile.css')
def profile_custom_static():
    return send_from_directory('css', 'profile.css')

def parse_article(article_full):
    """
    Разбирает строку артикула вида 'BK124074 джинсовый 48-50' на код товара,
    цвет и размер. Код — первый токен с буквами+цифрами слитно (BK124074,
    SNM223035), либо чисто числовой токен (для 'Топ 808'). Размер — последний
    токен вида ДД-ДД, если есть. Всё остальное — цвет.
    Возвращает (base_article, color, size, remaining_parts).
    """
    article_tokens = article_full.split()
    if not article_tokens:
        return None, None, None, []

    code_idx = None
    for i, tok in enumerate(article_tokens):
        if re.search(r'[A-Za-zА-Яа-я]', tok) and re.search(r'\d', tok):
            code_idx = i
            break
    if code_idx is None:
        for i, tok in enumerate(article_tokens):
            if tok.isdigit():
                code_idx = i
                break
    if code_idx is None:
        code_idx = 0

    base_article = ' '.join(article_tokens[:code_idx + 1])
    remaining_parts = article_tokens[code_idx + 1:]

    color = "Обычный"
    size = "Универсальный"

    if remaining_parts and re.match(r'^\d{2}-\d{2}$', remaining_parts[-1]):
        size = remaining_parts[-1]
        color_parts = remaining_parts[:-1]
    else:
        color_parts = remaining_parts

    if color_parts:
        color = " ".join(color_parts).capitalize()

    return base_article, color, size, remaining_parts


def upsert_product_variant(name, article_full, stock, price):
    """
    Создаёт или обновляет Product + ProductVariant по строке вида из 1С/xlsx.
    Возвращает (product_created: bool, variant_created: bool) или None при ошибке.
    """
    if not article_full or price is None:
        return None

    base_article, color, size, remaining_parts = parse_article(article_full)
    if base_article is None:
        return None

    name_lower = name.lower()
    category = 'hat' if ('шапка' in name_lower or 'снуд' in name_lower) else 'cap'
    image_path = DEFAULT_IMAGE

    base_name = name
    for p in remaining_parts:
        base_name = base_name.replace(p, '')
    base_name = base_name.strip()

    product_created = False
    variant_created = False

    product = Product.query.filter_by(article=base_article).first()
    if not product:
        product = Product(
            name=base_name,
            article=base_article,
            category=category,
            price=price,
            main_image=image_path
        )
        db.session.add(product)
        db.session.flush()
        product_created = True
    else:
        product.price = price

    variant = ProductVariant.query.filter_by(
        product_id=product.id,
        size=size,
        color=color
    ).first()

    if variant:
        variant.stock = stock
    else:
        variant = ProductVariant(
            product_id=product.id,
            size=size,
            color=color,
            stock=stock
        )
        db.session.add(variant)
        variant_created = True

    return product_created, variant_created


@app.route('/admin/import-xlsx', methods=['GET', 'POST'])
def admin_import_xlsx():
    import openpyxl

    # POST — загрузка файла через форму
    if request.method == 'POST':
        if 'xlsx_file' not in request.files:
            return jsonify({"status": "error", "message": "Файл не выбран"}), 400
        f = request.files['xlsx_file']
        if not f.filename.endswith('.xlsx'):
            return jsonify({"status": "error", "message": "Нужен файл .xlsx"}), 400
        xlsx_path = os.path.join(os.path.dirname(__file__), 'каталог.xlsx')
        f.save(xlsx_path)
    else:
        xlsx_path = os.path.join(os.path.dirname(__file__), 'каталог.xlsx')

    if not os.path.exists(xlsx_path):
        return jsonify({
            "status": "error",
            "message": "Файл каталог.xlsx не найден. Загрузите его через форму."
        }), 404

    xlsx_filename = xlsx_path
        
    try:
        # Открываем книгу. data_only=True берет значения из ячеек, а не формулы
        wb = openpyxl.load_workbook(xlsx_filename, data_only=True)
        sheet = wb.active  # Читаем первый (активный) лист
    except Exception as e:
        return jsonify({
            "status": "error", 
            "message": f"Ошибка при открытии Excel файла: {str(e)}"
        }), 500

    inserted_products = 0
    inserted_variants = 0
    
    # Считываем названия колонок из первой строки, чтобы скрипт сам понял, где какие данные
    headers = [str(cell.value).strip() if cell.value else "" for cell in sheet[1]]
    
    # Динамически находим индексы нужных колонок
    try:
        col_name_idx = headers.index('Наименование')
        col_stock_idx = headers.index('Остаток')
        col_article_idx = headers.index('Артикул')
        col_price_idx = headers.index('Оптовые ₽')
    except ValueError as e:
        return jsonify({
            "status": "error", 
            "message": f"В первой строке Excel не найдены обязательные колонки. Ошибка: {str(e)}"
        }), 400

    # Перебираем строки таблицы, начиная со 2-й (min_row=2)
    for row in sheet.iter_rows(min_row=2, values_only=True):
        # Если строка пустая, пропускаем её
        if not row or row[col_name_idx] is None:
            continue
            
        name = str(row[col_name_idx]).strip()
        article_full = str(row[col_article_idx]).strip() if row[col_article_idx] is not None else ""
        stock_val = row[col_stock_idx]
        price_val = row[col_price_idx]
        
        # Пропускаем пустые артикулы и технический мусор от 1С
        if not article_full or "1С" in name or price_val is None:
            continue
            
        # Безопасное чтение чисел из ячеек Excel
        try:
            stock = int(float(stock_val)) if stock_val is not None else 0
            price = float(price_val)
        except (ValueError, TypeError):
            continue

        result = upsert_product_variant(name, article_full, stock, price)
        if result is None:
            continue
        product_created, variant_created = result
        if product_created:
            inserted_products += 1
        if variant_created:
            inserted_variants += 1

    try:
        db.session.commit()
        return jsonify({
            "status": "success",
            "inserted_models": inserted_products,
            "inserted_variants": inserted_variants
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500


# ===== API ДЛЯ СИНХРОНИЗАЦИИ С 1С =====
ONEC_API_TOKEN = "435bd9b26921cbf7790c0534d7f84cc32d4d5e40a49130a634bf745773d20be5"  # тот же токен должен быть прописан в 1С


@app.route('/api/sync/products', methods=['POST'])
def sync_products_from_1c():
    """
    Принимает от 1С JSON вида:
    {
        "products": [
            {"article": "BK124074 джинсовый 48-50", "name": "Бейсболка BK124074 джинсовый 48-50", "price": 450, "stock": 84},
            ...
        ]
    }
    Каждая строка — это одна вариация (как строка в Excel-выгрузке).
    Артикул содержит код+цвет+размер вместе, парсится так же как при xlsx-импорте.
    """
    token = request.headers.get('X-API-Key')
    if token != ONEC_API_TOKEN:
        return jsonify({"status": "error", "message": "Неверный токен доступа"}), 403

    data = request.get_json(silent=True)
    if not data or 'products' not in data:
        return jsonify({"status": "error", "message": "Ожидается JSON с полем 'products'"}), 400

    inserted_products = 0
    inserted_variants = 0
    updated_variants = 0
    skipped = 0

    for item in data['products']:
        name = str(item.get('name', '')).strip()
        article_full = str(item.get('article', '')).strip()
        price_val = item.get('price')
        stock_val = item.get('stock', 0)

        if not article_full or not name or price_val is None:
            skipped += 1
            continue

        try:
            price = float(price_val)
            stock = int(float(stock_val))
        except (ValueError, TypeError):
            skipped += 1
            continue

        result = upsert_product_variant(name, article_full, stock, price)
        if result is None:
            skipped += 1
            continue

        product_created, variant_created = result
        if product_created:
            inserted_products += 1
        if variant_created:
            inserted_variants += 1
        else:
            updated_variants += 1

    try:
        db.session.commit()
        return jsonify({
            "status": "success",
            "new_products": inserted_products,
            "new_variants": inserted_variants,
            "updated_variants": updated_variants,
            "skipped": skipped
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/cart/add', methods=['POST'])
def add_to_cart():
    if not current_user.is_authenticated:
        return jsonify({"status": "error", "message": "Добавить в корзину может только зарегистрированный пользователь!"}), 401
    
    data = request.get_json()
    items = data.get('items', [])
    
    if not items:
        return jsonify({"status": "error", "message": "Товары не выбраны"}), 400
        
    for item in items:
        variant_id = item.get('variant_id')
        quantity = item.get('quantity')
        
        if not variant_id or quantity <= 0:
            continue
            
        variant = ProductVariant.query.get(variant_id)
        if not variant or variant.stock < quantity:
            return jsonify({"status": "error", "message": "Недостаточно товара на складе"}), 400
            
        # Проверяем, есть ли уже этот товар в корзине
        cart_item = CartItem.query.filter_by(user_id=current_user.id, variant_id=variant_id).first()
        if cart_item:
            cart_item.quantity = min(cart_item.quantity + quantity, variant.stock)
        else:
            cart_item = CartItem(user_id=current_user.id, variant_id=variant_id, quantity=quantity)
            db.session.add(cart_item)
            
    db.session.commit()
    return jsonify({"status": "success", "message": "Успешно добавлено!"})

@app.route('/cart/get', methods=['GET'])
@login_required
def get_cart():
    cart_items = CartItem.query.filter_by(user_id=current_user.id).all()
    items_data = []
    total_price = 0
    
    for item in cart_items:
        variant = item.variant
        product = variant.product
        item_total = product.price * item.quantity
        total_price += item_total

        # Берём картинку из БД: вариации → товар → дефолт
        img_url = variant.image or product.main_image or DEFAULT_IMAGE

        items_data.append({
            "id": item.id,
            "name": product.name,
            "article": product.article,
            "color": variant.color or "Обычный",
            "size": variant.size or "Универсальный",
            "price": product.price,
            "quantity": item.quantity,
            "image": img_url,
            "item_total": item_total
        })
        
    return jsonify({
        "items": items_data,
        "total_price": total_price
    })

@app.route('/cart/remove/<int:item_id>', methods=['POST'])
@login_required
def remove_from_cart(item_id):
    item = CartItem.query.filter_by(id=item_id, user_id=current_user.id).first_or_404()
    db.session.delete(item)
    db.session.commit()
    return jsonify({"status": "success"})

@app.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():
    import datetime

    cart_items = CartItem.query.filter_by(user_id=current_user.id).all()
    if not cart_items:
        flash('Ваша корзина пуста', 'warning')
        return redirect(url_for('catalog'))

    # Собираем данные корзины для отображения
    items_data = []
    total_price = 0
    for item in cart_items:
        variant = item.variant
        product = variant.product
        item_total = product.price * item.quantity
        total_price += item_total
        items_data.append({
            'cart_item_id': item.id,
            'name': product.name,
            'article': product.article,
            'color': variant.color or 'Обычный',
            'size': variant.size or 'Универсальный',
            'price': product.price,
            'quantity': item.quantity,
            'item_total': item_total
        })

    if request.method == 'POST':
        # Валидация
        required = ['first_name', 'patronymic', 'last_name', 'phone', 'email',
                    'org_type', 'country', 'region', 'city', 'address']
        for field in required:
            if not request.form.get(field, '').strip():
                flash(f'Заполните все обязательные поля', 'danger')
                return render_template('checkout.html', items=items_data, total_price=total_price,
                                       form=request.form)

        if not request.form.get('agree'):
            flash('Необходимо согласиться на обработку персональных данных', 'danger')
            return render_template('checkout.html', items=items_data, total_price=total_price,
                                   form=request.form)

        # Создаём заказ
        # Сначала проверяем и списываем остатки — если чего-то не хватает, откатываемся
        stock_errors = []
        for item in cart_items:
            variant = item.variant
            if variant.stock < item.quantity:
                stock_errors.append(
                    f'«{variant.product.name}» ({variant.color}, {variant.size}): '
                    f'запрошено {item.quantity} шт., на складе {variant.stock} шт.'
                )
        if stock_errors:
            flash('Недостаточно товара на складе:\n' + '\n'.join(stock_errors), 'danger')
            return render_template('checkout.html', items=items_data, total_price=total_price,
                                   form=request.form)

        order = Order(
            user_id=current_user.id,
            first_name=request.form['first_name'].strip(),
            patronymic=request.form['patronymic'].strip(),
            last_name=request.form['last_name'].strip(),
            phone=request.form['phone'].strip(),
            email=request.form['email'].strip(),
            org_type=request.form['org_type'].strip(),
            company=request.form.get('company', '').strip(),
            country=request.form['country'].strip(),
            region=request.form['region'].strip(),
            city=request.form['city'].strip(),
            postal_code=request.form.get('postal_code', '').strip(),
            address=request.form['address'].strip(),
            comment=request.form.get('comment', '').strip(),
            total_price=total_price,
            created_at=datetime.datetime.utcnow()
        )
        db.session.add(order)
        db.session.flush()

        for item in cart_items:
            variant = item.variant
            product = variant.product
            order_item = OrderItem(
                order_id=order.id,
                variant_id=variant.id,
                quantity=item.quantity,
                price_per_unit=product.price
            )
            db.session.add(order_item)
            variant.stock -= item.quantity  # списываем со склада
            db.session.delete(item)

        db.session.commit()

        # Отправка писем
        try:
            send_order_emails(order)
        except Exception as e:
            app.logger.error(f'Ошибка отправки письма для заказа #{order.id}: {e}')

        flash(f'Заказ №{order.id} успешно оформлен!', 'success')
        return redirect(url_for('order_success', order_id=order.id))

    return render_template('checkout.html', items=items_data, total_price=total_price,
                           form={})


@app.route('/order/success/<int:order_id>')
@login_required
def order_success(order_id):
    order = Order.query.filter_by(id=order_id, user_id=current_user.id).first_or_404()
    return render_template('order_success.html', order=order)


@app.route('/my-orders')
@login_required
def my_orders():
    orders = Order.query.filter_by(user_id=current_user.id).order_by(Order.created_at.desc()).all()
    return render_template('my_orders.html', orders=orders)


@app.route('/admin/orders')
@login_required
def admin_orders():
    if current_user.role != 'Admin':
        return redirect(url_for('catalog'))
    orders = Order.query.order_by(Order.created_at.desc()).all()
    return render_template('admin_orders.html', orders=orders)


@app.route('/admin/orders/<int:order_id>/status', methods=['POST'])
@login_required
def update_order_status(order_id):
    if current_user.role != 'Admin':
        return jsonify({'status': 'error', 'message': 'Нет доступа'}), 403
    order = Order.query.get_or_404(order_id)
    new_status = request.get_json().get('status')
    allowed = ['Новый', 'В обработке', 'Отправлен', 'Выполнен', 'Отменён']
    if new_status not in allowed:
        return jsonify({'status': 'error', 'message': 'Недопустимый статус'}), 400

    old_status = order.status

    # Возврат остатков при отмене
    if new_status == 'Отменён' and old_status != 'Отменён':
        for item in order.items:
            item.variant.stock += item.quantity

    # Повторное списание если отмену «отменили»
    elif old_status == 'Отменён' and new_status != 'Отменён':
        stock_errors = []
        for item in order.items:
            if item.variant.stock < item.quantity:
                stock_errors.append(
                    f'«{item.variant.product.name}» ({item.variant.color}, {item.variant.size}): '
                    f'нужно {item.quantity} шт., на складе {item.variant.stock} шт.'
                )
        if stock_errors:
            return jsonify({
                'status': 'error',
                'message': 'Недостаточно товара на складе: ' + '; '.join(stock_errors)
            }), 400
        for item in order.items:
            item.variant.stock -= item.quantity

    order.status = new_status
    db.session.commit()
    return jsonify({'status': 'success'})


@app.route('/admin/products')
@login_required
def admin_products():
    if current_user.role != 'Admin':
        return redirect(url_for('catalog'))
    products = Product.query.order_by(Product.name).all()
    return render_template('admin_products.html', products=products)


@app.route('/admin/products/<int:product_id>', methods=['GET'])
@login_required
def admin_product_detail(product_id):
    if current_user.role != 'Admin':
        return jsonify({'status': 'error'}), 403
    product = Product.query.get_or_404(product_id)
    variants = [{
        'id': v.id, 'color': v.color or '', 'size': v.size or '',
        'stock': v.stock, 'image': v.image or ''
    } for v in product.variants]
    return jsonify({
        'id': product.id,
        'name': product.name,
        'article': product.article,
        'category': product.category,
        'price': product.price,
        'description': product.description or '',
        'is_hidden': product.is_hidden or False,
        'main_image': product.main_image or '',
        'variants': variants
    })


@app.route('/admin/products/<int:product_id>/update', methods=['POST'])
@login_required
def admin_update_product(product_id):
    if current_user.role != 'Admin':
        return jsonify({'status': 'error', 'message': 'Нет доступа'}), 403
    product = Product.query.get_or_404(product_id)
    data = request.get_json()

    if 'name' in data:
        product.name = data['name'].strip()
    if 'price' in data:
        try:
            product.price = float(data['price'])
        except (ValueError, TypeError):
            return jsonify({'status': 'error', 'message': 'Неверная цена'}), 400
    if 'category' in data:
        product.category = data['category']
    if 'description' in data:
        product.description = data['description'].strip()
    if 'is_hidden' in data:
        product.is_hidden = bool(data['is_hidden'])

    # Обновление вариантов
    if 'variants' in data:
        for vdata in data['variants']:
            if vdata.get('_delete') and vdata.get('id'):
                v = ProductVariant.query.get(vdata['id'])
                if v and v.product_id == product_id:
                    delete_image_file(v.image)
                    db.session.delete(v)
            elif vdata.get('id'):
                v = ProductVariant.query.get(vdata['id'])
                if v and v.product_id == product_id:
                    v.color = vdata.get('color', v.color)
                    v.size = vdata.get('size', v.size)
                    v.stock = int(vdata.get('stock', v.stock))
            elif vdata.get('_new'):
                new_v = ProductVariant(
                    product_id=product_id,
                    color=vdata.get('color', '').strip(),
                    size=vdata.get('size', '').strip(),
                    stock=int(vdata.get('stock', 0))
                )
                db.session.add(new_v)

    try:
        db.session.commit()
        return jsonify({'status': 'success'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/admin/products/new', methods=['POST'])
@login_required
def admin_create_product():
    if current_user.role != 'Admin':
        return jsonify({'status': 'error', 'message': 'Нет доступа'}), 403
    data = request.get_json()

    required = ['name', 'article', 'price']
    for f in required:
        if not data.get(f):
            return jsonify({'status': 'error', 'message': f'Поле {f} обязательно'}), 400

    if Product.query.filter_by(article=data['article'].strip()).first():
        return jsonify({'status': 'error', 'message': 'Товар с таким артикулом уже существует'}), 400

    try:
        product = Product(
            name=data['name'].strip(),
            article=data['article'].strip(),
            category=data.get('category', 'cap'),
            price=float(data['price']),
            description=data.get('description', '').strip(),
            is_hidden=False
        )
        db.session.add(product)
        db.session.flush()

        for vdata in data.get('variants', []):
            v = ProductVariant(
                product_id=product.id,
                color=vdata.get('color', '').strip(),
                size=vdata.get('size', '').strip(),
                stock=int(vdata.get('stock', 0))
            )
            db.session.add(v)

        db.session.commit()
        return jsonify({'status': 'success', 'product_id': product.id})
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/admin/products/<int:product_id>/toggle-hidden', methods=['POST'])
@login_required
def admin_toggle_hidden(product_id):
    if current_user.role != 'Admin':
        return jsonify({'status': 'error'}), 403
    product = Product.query.get_or_404(product_id)
    product.is_hidden = not product.is_hidden
    db.session.commit()
    return jsonify({'status': 'success', 'is_hidden': product.is_hidden})


@app.route('/css/admin_products.css')
def admin_products_css():
    return send_from_directory('css', 'admin_products.css')


@app.route('/static/images/products/<path:filename>')
def product_image(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)


# ---- Загрузить главное изображение товара ----
@app.route('/admin/products/<int:product_id>/upload-image', methods=['POST'])
@login_required
def upload_product_image(product_id):
    if current_user.role != 'Admin':
        return jsonify({'status': 'error'}), 403
    product = Product.query.get_or_404(product_id)

    f = request.files.get('image')
    if not f or not allowed_file(f.filename):
        return jsonify({'status': 'error', 'message': 'Недопустимый файл'}), 400

    # Удаляем старое изображение
    delete_image_file(product.main_image)

    ext = f.filename.rsplit('.', 1)[1].lower()
    filename = secure_filename(f'product_{product_id}_main.{ext}')
    f.save(os.path.join(UPLOAD_FOLDER, filename))
    product.main_image = f'/static/images/products/{filename}'
    db.session.commit()
    return jsonify({'status': 'success', 'url': product.main_image})


# ---- Удалить главное изображение товара ----
@app.route('/admin/products/<int:product_id>/delete-image', methods=['POST'])
@login_required
def delete_product_image(product_id):
    if current_user.role != 'Admin':
        return jsonify({'status': 'error'}), 403
    product = Product.query.get_or_404(product_id)
    delete_image_file(product.main_image)
    product.main_image = None
    db.session.commit()
    return jsonify({'status': 'success'})


# ---- Загрузить изображение вариации ----
@app.route('/admin/variants/<int:variant_id>/upload-image', methods=['POST'])
@login_required
def upload_variant_image(variant_id):
    if current_user.role != 'Admin':
        return jsonify({'status': 'error'}), 403
    variant = ProductVariant.query.get_or_404(variant_id)

    f = request.files.get('image')
    if not f or not allowed_file(f.filename):
        return jsonify({'status': 'error', 'message': 'Недопустимый файл'}), 400

    delete_image_file(variant.image)

    ext = f.filename.rsplit('.', 1)[1].lower()
    filename = secure_filename(f'variant_{variant_id}.{ext}')
    f.save(os.path.join(UPLOAD_FOLDER, filename))
    variant.image = f'/static/images/products/{filename}'
    db.session.commit()
    return jsonify({'status': 'success', 'url': variant.image})


# ---- Удалить изображение вариации ----
@app.route('/admin/variants/<int:variant_id>/delete-image', methods=['POST'])
@login_required
def delete_variant_image(variant_id):
    if current_user.role != 'Admin':
        return jsonify({'status': 'error'}), 403
    variant = ProductVariant.query.get_or_404(variant_id)
    delete_image_file(variant.image)
    variant.image = None
    db.session.commit()
    return jsonify({'status': 'success'})


# ---- Полное удаление товара ----
@app.route('/admin/products/<int:product_id>/delete', methods=['POST'])
@login_required
def admin_delete_product(product_id):
    if current_user.role != 'Admin':
        return jsonify({'status': 'error'}), 403
    product = Product.query.get_or_404(product_id)

    # Удаляем все файлы изображений
    delete_image_file(product.main_image)
    for v in product.variants:
        delete_image_file(v.image)

    # Каскадно удаляем вариации и сам товар
    for v in product.variants:
        db.session.delete(v)
    db.session.delete(product)
    db.session.commit()
    return jsonify({'status': 'success'})


def send_reset_email(email, username, code):
    """Отправляет письмо с кодом сброса пароля."""
    _tpl_path = os.path.join(os.path.dirname(__file__), 'email_reset.html')
    with open(_tpl_path, encoding='utf-8') as f:
        html = f.read()
    html = html.replace('{{username}}', username).replace('{{code}}', code)

    text = (
        f"Здравствуйте, {username}!\n\n"
        f"Вы запросили сброс пароля на UrbanPeak.\n\n"
        f"Ваш код подтверждения:\n\n"
        f"  {code}\n\n"
        f"Код действителен 15 минут.\n\n"
        f"Если вы не запрашивали сброс пароля — проигнорируйте письмо.\n\n"
        f"UrbanPeak · orders@urbanpeakshop.ru"
    )

    msg = MIMEMultipart('alternative')
    msg['Subject'] = 'UrbanPeak: сброс пароля'
    msg['From']    = f'UrbanPeak <{MAIL_FROM}>'
    msg['To']      = email
    msg.attach(MIMEText(text, 'plain', 'utf-8'))
    msg.attach(MIMEText(html,  'html',  'utf-8'))

    with smtplib.SMTP_SSL(MAIL_HOST, MAIL_PORT) as smtp:
        smtp.login(MAIL_USER, MAIL_PASSWORD)
        smtp.sendmail(MAIL_FROM, [email], msg.as_bytes())


@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        import random
        email = request.form.get('email', '').strip()

        user = User.query.filter_by(email=email).first()
        if not user:
            return render_template('forgot_password.html',
                                   error='Пользователь с таким email не найден')

        # Удаляем старый код если был
        PasswordReset.query.filter_by(email=email).delete()

        code = str(random.randint(100000, 999999))
        reset = PasswordReset(email=email, code=code)
        db.session.add(reset)
        db.session.commit()

        try:
            send_reset_email(email, user.username, code)
        except Exception as e:
            app.logger.error(f'Ошибка отправки кода сброса на {email}: {e}')
            return render_template('forgot_password.html',
                                   error='Не удалось отправить письмо. Проверьте email.')

        return redirect(url_for('verify_reset', email=email))

    return render_template('forgot_password.html', error=None)


@app.route('/verify-reset', methods=['GET', 'POST'])
def verify_reset():
    import datetime
    email = request.args.get('email') or request.form.get('email', '')

    if not email:
        return redirect(url_for('forgot_password'))

    if request.method == 'POST':
        code_entered = request.form.get('code', '').strip()
        reset = PasswordReset.query.filter_by(email=email).first()

        if not reset:
            return render_template('verify_reset.html', email=email,
                                   error='Запрос не найден. Попробуйте снова.')

        age = datetime.datetime.utcnow() - reset.created_at
        if age.total_seconds() > 900:
            db.session.delete(reset)
            db.session.commit()
            return render_template('verify_reset.html', email=email,
                                   error='Код истёк. Запросите новый.')

        if reset.code != code_entered:
            return render_template('verify_reset.html', email=email,
                                   error='Неверный код. Попробуйте ещё раз.')

        # Код верный — помечаем что можно менять пароль (храним в сессии)
        from flask import session
        session['reset_verified_email'] = email
        return redirect(url_for('new_password'))

    return render_template('verify_reset.html', email=email, error=None)


@app.route('/resend-reset-code')
def resend_reset_code():
    import random
    email = request.args.get('email', '')
    reset = PasswordReset.query.filter_by(email=email).first()

    if not reset:
        return redirect(url_for('forgot_password'))

    reset.code = str(random.randint(100000, 999999))
    reset.created_at = __import__('datetime').datetime.utcnow()
    db.session.commit()

    user = User.query.filter_by(email=email).first()
    if user:
        try:
            send_reset_email(email, user.username, reset.code)
        except Exception as e:
            app.logger.error(f'Ошибка повторной отправки кода сброса на {email}: {e}')

    return redirect(url_for('verify_reset', email=email))


@app.route('/new-password', methods=['GET', 'POST'])
def new_password():
    from flask import session
    email = session.get('reset_verified_email')

    if not email:
        return redirect(url_for('forgot_password'))

    if request.method == 'POST':
        password1 = request.form.get('password1', '')
        password2 = request.form.get('password2', '')

        if len(password1) < 6:
            return render_template('new_password.html',
                                   error='Пароль должен быть не менее 6 символов')
        if password1 != password2:
            return render_template('new_password.html',
                                   error='Пароли не совпадают')

        user = User.query.filter_by(email=email).first()
        if not user:
            return redirect(url_for('forgot_password'))

        user.password = generate_password_hash(password1)
        PasswordReset.query.filter_by(email=email).delete()
        session.pop('reset_verified_email', None)
        db.session.commit()

        login_user(user)
        flash('Пароль успешно изменён!', 'success')
        return redirect(url_for('catalog'))

    return render_template('new_password.html', error=None)


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)