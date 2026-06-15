from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()

class PasswordReset(db.Model):
    """Временный код для сброса пароля."""
    __tablename__ = 'password_resets'

    id         = db.Column(db.Integer, primary_key=True)
    email      = db.Column(db.String(120), nullable=False)
    code       = db.Column(db.String(6), nullable=False)
    created_at = db.Column(db.DateTime, default=__import__('datetime').datetime.utcnow)


class PendingUser(db.Model):
    """Временная запись до подтверждения email."""
    __tablename__ = 'pending_users'

    id         = db.Column(db.Integer, primary_key=True)
    username   = db.Column(db.String(80), nullable=False)
    email      = db.Column(db.String(120), unique=True, nullable=False)
    tel        = db.Column(db.String(12), nullable=False)
    password   = db.Column(db.String(200), nullable=False)  # уже хэшированный
    code       = db.Column(db.String(6), nullable=False)
    created_at = db.Column(db.DateTime, default=__import__('datetime').datetime.utcnow)


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    tel = db.Column(db.String(12), unique=True, nullable = False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String, default="User")


class Product(db.Model):
    __tablename__ = 'products'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    article = db.Column(db.String(50), unique=True, nullable=False)
    category = db.Column(db.String(50))  # 'hat' or 'cap'
    price = db.Column(db.Float, nullable=False)
    main_image = db.Column(db.String(200))
    description = db.Column(db.Text, default='')  # Описание товара (опционально)
    is_hidden = db.Column(db.Boolean, default=False)  # Скрыт ли товар из каталога
    
    variants = db.relationship('ProductVariant', backref='product', lazy=True)

class ProductVariant(db.Model):
    __tablename__ = 'product_variants'
    
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    
    size = db.Column(db.String(10))
    color = db.Column(db.String(30))
    #color_hex = db.Column(db.String(7))
    
    stock = db.Column(db.Integer, default=0)
    image = db.Column(db.String(200))

class Order(db.Model):
    __tablename__ = 'orders'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=__import__('datetime').datetime.utcnow)
    status = db.Column(db.String(30), default='Новый')  # Новый / В обработке / Отправлен / Выполнен / Отменён

    # Покупатель
    first_name = db.Column(db.String(80), nullable=False)
    patronymic = db.Column(db.String(80), nullable=False)
    last_name = db.Column(db.String(80), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    org_type = db.Column(db.String(50), nullable=False)
    company = db.Column(db.String(120))

    # Адрес
    country = db.Column(db.String(60), nullable=False)
    region = db.Column(db.String(80), nullable=False)
    city = db.Column(db.String(80), nullable=False)
    postal_code = db.Column(db.String(10))
    address = db.Column(db.String(200), nullable=False)

    # Доп. информация
    comment = db.Column(db.Text)

    total_price = db.Column(db.Float, nullable=False, default=0)

    items = db.relationship('OrderItem', backref='order', lazy=True)
    user = db.relationship('User', backref='orders', lazy=True)


class OrderItem(db.Model):
    __tablename__ = 'order_items'

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    variant_id = db.Column(db.Integer, db.ForeignKey('product_variants.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    price_per_unit = db.Column(db.Float, nullable=False)

    variant = db.relationship('ProductVariant', backref='order_items', lazy=True)


class CartItem(db.Model):
    __tablename__ = 'cart_items'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    variant_id = db.Column(db.Integer, db.ForeignKey('product_variants.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)

    # Связи для быстрого доступа к данным
    variant = db.relationship('ProductVariant', backref='cart_items', lazy=True)