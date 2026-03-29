from server import app, db, User
from werkzeug.security import generate_password_hash

with app.app_context():
    # Проверяем, есть ли админ
    admin = User.query.filter_by(username='admin').first()
    
    if not admin:
        admin = User(
            username='admin',
            email='admin@site.com',
            tel = '00000000000',
            password=generate_password_hash('admin123'),
            role='Admin'
        )
        db.session.add(admin)
        db.session.commit()
        print("✅ Администратор создан!")
        print(f"   Логин: admin")
        print(f"   Пароль: admin123")
    else:
        print("⚠️ Администратор уже существует")
        print(f"   Имя: {admin.username}")
        print(f"   Email: {admin.email}")