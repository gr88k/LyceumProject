
from flask import Flask
from flask import render_template, send_from_directory, jsonify, request
import json
import math


app = Flask(__name__, template_folder='.', static_folder='css')

ITEMS_PER_PAGE = 12


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
def hello_world():
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

@app.route('/css/catalog.css')
def catalog_custom_static():
    return send_from_directory('css', 'catalog.css')

@app.route('/data')
def catalog():
    with open('products.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    return jsonify(data)

@app.route('/about')
def about():
    return render_template("index.html") # отображение главной страницы

@app.route('/css/index.css')
def index_custom_static():
    return send_from_directory('css', 'index.css')


if __name__ == '__main__':
  app.run(debug=True)