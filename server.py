
from flask import Flask
from flask import render_template, send_from_directory, jsonify, request, redirect, url_for
import json
import math
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user
from models import db, User
from werkzeug.security import generate_password_hash, check_password_hash


app = Flask(__name__, template_folder='.', static_folder='css')

ITEMS_PER_PAGE = 12

app.config['SECRET_KEY'] = 'секретный-ключ-для-сессий'  # Обязательно!
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'  # файл БД
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

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
    

@app.route('/catalog')
def catalog():
    page = request.args.get('page', default=1, type=int)
    types = request.args.getlist('type')
    colors = request.args.getlist('color')

    search_query = request.args.get('q', '').strip()

    #try:
        #page = int(request.args.get('page', 1))
    #except ValueError:
        #page = 1

    with open('products.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    products = data.get('products', [])

    #filtered_products = products

    def get_product_type(article):
        if article and len(article) >= 2:
            first_two = article[:2]
            if first_two == 'SH':
                return 'hat'
            elif first_two == 'CP':
                return 'cap'
        return None  # если не определено
    
    #filtered_products = products.copy()
    filtered_products = search_products(products, search_query)


    if types:
        filtered_products = [
            p for p in filtered_products
            if get_product_type(p.get('article', '')) in types
        ]

    if colors:
        filtered_products = [
            p for p in filtered_products
            if p.get('color') in colors
        ]

    #if search_query:
        # Поиск по названию (регистронезависимый)
        #filtered_products = [
            #p for p in products 
            #if search_query.lower() in p.get('name', '').lower()]


    if not types and not colors and not search_query:  # если ничего не выбрано - показываем всё
        filtered_products = products

    # Получаем товары и данные пагинации
    products, pagination = get_paginated_products(filtered_products, page)

    return render_template("catalog.html", products=products, pagination = pagination,
                           current_filters = {
                               'type': types
                           }) # отображение страницы каталога

@app.route('/product/<string:product_article>') # страница товара
def product_page(product_article):
    with open('products.json', 'r', encoding='utf-8') as f:
        data = json.load(f)

    product = None
    for p in data['products']:
        if p['article'] == product_article:
            product = p
            break

    if not product:
        return "Товар не найден", 404
    
    return render_template("product.html", product=product)

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

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        tel = request.form.get('tel')
        password = request.form.get('password')

        if not username or not email or not password or not tel:
            return "Все поля обязательны", 400
        
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            return "Пользователь с таким email уже существует", 400
        
        hashed_password = generate_password_hash(password)

        new_user = User(
            username=username,
            email=email,
            tel = tel,
            password=hashed_password
        )

        try:
            db.session.add(new_user)
            db.session.commit()

            #with app.app_context():
                #all_users = User.query.all()
                #for user in all_users:
                    #print(f"ID: {user.id}")
                    #print(f"Имя: {user.username}")
                    #print(f"Email: {user.email}")
                    #print(f"Пароль (хэш): {user.password[:50]}...")
                    #print("-" * 50)

            return redirect(url_for('login'))
        except:
            db.session.rollback()
            return "Ошибка при сохранении", 500
        
    return render_template("register.html")

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        user = User.query.filter_by(email=email).first()
        
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('catalog'))
        
        else:
            return "Неверный email или пароль", 400
    return render_template("login.html")

@app.route('/css/index.css')
def index_custom_static():
    return send_from_directory('css', 'index.css')

@app.route('/css/product.css')
def product_custom_static():
    return send_from_directory('css', 'product.css')

@app.route('/css/register.css')
def register_custom_static():
    return send_from_directory('css', 'register.css')

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)