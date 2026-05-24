from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()

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